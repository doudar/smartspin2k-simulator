"""Trusted adapter for long-ride DATA, never an experiment-code import.

Split large batches into bounded per-case archives; preserve original file names
and the original full manifest. Training evidence is archived once and linked.
"""
import json,shutil
from pathlib import Path
from build import ALLOWED,MAX_FILE,MAX_RUN,SAFE,LONG_RIDE_EXPERIMENTS,read_json,valid_tree,validate_metadata

STATES={'empty':'empty','partial':'partially learned','full':'fully learned tested range'}
SPRINT_EXPERIMENT='continuous-long-ride-sprints-v2'

def case_checks(row,experiment):
    """Every scored interval and both signals must contribute to the result."""
    checks=[row,row.get('reported_power_comparison',{})]
    for field,label in [('window_comparisons','probe')]+([('sprint_comparisons','sprint')] if experiment==SPRINT_EXPERIMENT else []):
        intervals=row.get(field,{})
        if not isinstance(intervals,dict) or set(intervals)!=set(('early','middle','late')):raise ValueError(f'Incomplete {label} decisions')
        for interval in intervals.values():
            if not isinstance(interval,dict):raise ValueError(f'Invalid {label} decision')
            checks.extend((interval,interval.get('reported_power_comparison',{})))
    return checks

def copy_inert(source,dest):
    if source.is_symlink() or any(parent.is_symlink() for parent in source.parents):raise ValueError('Symlink long-ride root')
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

def checked_case(row,experiment):
    if not isinstance(row,dict) or row.get('minutes') not in (30,60,90) or row.get('initial_state') not in STATES or type(row.get('seed')) is not int:
        raise ValueError('Invalid long-ride case')
    if experiment==SPRINT_EXPERIMENT:
        if row['minutes']!=90 or row['initial_state'] not in ('empty','full') or type(row.get('sensitivity')) is not int or row['sensitivity'] not in (3,5,10):raise ValueError('Invalid sprint ride sensitivity matrix')
        return row['minutes'],row['initial_state'],row['seed'],row['sensitivity']
    return row['minutes'],row['initial_state'],row['seed']

def metadata_for(root,source):
    file=source/'run-metadata.json'
    fallback=root/'run-metadata.json'
    value=read_json(file) if file.exists() or file.is_symlink() else read_json(fallback) if fallback.exists() or fallback.is_symlink() else {}
    return validate_metadata(value)

