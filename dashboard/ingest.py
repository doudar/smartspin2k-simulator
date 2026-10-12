#!/usr/bin/env python3
"""Workflow-event ingestion. Inputs affect data only, never a code checkout."""
import argparse, datetime, json, os
from pathlib import Path
from build import build, materialize, read_json, valid_tree

def main():
    p=argparse.ArgumentParser();p.add_argument('--history',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--input',type=Path,required=True);a=p.parse_args()
    if os.getenv('EVENT_NAME')=='workflow_run':
        run_id=os.environ['SOURCE_RUN_ID'];attempt=os.environ['SOURCE_ATTEMPT']
        if not run_id.isdigit() or not attempt.isdigit(): raise ValueError('Invalid workflow identity')
        identity=f'actions-{run_id}-{attempt}'
        if not (a.history/identity).exists():
            a.input.mkdir(parents=True,exist_ok=True)
            # One artifact may hold a bounded release matrix; each release gets its own immutable ID.
            children=[p for p in a.input.iterdir() if p.is_dir() and (p/'comparison.json').is_file()]
            sources=children if children and not (a.input/'comparison.json').exists() else [a.input]
            if len(sources)>10: raise ValueError('Historical batch too large')
            for source in sources:
                rid=identity+('-'+source.name if source!=a.input else '')
                if (a.history/rid).exists(): continue
                metadata=read_json(source/'run-metadata.json') if (source/'run-metadata.json').exists() else {}
                valid_tree(metadata)
                if not isinstance(metadata,dict): metadata={'notes':'Producer metadata was not an object and was discarded.'}
                metadata.update({'workflow_url':f'https://github.com/doudar/smartspin2k-simulator/actions/runs/{run_id}', 'workflow_conclusion':os.getenv('SOURCE_CONCLUSION'),'workflow_updated_at':os.getenv('SOURCE_DATE'),'imported_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
                try: materialize(source,a.history/rid,rid,metadata)
                except (ValueError,KeyError,TypeError,json.JSONDecodeError,UnicodeError) as e:
                    # Publish rejected/incomplete runs, but do not expose unsafe payloads.
                    safe=a.input.parent/('rejected-'+rid);safe.mkdir(exist_ok=True)
                    (safe/'comparison.json').write_text(json.dumps({'status':'incomplete','passed':False,'runs':[],'error':f'Evidence validation rejected this payload: {type(e).__name__}. Raw payload was not published.'}))
                    materialize(safe,a.history/rid,rid,{'workflow_url':metadata['workflow_url'],'imported_at':metadata['imported_at'],'notes':'Original artifact remains available in Actions subject to retention.'})
    build(a.history,a.output)
if __name__=='__main__':main()
