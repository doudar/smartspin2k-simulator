#!/usr/bin/env python3
"""Trusted, dependency-free Pages renderer. Treat every experiment file as data.

Never copies HTML/JS/SVG or executes code from an experiment/artifact. Evidence
archives contain only allowlisted inert files. Existing runs are immutable.
"""
import argparse, csv, hashlib, io, json, math, re, shutil, zipfile
from pathlib import Path

SAFE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}$')
ALLOWED = {'.json', '.csv', '.log', '.ptab', '.txt'}
MAX_FILE = 32 * 1024 * 1024
MAX_RUN = 200 * 1024 * 1024
LONG_RIDE_EXPERIMENTS = {'continuous-long-ride-v1', 'continuous-long-ride-sprints-v2'}
# Verified tested ref at experiment time; never infer the candidate from simulator main.
# Exact commits also recorded with candidate_ref='erg-spike-gate' in archived runs.
# Push-triggered short experiments omit candidate_ref; group only these verified
# snapshots without rewriting their original metadata.
KNOWN_TESTED_REFS = {
    '782c2b5e303115f90bf8f81b724da5717362de39':'erg-spike-gate',
    'b776105cd1e3edb93a91bada3f27aaecc25533dc':'erg-spike-gate',
}

def read_json(path):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents): raise ValueError('Symlink in JSON path')
    if path.stat().st_size > MAX_FILE: raise ValueError('JSON too large')
    return json.loads(path.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))

def valid_tree(value, depth=0):
    if depth > 25: raise ValueError('JSON too deep')
    if isinstance(value, dict):
        if len(value)>1000: raise ValueError('Oversized object')
        for k,v in value.items():
            if not isinstance(k,str) or len(k)>300: raise ValueError('Invalid key')
            valid_tree(v,depth+1)
    elif isinstance(value,list):
        if len(value)>10000: raise ValueError('Oversized list')
        for v in value: valid_tree(v,depth+1)
    elif isinstance(value,str):
        if len(value)>50000: raise ValueError('Oversized string')
    elif isinstance(value,float) and not math.isfinite(value): raise ValueError('Nonfinite number')
    elif value is not None and not isinstance(value,(str,int,float,bool)): raise ValueError('Invalid value')

def collect(source):
    if source.is_symlink(): raise ValueError('Symlink evidence root')
    files={}; total=0
    for p in sorted(source.rglob('*')):
        if p.is_symlink(): raise ValueError('Symlink in evidence')
        if not p.is_file(): continue
        rel=p.relative_to(source)
        if any(not SAFE.fullmatch(s) for s in rel.parts): raise ValueError('Unsafe evidence path')
        if p.suffix not in ALLOWED or 'build' in rel.parts: continue
        size=p.stat().st_size; total+=size
        if size>MAX_FILE or total>MAX_RUN: raise ValueError('Evidence exceeds size limit')
        files[str(rel)]=p.read_bytes()
    return files

def validate(manifest):
    valid_tree(manifest)
    if not isinstance(manifest,dict) or manifest.get('status') not in ('complete','failed','incomplete','unsupported'): raise ValueError('Invalid status')
    runs=manifest.get('runs',[])
    if not isinstance(runs,list) or len(runs)>500: raise ValueError('Invalid runs')
    for key in ('error','coverage_level','budget_status','simulator_sha256','profile_sha256','package_config_sha256'):
        if manifest.get(key) is not None and not isinstance(manifest[key],str): raise ValueError('Invalid manifest text')
    firmware=manifest.get('firmware',{})
    if not isinstance(firmware,dict) or any(not isinstance(v,dict) for v in firmware.values()): raise ValueError('Invalid firmware provenance')
    seen=set()
    for row in runs:
        if not isinstance(row,dict): raise ValueError('Run must be an object')
        if not SAFE.fullmatch(row.get('scenario','')) or type(row.get('seed')) is not int: raise ValueError('Invalid scenario/seed')
        if row.get('artifact_key') is not None and (not isinstance(row['artifact_key'],str) or not SAFE.fullmatch(row['artifact_key'])): raise ValueError('Invalid artifact key')
        key=(row['scenario'],row['seed'])
        if key in seen: raise ValueError('Duplicate scenario/seed')
        seen.add(key)
        for decision in (row,row.get('reported_power_comparison',{})):
            if not isinstance(decision,dict): raise ValueError('Invalid decision object')
            for flag in ('passed','absolute_passed','relative_passed'):
                if decision.get(flag) is not None and type(decision[flag]) is not bool: raise ValueError('Invalid decision')
            failures=decision.get('failures',[])
            if not isinstance(failures,list) or any(not isinstance(f,str) for f in failures): raise ValueError('Invalid failures')
    return manifest

