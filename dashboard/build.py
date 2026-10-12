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
# Verified tested ref at experiment time; never infer the candidate from simulator main.
KNOWN_TESTED_REFS = {'782c2b5e303115f90bf8f81b724da5717362de39':'erg-spike-gate'}

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
            result['traces'][key]=motor_chart(z.read(matches[0]),preserve_extrema=data['comparison'].get('experiment')=='continuous-long-ride-v1')
    return result

def validate_metadata(metadata):
    valid_tree(metadata)
    if not isinstance(metadata,dict): raise ValueError('Metadata must be an object')
    for key in ('run_started_at','run_completed_at','imported_at','candidate_ref','release_tag','release_published_at','baseline_release_tag','baseline_release_published_at','adapter_commit','simulator_commit','notes','workflow_url','workflow_conclusion','workflow_updated_at'):
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
                if name in files: summary['traces'][key][variant]=chart(files[name],preserve_extrema=manifest.get('experiment')=='continuous-long-ride-v1')
        (dest/'data.json').write_text(json.dumps(summary,allow_nan=False,separators=(',',':')))
        (dest/'comparison.json').write_bytes(files['comparison.json'])
        (dest/'SHA256SUMS.txt').write_text('\n'.join(f'{hashlib.sha256(data).hexdigest()}  {name}' for name,data in files.items())+'\n')
    except BaseException:
        shutil.rmtree(dest); raise

def build(history,output):
    output.mkdir(parents=True,exist_ok=True)
    entries=[]
    for run in sorted(history.iterdir()) if history.exists() else []:
        if run.name == '.gitkeep': continue
        if not run.is_dir() or not SAFE.fullmatch(run.name): raise ValueError('Unsafe history directory')
        data=read_json(run/'data.json'); validate(data['comparison']); valid_tree(data); validate_metadata(data['metadata'])
        if data['id']!=run.name: raise ValueError('History id mismatch')
        target=output/'runs'/run.name; target.mkdir(parents=True,exist_ok=True)
        for name in ('data.json','comparison.json','SHA256SUMS.txt','evidence.zip'):
            if (run/name).is_symlink(): raise ValueError('Symlink')
            shutil.copyfile(run/name,target/name)
        display=output/MOTOR_RENDERER; display.mkdir(exist_ok=True)
        try: motor=motor_display(run,data)
        except (ValueError,KeyError,UnicodeError,zipfile.BadZipFile,csv.Error):
            motor={'source_field':'motor_steps','units':'steps','renderer':MOTOR_RENDERER,'traces':{},'status':'unavailable'}
        (display/(run.name+'.json')).write_text(json.dumps(motor,allow_nan=False,separators=(',',':')))
        candidate=data['comparison'].get('firmware',{}).get('candidate',{}).get('commit')
        display_ref=data['metadata'].get('release_tag') or data['metadata'].get('candidate_ref') or KNOWN_TESTED_REFS.get(candidate) or ('commit '+candidate[:12] if isinstance(candidate,str) else 'Unrecorded ref')
        if data['metadata'].get('evidence_only') is True: continue
        entries.append({'id':run.name,'metadata':data['metadata'],'display_ref':display_ref,'candidate_commit':candidate,'status':data['comparison']['status'],'pairs':len(data['comparison'].get('runs',[])),'selections':[{'scenario':row['scenario'],'seed':row['seed']} for row in data['comparison'].get('runs',[])]})
    for name in ('index.html','app.js','style.css'): shutil.copyfile(Path(__file__).parent/name,output/name)
    template=(output/'index.html').read_text()
    for asset in ('app.js','style.css'):
        version=hashlib.sha256((output/asset).read_bytes()).hexdigest()[:16]
        template=template.replace('"'+asset+'"','"'+asset+'?v='+version+'"')
    (output/'index.html').write_text(template)
    (output/'history.json').write_text(json.dumps(entries))
    (output/'.nojekyll').touch()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--history',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--input',type=Path);p.add_argument('--run-id');p.add_argument('--metadata',type=Path)
    a=p.parse_args()
    if a.input:
        materialize(a.input,a.history/a.run_id,a.run_id,read_json(a.metadata) if a.metadata else {})
    build(a.history,a.output)
if __name__=='__main__': main()
