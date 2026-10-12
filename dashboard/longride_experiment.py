#!/usr/bin/env python3
"""Run the bounded training + paired long-ride matrix and record provenance."""
import datetime,hashlib,json,platform,subprocess,sys
from pathlib import Path
import numpy

ROOT=Path(__file__).resolve().parent.parent
PIN='b776105cd1e3edb93a91bada3f27aaecc25533dc'
CASES=[{'minutes':m,'initial_state':s,'seed':27} for m in (30,60,90) for s in ('empty','partial','full')]
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
def main():
    output=Path('output');output.mkdir(exist_ok=True)
    if sha('adapter')!=PIN or sha('candidate')!=PIN:raise ValueError('Unexpected adapter/candidate commit')
    meta={'run_started_at':now(),'simulator_commit':sha(ROOT),'adapter_commit':sha('adapter'),'candidate_ref':'erg-spike-gate','baseline_release_tag':'26.10.1','baseline_release_published_at':'2026-10-01T20:47:58Z','runtime_toolchain':{'python':platform.python_version(),'numpy':numpy.__version__},'notes':'One seed27;30/60/90minutes; empty,partial,fully supporteddeclared measured tested grid. One native process per ride, paired identical earned starting fixtures. Includes12s sensor outage and60s actual cadence-zero rider pause outside probes. Training and testing use separate declared seeds; no physical hardware or flash-persistence validation. Whole-ride scores include the pedaling pause; requested power is unattainable at zero cadence.'}
    for cc in ('g++','gcc'):meta['runtime_toolchain'][cc]=subprocess.check_output([cc,'--version'],text=True).splitlines()[0]
    common=[sys.executable,'-m','ss2k_sim.longride']
    args=['--firmware-root','adapter','--candidate-root','candidate']
    code=2
    try:
        train_meta={**meta,'run_started_at':now(),'notes':meta['notes']+' This record is shared fixture-training evidence.'}
        training=subprocess.call(common+['train',*args,'--output',str(output/'training')])
        train_meta['run_completed_at']=now();(output/'training').mkdir(exist_ok=True);(output/'training/run-metadata.json').write_text(json.dumps(train_meta,indent=2))
        if training or not (output/'training/full.json').is_file():
            (output/'paired').mkdir(exist_ok=True)
            (output/'paired/longride.json').write_text(json.dumps({'status':'failed','experiment':'continuous-long-ride-v1','runs':[],'requested_cases':CASES,'error':'Training did not produce a verified fully supported tested-range fixture; comparison was not fabricated.'}))
            code=2
        else:
            meta['run_started_at']=now()
            code=subprocess.call(common+['compare',*args,'--baseline-root','baseline','--fixtures',str(output/'training'),'--output',str(output/'paired'),'--minutes','30','60','90','--states','empty','partial','full','--seeds','27','--stress'])
    finally:
        meta['run_completed_at']=now();meta['exit_code']=code
        (output/'run-metadata.json').write_text(json.dumps(meta,indent=2))
        (output/'paired').mkdir(exist_ok=True)
        (output/'paired/run-metadata.json').write_text(json.dumps(meta,indent=2))
    return code
if __name__=='__main__':sys.exit(main())