def decimate_extrema(rows,columns=(2,3),transition_column=1,max_points=1801):
    """Keep endpoints, target edges and each bucket's extrema, in time order."""
    if len(rows)<=max_points:return rows
    anchors={0,len(rows)-1}
    if transition_column is not None:
        for i in range(1,len(rows)):
            if rows[i][transition_column]!=rows[i-1][transition_column]:anchors.update((i-1,i))
    # Unbounded adversarial target edges cannot enlarge the renderer payload.
    if len(anchors)>600:
        ordered=sorted(anchors);anchors={ordered[round(i*(len(ordered)-1)/599)] for i in range(600)}
    slots=4+2*len(columns)
    buckets=max(1,(max_points-len(anchors))//slots)
    for b in range(buckets):
        start=b*len(rows)//buckets;end=(b+1)*len(rows)//buckets
        anchors.update((start,end-1))
        for col in columns:
            finite=[i for i in range(start,end) if rows[i][col] is not None]
            if finite:anchors.update((min(finite,key=lambda i:rows[i][col]),max(finite,key=lambda i:rows[i][col])))
        missing=[i for i in range(start,end) if any(rows[i][col] is None for col in columns)]
        if missing:anchors.update((missing[0],missing[-1]))
    return [rows[i] for i in sorted(anchors)]

def chart(raw,*,preserve_extrema=False):
    rows=[]
    for n,row in enumerate(csv.DictReader(io.StringIO(raw.decode('utf8')))):
        if n>1000000: raise ValueError('Trace too long')
        vals=[float(row[k]) for k in ('time_s','target_w','power_w','latest_delivered_sensor_power_w')]
        if not all(math.isfinite(v) and abs(v)<1e9 for v in vals): raise ValueError('Invalid trace')
        rows.append(vals)
    if preserve_extrema:return decimate_extrema(rows)
    step=max(1,math.ceil(len(rows)/1800))
    return rows[::step]+([rows[-1]] if rows and (len(rows)-1)%step else [])

# Versioned, reproducible display data lives outside immutable evidence runs.
MOTOR_RENDERER = 'motor-v1'
CADENCE_RENDERER = 'cadence-v1'
EVIDENCE_RELEASE_ROOT = 'https://github.com/doudar/smartspin2k-simulator/releases/download/'
MAX_EVIDENCE_ZIP = 2 * 1024 * 1024 * 1024 - 1
MAX_SAFE_INTEGER = 9007199254740991

def validate_evidence_location(location,run_id=None):
    """Accept only the publisher's content-addressed asset in this repository."""
    valid_tree(location)
    if not isinstance(location,dict) or set(location)!={'schema_version','url','sha256','size','asset_id'}:
        raise ValueError('Invalid evidence location fields')
    if type(location['schema_version']) is not int or location['schema_version']!=1:
        raise ValueError('Invalid evidence location version')
    digest=location['sha256']
    if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):
        raise ValueError('Invalid evidence SHA-256')
    for field,limit in (('size',MAX_EVIDENCE_ZIP),('asset_id',MAX_SAFE_INTEGER)):
        if type(location[field]) is not int or not 0<location[field]<=limit:
            raise ValueError('Invalid evidence '+field)
    if run_id is not None and (not isinstance(run_id,str) or not SAFE.fullmatch(run_id)): raise ValueError('Invalid evidence run id')
    pattern=re.escape(EVIDENCE_RELEASE_ROOT)+r'evidence-[1-9][0-9]{0,19}-[1-9][0-9]{0,8}/([a-zA-Z0-9][a-zA-Z0-9_.-]{0,100})-'+digest+r'\.zip'
    match=re.fullmatch(pattern,location['url']) if isinstance(location['url'],str) else None
    if not match or run_id is not None and match[1]!=run_id:
        raise ValueError('Invalid evidence release URL')
    return location

