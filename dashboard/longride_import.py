"""Trusted adapter for long-ride DATA, never an experiment-code import.

Split large batches into bounded per-case archives; preserve original file names
and the original full manifest. Training evidence is archived once and linked.
"""
import json,shutil
from pathlib import Path
from build import ALLOWED,MAX_FILE,MAX_RUN,SAFE,read_json,valid_tree,validate_metadata

STATES={'empty':'empty','partial':'partially learned','full':'fully learned tested range'}

def copy_inert(source,dest):
    if source.is_symlink():raise ValueError('Symlink long-ride root')
    total=0
    for p in source.rglob('*') if source.exists() else []:
        if p.is_symlink():raise ValueError('Symlink in long-ride evidence')
        if not p.is_file():continue
        rel=p.relative_to(source)
        if any(not SAFE.fullmatch(part) for part in rel.parts):raise ValueError('Unsafe evidence path')
        if p.suffix not in ALLOWED or 'build' in rel.parts:continue
        size=p.stat().st_size;total+=size
        if size>MAX_FILE or total>MAX_RUN:raise ValueError('Long-ride evidence exceeds bounded archive limits')
        target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)

def checked_case(row):
    if not isinstance(row,dict) or row.get('minutes') not in (30,60,90) or row.get('initial_state') not in STATES or type(row.get('seed')) is not int:
        raise ValueError('Invalid long-ride case')
    return row['minutes'],row['initial_state'],row['seed']

def metadata_for(root,source):
    file=source/'run-metadata.json'
    value=read_json(file) if file.is_file() else read_json(root/'run-metadata.json') if (root/'run-metadata.json').is_file() else {}
    return validate_metadata(value)

def prepare(root,stage,identity):
    """Return canonical evidence directories, retaining partial/missing cases."""
    paired=root/'paired' if (root/'paired').is_dir() else root
    if not (paired/'longride.json').is_file():return None
    manifest=read_json(paired/'longride.json');valid_tree(manifest)
    if not isinstance(manifest,dict) or manifest.get('experiment')!='continuous-long-ride-v1':raise ValueError('Unknown long-ride manifest')
    if not isinstance(manifest.get('initial_fixtures',{}),dict):raise ValueError('Invalid fixture manifest')
    rows=manifest.get('runs',[])
    if not isinstance(rows,list) or len(rows)>27:raise ValueError('Long-ride batch too large')
    recorded={}
    for row in rows:
        key=checked_case(row)
        windows=row.get('window_comparisons',{})
        if not isinstance(windows,dict) or set(windows)!=set(('early','middle','late')):raise ValueError('Incomplete probe decisions')
        checks=[row,row.get('reported_power_comparison',{})]
        for window in windows.values():
            if not isinstance(window,dict):raise ValueError('Invalid probe decision')
            checks.extend((window,window.get('reported_power_comparison',{})))
        for check in checks:
            if not isinstance(check,dict) or any(type(check.get(flag)) is not bool for flag in ('absolute_passed','relative_passed')):raise ValueError('Unmeasured long-ride decision')
            if not isinstance(check.get('failures',[]),list) or any(not isinstance(f,str) for f in check.get('failures',[])):raise ValueError('Invalid probe failures')
        if key in recorded:raise ValueError('Duplicate long-ride case')
        recorded[key]=row
    requested=manifest.get('requested_cases') or [dict(minutes=k[0],initial_state=k[1],seed=k[2]) for k in recorded]
    if not isinstance(requested,list) or len(requested)>27:raise ValueError('Requested matrix too large')
    cases=[checked_case(r) for r in requested]
    if len(cases)!=len(set(cases)):raise ValueError('Duplicate requested case')
    if not cases:cases=[None] # Preserve an early batch failure instead of hiding it.
    sources=[];training_id=None
    training=root/'training'
    if (training/'longride.json').is_file():
        tm=read_json(training/'longride.json');valid_tree(tm)
        if not isinstance(tm,dict):raise ValueError('Invalid training manifest')
        dest=stage/'training';copy_inert(training,dest)
        canonical={**tm,'runs':[],'experiment':'long-ride-training-v1'}
        (dest/'comparison.json').write_text(json.dumps(canonical,allow_nan=False))
        meta=metadata_for(root,training);meta.update({'evidence_only':True,'notes':meta.get('notes','')+' Shared original production-learning training evidence. Not a paired acceptance run.'})
        (dest/'run-metadata.json').write_text(json.dumps(meta));sources.append(dest)
        training_id=identity+'-training'
    for key in cases:
        if key is None:
            name='long-incomplete';row=None
        else:
            minutes,state,seed=key;name=f'long-{minutes}m-{state}-{seed}';row=recorded.get(key)
        dest=stage/name;dest.mkdir(parents=True,exist_ok=True)
        canonical={k:v for k,v in manifest.items() if k not in ('runs','initial_fixtures','training')}
        canonical['batch_status']=manifest.get('status','incomplete')
        canonical['coverage_level']='Continuous production packet/controller simulation with one native process per ride; no radio, ESP32 scheduler or physical hardware'
        canonical['budget_status']='Provisional engineering bands, including early/middle/late probes; not hardware fidelity proof'
        canonical['runs']=[];canonical['status']='incomplete';canonical['passed']=False
        if key:
            artifact_key=f'long_{minutes}m_{state}-{seed}'
            for variant in ('baseline','candidate'):
                copy_inert(paired/variant/artifact_key,dest/variant/artifact_key)
            fixture=manifest.get('initial_fixtures',{}).get(state)
            (dest/'initial-fixture.json').write_text(json.dumps(fixture,allow_nan=False))
            if row is not None:
                checks=[row,row.get('reported_power_comparison',{})]
                for window in row.get('window_comparisons',{}).values():checks.extend((window,window.get('reported_power_comparison',{})))
                overall={name:all(check.get(name) is True for check in checks) for name in ('absolute_passed','relative_passed')}
                overall['passed']=overall['absolute_passed'] and overall['relative_passed']
                canonical['runs']=[{**row,'scenario':'long_ride','artifact_key':artifact_key,'overall_checks':overall,'overall_checks_scope':'Whole ride plus early/middle/late probes, both plant and delivered-sensor signals'}]
                canonical['status']='complete';canonical['passed']=row.get('passed')
            else:canonical['error']='This requested case did not complete. Partial files, if produced, remain in the raw archive. '+str(manifest.get('error',''))
        else:canonical['error']='Long-ride batch failed before a case manifest was recorded. '+str(manifest.get('error',''))
        (dest/'longride.json').write_bytes((paired/'longride.json').read_bytes())
        (dest/'comparison.json').write_text(json.dumps(canonical,allow_nan=False))
        meta=metadata_for(root,paired)
        meta.update({'experiment':'continuous-long-ride-v1','training_run_id':training_id,'notes':meta.get('notes','')+' Display dates describe the batch execution. Original longride.json and unchanged full-rate case files are archived. Fully learned means the declared measured tested grid only; RAM fixture import does not test flash persistence.'})
        if key:meta.update({'experiment_duration_min':minutes,'initial_state':state})
        (dest/'run-metadata.json').write_text(json.dumps(meta));sources.append(dest)
    return sources
