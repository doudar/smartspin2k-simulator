#!/usr/bin/env python3
"""Workflow-event ingestion. Inputs affect data only, never a code checkout."""
import argparse, datetime, hashlib, json, os, tempfile
from pathlib import Path
from build import SAFE, build, materialize, read_json, valid_tree

def main():
    p=argparse.ArgumentParser();p.add_argument('--history',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--input',type=Path,required=True);a=p.parse_args()
    if os.getenv('EVENT_NAME')=='workflow_run':
        run_id=os.environ['SOURCE_RUN_ID'];attempt=os.environ['SOURCE_ATTEMPT']
        if not run_id.isdigit() or not attempt.isdigit(): raise ValueError('Invalid workflow identity')
        identity=f'actions-{run_id}-{attempt}'
        if not (a.history/identity).exists():
            a.input.mkdir(parents=True,exist_ok=True)
            from longride_import import prepare
            stage=Path(tempfile.mkdtemp(prefix='longride-evidence-'))
            try: prepared=prepare(a.input,stage,identity)
            except (ValueError,KeyError,TypeError,json.JSONDecodeError,UnicodeError,OSError):
                rejected=stage/'longride-rejected';rejected.mkdir()
                (rejected/'comparison.json').write_text(json.dumps({'status':'incomplete','passed':False,'runs':[],'error':'Long-ride batch validation failed. Unsafe payload was not published; inspect the Actions artifact.'}))
                prepared=[rejected]
            # One artifact may hold a bounded release matrix; each release gets its own immutable ID.
            children=[p for p in a.input.iterdir() if p.is_dir() and ((p/'comparison.json').is_file() or (p/'run-metadata.json').is_file())]
            sources=prepared if prepared is not None else children if children and not (a.input/'comparison.json').exists() else [a.input]
            if len(sources)>28: raise ValueError('Experiment batch too large')
            for source in sources:
                suffix=source.name if SAFE.fullmatch(source.name) else hashlib.sha256(source.name.encode()).hexdigest()[:12]
                rid=identity+('-'+suffix if source!=a.input else '')
                if (a.history/rid).exists(): continue
                base_metadata={'workflow_url':f'https://github.com/doudar/smartspin2k-simulator/actions/runs/{run_id}', 'workflow_conclusion':os.getenv('SOURCE_CONCLUSION'),'workflow_updated_at':os.getenv('SOURCE_DATE'),'imported_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
                try:
                    metadata=read_json(source/'run-metadata.json') if (source/'run-metadata.json').exists() else {}
                    valid_tree(metadata)
                    if not isinstance(metadata,dict): raise ValueError('Producer metadata must be an object')
                    metadata.update(base_metadata)
                    if (source/'adapter-provenance.json').exists() and not metadata.get('runtime_toolchain'):
                        metadata['notes']=metadata.get('notes','')+' Runtime toolchain was not recorded for this cloud run. Any toolchain in adapter-provenance.json describes original local validation only; the initial-state audit is linked from the repository compatibility directory.'
                    materialize(source,a.history/rid,rid,metadata)
                except (ValueError,KeyError,TypeError,json.JSONDecodeError,UnicodeError,OSError) as e:
                    # Publish rejected/incomplete runs, but do not expose unsafe payloads.
                    safe=a.input.parent/('rejected-'+rid);safe.mkdir(exist_ok=True)
                    (safe/'comparison.json').write_text(json.dumps({'status':'incomplete','passed':False,'runs':[],'error':f'Evidence validation rejected this payload: {type(e).__name__}. Raw payload was not published.'}))
                    base_metadata['notes']='Original artifact remains available in Actions subject to retention.'
                    materialize(safe,a.history/rid,rid,base_metadata)
    build(a.history,a.output)
if __name__=='__main__':main()