def prepare(root,stage,identity,*,missing_cases=None):
    """Return canonical evidence directories, retaining partial/missing cases."""
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):raise ValueError('Symlink long-ride root')
    paired=root/'paired' if (root/'paired').is_dir() else root
    manifest_path=paired/'longride.json'
    missing_manifest=False
    if not manifest_path.exists() and not manifest_path.is_symlink():
        if missing_cases is None:return None
        missing_manifest=True
        manifest={'manifest_source':'ingestion-placeholder','status':'incomplete','experiment':SPRINT_EXPERIMENT,'runs':[],'requested_cases':missing_cases,'error':'No longride.json produced; inspect workflow log.'}
        manifest_bytes=json.dumps(manifest,allow_nan=False).encode()
    else:
        manifest=read_json(manifest_path)
        manifest_bytes=manifest_path.read_bytes()
    valid_tree(manifest)
    if not isinstance(manifest,dict) or manifest.get('experiment') not in LONG_RIDE_EXPERIMENTS:raise ValueError('Unknown long-ride manifest')
    experiment=manifest['experiment'];has_sprints=experiment==SPRINT_EXPERIMENT
    if not isinstance(manifest.get('initial_fixtures',{}),dict):raise ValueError('Invalid fixture manifest')
    rows=manifest.get('runs',[])
    if not isinstance(rows,list) or len(rows)>27:raise ValueError('Long-ride batch too large')
    recorded={}
    for row in rows:
        key=checked_case(row,experiment)
        checks=case_checks(row,experiment)
        for check in checks:
            if not isinstance(check,dict) or any(type(check.get(flag)) is not bool for flag in ('absolute_passed','relative_passed')):raise ValueError('Unmeasured long-ride decision')
            if not isinstance(check.get('failures',[]),list) or any(not isinstance(f,str) for f in check.get('failures',[])):raise ValueError('Invalid probe failures')
        if key in recorded:raise ValueError('Duplicate long-ride case')
        recorded[key]=row
    requested=manifest.get('requested_cases') or [dict(minutes=k[0],initial_state=k[1],seed=k[2],**({'sensitivity':k[3]} if has_sprints else {})) for k in recorded]
    if not isinstance(requested,list) or len(requested)>27:raise ValueError('Requested matrix too large')
    cases=[checked_case(r,experiment) for r in requested]
    if len(cases)!=len(set(cases)):raise ValueError('Duplicate requested case')
    if not cases:cases=[None] # Preserve an early batch failure instead of hiding it.
    sources=[];training_id=None
    training=root/'training'
    if (training/'longride.json').is_file():
        tm=read_json(training/'longride.json');valid_tree(tm)
        if not isinstance(tm,dict):raise ValueError('Invalid training manifest')
        dest=stage/'training';copy_inert(training,dest)
        if tm.get('experiment')!=experiment:raise ValueError('Training and paired experiment versions differ')
        canonical={**tm,'runs':[],'experiment':'long-ride-training-sprints-v2' if has_sprints else 'long-ride-training-v1'}
        (dest/'comparison.json').write_text(json.dumps(canonical,allow_nan=False))
        meta=metadata_for(root,training);meta.update({'evidence_only':True,'notes':(meta.get('notes') or '')+' Shared original production-learning training evidence. Not a paired acceptance run.'})
        (dest/'run-metadata.json').write_text(json.dumps(meta));sources.append(dest)
        training_id=identity+'-training'
    for key in cases:
        if key is None:
            name='long-incomplete';row=None
        else:
            minutes,state,seed=key[:3];sensitivity=key[3] if has_sprints else None
            name=f'long-{minutes}m-{state}'+(f'-sensitivity{sensitivity}' if has_sprints else '')+f'-{seed}';row=recorded.get(key)
        dest=stage/name;dest.mkdir(parents=True,exist_ok=True)
        canonical={k:v for k,v in manifest.items() if k not in ('runs','initial_fixtures','training')}
        canonical['batch_status']=manifest.get('status','incomplete')
        canonical['coverage_level']='Continuous production packet/controller simulation with one native process per ride; no radio, ESP32 scheduler or physical hardware'
        canonical['budget_status']='Provisional engineering bands, including early/middle/late probes'+(' and all three sprint blocks' if has_sprints else '')+'; not hardware fidelity proof'
        canonical['runs']=[];canonical['status']='incomplete';canonical['passed']=False
        if key:
            artifact_key=f'long_{minutes}m_{state}'+(f'_sensitivity{sensitivity}' if has_sprints else '')+f'-{seed}'
            for variant in ('baseline','candidate'):
                copy_inert(paired/variant/artifact_key,dest/variant/artifact_key)
            fixture=manifest.get('initial_fixtures',{}).get(state)
            (dest/'initial-fixture.json').write_text(json.dumps(fixture,allow_nan=False))
            if row is not None:
                checks=case_checks(row,experiment)
                overall={name:all(check.get(name) is True for check in checks) for name in ('absolute_passed','relative_passed')}
                overall['passed']=overall['absolute_passed'] and overall['relative_passed']
                canonical['runs']=[{**row,'scenario':'long_ride','artifact_key':artifact_key,'overall_checks':overall,'overall_checks_scope':'Whole ride plus early/middle/late probes'+(' and all three sprint blocks' if has_sprints else '')+', both plant and delivered-sensor signals'}]
                canonical['status']='complete';canonical['passed']=overall['passed']
            else:canonical['error']='This requested case did not complete. Partial files, if produced, remain in the raw archive. '+str(manifest.get('error',''))
        else:canonical['error']='Long-ride batch failed before a case manifest was recorded. '+str(manifest.get('error',''))
        (dest/'longride.json').write_bytes(manifest_bytes)
        (dest/'comparison.json').write_text(json.dumps(canonical,allow_nan=False))
        meta=metadata_for(root,paired)
        evidence_note=' No producer longride.json was available; archived manifest explicitly records unexecuted requested-case placeholders.' if missing_manifest else ' Display dates describe the batch execution. Original longride.json and unchanged full-rate case files are archived.'
        meta.update({'experiment':experiment,'training_run_id':training_id,'notes':(meta.get('notes') or '')+evidence_note+' Fully learned means the declared measured tested grid only; RAM fixture import does not test flash persistence.'})
        if key:meta.update({'experiment_duration_min':minutes,'initial_state':state})
        if key and has_sprints:meta['sensitivity']=sensitivity
        (dest/'run-metadata.json').write_text(json.dumps(meta));sources.append(dest)
    return sources