def validate_display(display,data,renderer):
    """Validate bounded persisted presentation data without reopening remote ZIPs."""
    valid_tree(display)
    if renderer not in (MOTOR_RENDERER,CADENCE_RENDERER): raise ValueError('Unknown display renderer')
    cadence=renderer==CADENCE_RENDERER
    expected={'source_field':'cadence_rpm' if cadence else 'motor_steps',
              'units':'rpm' if cadence else 'steps','renderer':renderer}
    if cadence: expected['received_source_field']=None
    if not isinstance(display,dict) or set(display)-set(expected)-{'traces','status'}:
        raise ValueError('Invalid display fields')
    if any(key not in display or display[key]!=value for key,value in expected.items()):
        raise ValueError('Invalid display provenance')
    traces=display.get('traces')
    if not isinstance(traces,dict): raise ValueError('Invalid display traces')
    if 'status' in display and (display['status']!='unavailable' or traces):
        raise ValueError('Invalid display status')
    keys={f"{row['scenario']}-{row['seed']}" for row in data['comparison'].get('runs',[])}
    if set(traces)-keys: raise ValueError('Unknown display trace')
    for rows in traces.values():
        if not isinstance(rows,list) or len(rows)>1801: raise ValueError('Oversized display trace')
        previous=None
        for row in rows:
            if not isinstance(row,list) or len(row)!=(3 if cadence else 2): raise ValueError('Invalid display row')
            for column,value in enumerate(row):
                if column and value is None: continue
                if type(value) not in (int,float) or abs(value)>=1e9 or not math.isfinite(value):
                    raise ValueError('Invalid display number')
                if cadence and value<0: raise ValueError('Invalid cadence display number')
            if previous is not None and row[0]<=previous: raise ValueError('Nonmonotonic display time')
            previous=row[0]
            if cadence and row[2] is not None: raise ValueError('Unrecorded received cadence')
    return display

def motor_chart(raw,*,preserve_extrema=False):
    rows=[]
    reader=csv.DictReader(io.StringIO(raw.decode('utf8')))
    if not reader.fieldnames or 'motor_steps' not in reader.fieldnames:
        return []
    for n,row in enumerate(reader):
        if n>1000000: raise ValueError('Trace too long')
        t=float(row['time_s'])
        if not math.isfinite(t) or abs(t)>=1e9: raise ValueError('Invalid trace time')
        try: position=float(row.get('motor_steps',''))
        except (ValueError,TypeError): position=None
        if position is not None and (not math.isfinite(position) or abs(position)>=1e9): position=None
        rows.append([t,position])
    if preserve_extrema:return decimate_extrema(rows,columns=(1,),transition_column=None)
    step=max(1,math.ceil(len(rows)/1800))
    # Preserve missing-data gaps even when their rows fall between display samples.
    result=[[rows[i][0], rows[i][1] if all(r[1] is not None for r in rows[max(0,i-step+1):i+1]) else None] for i in range(0,len(rows),step)]
    if rows and (len(rows)-1)%step:
        result.append([rows[-1][0],rows[-1][1] if all(r[1] is not None for r in rows[len(result)*step-step+1:]) else None])
    return result

def motor_display(run,data):
    result={'source_field':'motor_steps','units':'steps','renderer':MOTOR_RENDERER,'traces':{}}
    with zipfile.ZipFile(run/'evidence.zip') as z:
        if len(z.infolist())>10000: raise ValueError('Too many evidence entries')
        for row in data['comparison'].get('runs',[]):
            key=f"{row['scenario']}-{row['seed']}"
            artifact_key=row.get('artifact_key',key)
            name=f'candidate/{artifact_key}/trace.csv'
            matches=[entry for entry in z.infolist() if entry.filename==name]
            if not matches: continue
            if len(matches)!=1 or matches[0].file_size>MAX_FILE: raise ValueError('Invalid motor evidence')
            result['traces'][key]=motor_chart(z.read(matches[0]),preserve_extrema=data['comparison'].get('experiment') in LONG_RIDE_EXPERIMENTS)
    return result

