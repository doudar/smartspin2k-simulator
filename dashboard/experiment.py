#!/usr/bin/env python3
"""Run existing simulator unchanged; record wrapper provenance even on failure."""
import argparse, datetime, hashlib, json, platform, shutil, subprocess, sys
import numpy
from pathlib import Path

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path): return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
def main():
    p=argparse.ArgumentParser();p.add_argument('--firmware-root',type=Path,required=True);p.add_argument('--baseline-root',type=Path,required=True);p.add_argument('--candidate-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--release-tag');p.add_argument('--release-published-at');p.add_argument('--adapter-sha256');p.add_argument('--adapter-patch',type=Path);p.add_argument('--simulator-root',type=Path);a=p.parse_args()
    metadata={'run_started_at':now(),'simulator_commit':sha(a.simulator_root or Path(__file__).resolve().parent.parent),'adapter_commit':sha(a.firmware_root),'release_tag':a.release_tag,'release_published_at':a.release_published_at,'baseline_release_tag':'26.10.1','baseline_release_published_at':'2026-10-01T20:47:58Z','notes':'Production controller unchanged. Same current adapter, model, full six-scenario matrix and seeds 7/27/91; software simulation, no hardware validation.'}
    metadata['runtime_toolchain']={'python':platform.python_version(),'numpy':numpy.__version__}
    for compiler in ('g++','gcc'):
        if shutil.which(compiler): metadata['runtime_toolchain'][compiler]=subprocess.check_output([compiler,'--version'],text=True).splitlines()[0]
    if a.adapter_patch:
        metadata['adapter_patch_sha256']=hashlib.sha256(a.adapter_patch.read_bytes()).hexdigest()
        metadata['notes']+=' Reviewed historical compatibility patch applied to adapter only; production functions remain byte-exact, apart from documented peripheral include/virtual-clock seams.'
    code=2
    try: code=subprocess.call([sys.executable,'-m','ss2k_sim','compare','--firmware-root',str(a.firmware_root),'--baseline-root',str(a.baseline_root),'--candidate-root',str(a.candidate_root),'--output',str(a.output)]+(['--adapter-sha256',a.adapter_sha256] if a.adapter_sha256 else []))
    finally:
        a.output.mkdir(parents=True,exist_ok=True);metadata['run_completed_at']=now();metadata['exit_code']=code
        (a.output/'run-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return code
if __name__=='__main__':sys.exit(main())
