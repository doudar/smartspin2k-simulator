#!/usr/bin/env python3
"""Run the bounded training + paired long-ride matrix and record provenance."""
import argparse,datetime,hashlib,json,platform,subprocess,sys
from pathlib import Path
import numpy
from ss2k_sim import baseline

ROOT=Path(__file__).resolve().parent.parent
CASES=[{'minutes':m,'initial_state':s,'seed':7,'sensitivity':sensitivity} for m in (90,) for s in ('empty','full') for sensitivity in (3,5,10)]
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--firmware-root',type=Path,default=Path('adapter'))
    p.add_argument('--candidate-root',type=Path,default=Path('candidate'))
    p.add_argument('--baseline-root',type=Path,default=Path('baseline'))
    p.add_argument('--output',type=Path,default=Path('output'))
    p.add_argument('--adapter-patch',type=Path)
    p.add_argument('--fixtures',type=Path,help='Reuse verified shared training fixtures')
    p.add_argument('--candidate-ref',default='erg-spike-gate')
    p.add_argument('--release-tag');p.add_argument('--release-published-at')
    baseline.arguments(p)
    return p


def main(argv=None):
    a=parser().parse_args(argv)
    output=a.output
    if output.exists() and any(output.iterdir()): raise FileExistsError('Output must be new/empty')
    selection=baseline.select(a)
    # Freeze before training so branch motion cannot change this matrix.
    with baseline.pinned_root(a.baseline_root, selection) as root:
        a.baseline_root=root
        output.mkdir(parents=True,exist_ok=True)
        pin=output.resolve()/'baseline-selection.json'
        pin.write_text(json.dumps(selection,indent=2)+'\n')
        import os
        old=os.environ.get(baseline.ENV)
        os.environ[baseline.ENV]=str(pin)
        try:
            return execute(a, selection)
        finally:
            if old is None: os.environ.pop(baseline.ENV,None)
            else: os.environ[baseline.ENV]=old


def execute(a, selection):
    output=a.output
    meta={'run_started_at':now(),'simulator_commit':sha(ROOT),'adapter_commit':sha(a.firmware_root),'candidate_commit':sha(a.candidate_root),'candidate_ref':a.candidate_ref,'release_tag':a.release_tag,'release_published_at':a.release_published_at,'baseline_selection':selection,'runtime_toolchain':{'python':platform.python_version(),'numpy':numpy.__version__},'notes':'Fixed seed 7; 90 minutes; empty or fully supported 45-cell declared production-learned grid; ERG sensitivity 3/5/10. Three identical 100W30s / 500W25s / 100W30s blocks at85rpm, separately scored. One native process per ride, paired identical earned starting fixtures. Includes 12s sensor outage and 60s actual cadence-zero rider pause outside probes. Training and testing both use seed 7; this is single-seed repeatability coverage; no physical hardware or flash-persistence validation. Whole-ride scores include the pedaling pause; requested power is unattainable at zero cadence.'}
    if a.adapter_patch: meta['adapter_patch_sha256']=hashlib.sha256(a.adapter_patch.read_bytes()).hexdigest()
    for cc in ('g++','gcc'):meta['runtime_toolchain'][cc]=subprocess.check_output([cc,'--version'],text=True).splitlines()[0]
    common=[sys.executable,'-m','ss2k_sim.longride']
    args=['--firmware-root',str(a.firmware_root),'--candidate-root',str(a.candidate_root)]
    fixtures=a.fixtures or output/'training'
    meta['shared_fixture_source']=str(fixtures.resolve())
    code=2
    try:
        train_meta={**meta,'run_started_at':now(),'notes':meta['notes']+' This record is shared fixture-training evidence.'}
        training=0
        if a.fixtures is None:
            training=subprocess.call(common+['train',*args,'--output',str(fixtures)])
            train_meta['run_completed_at']=now();fixtures.mkdir(exist_ok=True);(fixtures/'run-metadata.json').write_text(json.dumps(train_meta,indent=2))
        if training or not (fixtures/'full.json').is_file():
            (output/'paired').mkdir(exist_ok=True)
            (output/'paired/longride.json').write_text(json.dumps({'status':'failed','experiment':'continuous-long-ride-sprints-v2','runs':[],'requested_cases':CASES,'error':'Training did not produce a verified fully supported tested-range fixture; comparison was not fabricated.'}))
            code=2
        else:
            meta['run_started_at']=now()
            code=subprocess.call(common+['compare',*args,'--baseline-root',str(a.baseline_root),'--fixtures',str(fixtures),'--output',str(output/'paired'),'--minutes','90','--states','empty','full','--sensitivities','3','5','10','--seeds','7','--stress'])
    finally:
        meta['run_completed_at']=now();meta['exit_code']=code
        (output/'run-metadata.json').write_text(json.dumps(meta,indent=2))
        (output/'paired').mkdir(exist_ok=True)
        (output/'paired/run-metadata.json').write_text(json.dumps(meta,indent=2))
    return code
if __name__=='__main__':sys.exit(main())