def cadence_chart(raw):
    """Candidate modeled rider RPM, never workout cues or reconstructed firmware RPM.

    trace.csv's cadence_rpm is the rider/bike input recorded by runner.run().
    cadence.csv's reported_rpm is also model-side, despite its name. Neither is
    the firmware's decoded runtime cadence. Reserve a nullable third column for
    that signal, but do not infer it from CSC packets or intermittent ERG logs.
    """
    rows=[]
    reader=csv.DictReader(io.StringIO(raw.decode('utf8')))
    if not reader.fieldnames or 'cadence_rpm' not in reader.fieldnames:
        return []
    if reader.fieldnames.count('cadence_rpm')!=1 or reader.fieldnames.count('time_s')!=1:
        raise ValueError('Invalid cadence columns')
    for n,row in enumerate(reader):
        if n>1000000: raise ValueError('Trace too long')
        try: t=float(row['time_s'])
        except (ValueError,TypeError): raise ValueError('Invalid trace time') from None
        if not math.isfinite(t) or not 0<=t<1e9: raise ValueError('Invalid trace time')
        if rows and t<=rows[-1][0]: raise ValueError('Nonmonotonic trace time')
        try: cadence=float(row.get('cadence_rpm',''))
        except (ValueError,TypeError): cadence=None
        if cadence is not None and (not math.isfinite(cadence) or not 0<=cadence<1e9): cadence=None
        rows.append([t,cadence,None])
    # Only the recorded column participates: including the always-null reserved
    # column would hide internal rider gaps behind an "all rows missing" test.
    return decimate_extrema(rows,columns=(1,),transition_column=None)

def cadence_display(run,data):
    result={'source_field':'cadence_rpm','received_source_field':None,
            'units':'rpm','renderer':CADENCE_RENDERER,'traces':{}}
    with zipfile.ZipFile(run/'evidence.zip') as z:
        if len(z.infolist())>10000: raise ValueError('Too many evidence entries')
        for row in data['comparison'].get('runs',[]):
            key=f"{row['scenario']}-{row['seed']}"
            artifact_key=row.get('artifact_key',key)
            name=f'candidate/{artifact_key}/trace.csv'
            matches=[entry for entry in z.infolist() if entry.filename==name]
            if not matches: continue
            if len(matches)!=1 or matches[0].file_size>MAX_FILE: raise ValueError('Invalid cadence evidence')
            result['traces'][key]=cadence_chart(z.read(matches[0]))
    return result

def validate_metadata(metadata):
    valid_tree(metadata)
    if not isinstance(metadata,dict): raise ValueError('Metadata must be an object')
    for key in ('run_started_at','run_completed_at','imported_at','candidate_ref','release_tag','release_published_at','baseline_release_tag','baseline_release_published_at','adapter_commit','simulator_commit','notes','workflow_url','workflow_conclusion','workflow_updated_at','experiment','training_run_id'):
        if metadata.get(key) is not None and not isinstance(metadata[key],str): raise ValueError('Invalid metadata text')
    return metadata

