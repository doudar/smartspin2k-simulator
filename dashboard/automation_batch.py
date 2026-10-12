#!/usr/bin/env python3
"""One immutable revision, full short and six-long-ride coverage, no fail-fast."""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--revision',required=True);p.add_argument('--suite',choices=('short','long','both'),default='both');p.add_argument('--output',type=Path,default=Path('output'));p.add_argument('--fixtures',type=Path,default=Path('fixtures'));a=p.parse_args()
    plan=json.loads(a.plan.read_text());version=next(v for v in plan['versions'] if v['id']==a.revision)
    output=a.output/version['id'];output.mkdir(parents=True,exist_ok=True)
    pin=output.resolve()/'baseline-selection.json';pin.write_text(json.dumps(plan['baseline_selection']));os.environ['SS2K_BASELINE_SELECTION']=str(pin)
    common=['--firmware-root','adapter','--baseline-root','baseline','--candidate-root','candidate','--candidate-ref',version['ref']]
    if version.get('tag'):common+=['--release-tag',version['tag'],'--release-published-at',version['published_at']]
    codes={}
    if a.suite in ('short','both'):
        codes['short']=subprocess.call([sys.executable,str(ROOT/'experiment.py'),*common,'--output',str(output/'short'),'--adapter-patch',str(ROOT/'compatibility/history-adapter.patch')])
    if a.suite in ('long','both'):
        codes['long']=subprocess.call([sys.executable,str(ROOT/'longride_experiment.py'),*common,'--output',str(output/'long'),'--fixtures',str(a.fixtures),'--adapter-patch',str(ROOT/'compatibility/history-adapter.patch')])
        if a.fixtures.is_dir():shutil.copytree(a.fixtures,output/'long'/'training',dirs_exist_ok=True)
    # Audit both compiled production sources before discarding compilation trees.
    for suite,relative,manifest in [('short','short','comparison.json'),('long','long/paired','longride.json')]:
        if suite not in codes:continue
        target=output/relative
        for variant in ('candidate','baseline'):
            build=target/variant/'build'
            if not build.is_dir():continue
            audit=subprocess.call([sys.executable,str(ROOT/'audit_history.py'),'--adapter','adapter','--candidate',variant,'--build',str(build),'--label',variant,'--output',str(target/(variant+'-production-source-audit.json'))])
            if audit:
                codes[suite]=2
                f=target/manifest
                if f.is_file():
                    value=json.loads(f.read_text());value.update(status='failed',passed=False,error='Compiled production-source audit failed; do not interpret as faithful firmware evidence.');f.write_text(json.dumps(value))
    # Never cache executables or compilation trees. All cached payloads are data.
    for build in list(output.rglob('build')):
        if build.is_dir() and not build.is_symlink():shutil.rmtree(build)
    (output/'batch-result.json').write_text(json.dumps({'exit_codes':codes,'candidate_commit':version['commit'],'suite':a.suite,'source_run_id':os.getenv('GITHUB_RUN_ID'),'source_attempt':os.getenv('GITHUB_RUN_ATTEMPT')}))
    return max(codes.values(),default=2)
if __name__=='__main__':raise SystemExit(main())