def materialize(source, dest, run_id, metadata):
    if not SAFE.fullmatch(run_id): raise ValueError('Invalid run id')
    if dest.exists(): raise ValueError('Immutable run already exists: '+run_id)
    files=collect(source)
    if 'comparison.json' not in files: files['comparison.json']=json.dumps({'status':'incomplete','passed':False,'runs':[],'error':'No comparison.json produced; inspect workflow log.'}).encode()
    manifest=validate(json.loads(files['comparison.json']))
    validate_metadata(metadata)
    dest.mkdir(parents=True)
    try:
        with zipfile.ZipFile(dest/'evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
            for name,data in files.items(): z.writestr(name,data)
        summary={'id':run_id,'metadata':metadata,'comparison':manifest,'traces':{}}
        for row in manifest.get('runs',[]):
            key=f"{row['scenario']}-{row['seed']}"
            summary['traces'][key]={}
            for variant in ('baseline','candidate'):
                artifact_key=row.get('artifact_key',key)
                name=f'{variant}/{artifact_key}/trace.csv'
                if name in files: summary['traces'][key][variant]=chart(files[name],preserve_extrema=manifest.get('experiment') in LONG_RIDE_EXPERIMENTS)
        (dest/'data.json').write_text(json.dumps(summary,allow_nan=False,separators=(',',':')))
        (dest/'comparison.json').write_bytes(files['comparison.json'])
        (dest/'SHA256SUMS.txt').write_text('\n'.join(f'{hashlib.sha256(data).hexdigest()}  {name}' for name,data in files.items())+'\n')
    except BaseException:
        shutil.rmtree(dest); raise

def build(history,output):
    output.mkdir(parents=True,exist_ok=True)
    entries=[]; evidence_index={}
    for run in sorted(history.iterdir()) if history.exists() else []:
        if run.name == '.gitkeep': continue
        if not run.is_dir() or not SAFE.fullmatch(run.name): raise ValueError('Unsafe history directory')
        data=read_json(run/'data.json'); validate(data['comparison']); valid_tree(data); validate_metadata(data['metadata'])
        if data['id']!=run.name: raise ValueError('History id mismatch')
        optional=('evidence-location.json','motor-display.json','cadence-display.json')
        for name in ('evidence.zip',*optional):
            if (run/name).is_symlink(): raise ValueError('Symlink in evidence record')
        location=validate_evidence_location(read_json(run/'evidence-location.json'),run.name) if (run/'evidence-location.json').exists() else None
        local_zip=(run/'evidence.zip').is_file()
        if not local_zip and location is None: raise ValueError('Missing local or external evidence: '+run.name)
        persisted={}
        for name,renderer in (('motor-display.json',MOTOR_RENDERER),('cadence-display.json',CADENCE_RENDERER)):
            if (run/name).exists(): persisted[renderer]=validate_display(read_json(run/name),data,renderer)
            elif not local_zip: raise ValueError('Missing persisted display: '+name)
        if location: evidence_index[run.name]=location['url']
        target=output/'runs'/run.name; target.mkdir(parents=True,exist_ok=True)
        names=['data.json','comparison.json','SHA256SUMS.txt']+[name for name in ('evidence.zip',*optional) if (run/name).exists()]
        for name in names:
            if (run/name).is_symlink(): raise ValueError('Symlink')
            shutil.copyfile(run/name,target/name)
        if not local_zip and (target/'evidence.zip').exists(): (target/'evidence.zip').unlink()
        display=output/MOTOR_RENDERER; display.mkdir(exist_ok=True)
        try: motor=persisted[MOTOR_RENDERER] if MOTOR_RENDERER in persisted else motor_display(run,data)
        except (ValueError,KeyError,UnicodeError,zipfile.BadZipFile,csv.Error):
            motor={'source_field':'motor_steps','units':'steps','renderer':MOTOR_RENDERER,'traces':{},'status':'unavailable'}
        (display/(run.name+'.json')).write_text(json.dumps(motor,allow_nan=False,separators=(',',':')))
        cadence_dir=output/CADENCE_RENDERER; cadence_dir.mkdir(exist_ok=True)
        try: cadence=persisted[CADENCE_RENDERER] if CADENCE_RENDERER in persisted else cadence_display(run,data)
        except (ValueError,KeyError,UnicodeError,zipfile.BadZipFile,csv.Error):
            cadence={'source_field':'cadence_rpm','received_source_field':None,
                     'units':'rpm','renderer':CADENCE_RENDERER,'traces':{},'status':'unavailable'}
        (cadence_dir/(run.name+'.json')).write_text(json.dumps(cadence,allow_nan=False,separators=(',',':')))
        candidate=data['comparison'].get('firmware',{}).get('candidate',{}).get('commit')
        display_ref=data['metadata'].get('release_tag') or data['metadata'].get('candidate_ref') or KNOWN_TESTED_REFS.get(candidate) or ('commit '+candidate[:12] if isinstance(candidate,str) else 'Unrecorded ref')
        if data['metadata'].get('evidence_only') is True: continue
        entries.append({'id':run.name,'metadata':data['metadata'],'display_ref':display_ref,'candidate_commit':candidate,'status':data['comparison']['status'],'pairs':len(data['comparison'].get('runs',[])),'selections':[{'scenario':row['scenario'],'seed':row['seed']} for row in data['comparison'].get('runs',[])]})
    for name in ('index.html','app.js','hover.js','style.css'): shutil.copyfile(Path(__file__).parent/name,output/name)
    template=(output/'index.html').read_text()
    for asset in ('app.js','hover.js','style.css'):
        version=hashlib.sha256((output/asset).read_bytes()).hexdigest()[:16]
        template=template.replace('"'+asset+'"','"'+asset+'?v='+version+'"')
    (output/'index.html').write_text(template)
    (output/'history.json').write_text(json.dumps(entries))
    (output/'evidence-index.json').write_text(json.dumps(evidence_index,sort_keys=True,separators=(',',':')))
    (output/'.nojekyll').touch()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--history',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--input',type=Path);p.add_argument('--run-id');p.add_argument('--metadata',type=Path)
    a=p.parse_args()
    if a.input:
        materialize(a.input,a.history/a.run_id,a.run_id,read_json(a.metadata) if a.metadata else {})
    build(a.history,a.output)
if __name__=='__main__': main()
