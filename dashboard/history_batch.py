#!/usr/bin/env python3
"""Bounded official release matrix; never change firmware/controller sources."""
import json,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MATRIX=[('26.8.23','candidate-26.8.23','2026-08-23T16:15:26Z'),('26.9.15','candidate-26.9.15','2026-09-15T17:44:08Z'),('26.10.1','baseline','2026-10-01T20:47:58Z'),('782c2b5','candidate-current',None)]
ADAPTER='098a900211f1803e2723634325061b6185b1d5e2fb20e13e8698d42097910f32'
def main():
    codes=[]
    for label,candidate,published in MATRIX:
        output=Path('output')/label
        cmd=[sys.executable,str(ROOT/'experiment.py'),'--firmware-root','adapter','--baseline-root','baseline','--candidate-root',candidate,'--output',str(output),'--adapter-sha256',ADAPTER,'--adapter-patch',str(ROOT/'compatibility/history-adapter.patch'),'--simulator-root','engine']
        cmd+=['--candidate-ref',label if published else 'erg-spike-gate']
        if published:cmd+=['--release-tag',label,'--release-published-at',published]
        code=subprocess.call(cmd);codes.append(code)
        manifest=output/'comparison.json'
        if manifest.exists() and json.loads(manifest.read_text()).get('status')=='complete':
            audit=subprocess.call([sys.executable,str(ROOT/'audit_history.py'),'--adapter','adapter','--candidate',candidate,'--build',str(output/'candidate/build'),'--label',label,'--output',str(output/'production-source-audit.json')])
            if audit:
                data=json.loads(manifest.read_text());data['status']='failed';data['passed']=False;data['error']='Production-source audit failed. Do not interpret this run as faithful release evidence.';manifest.write_text(json.dumps(data,indent=2));codes.append(2)
        # Include the reviewed adapter provenance beside each raw run.
        output.mkdir(parents=True,exist_ok=True)
        provenance=json.loads((ROOT/'compatibility/provenance.json').read_text())
        if 'toolchain' in provenance: provenance['original_validation_toolchain']=provenance.pop('toolchain')
        provenance['runtime_toolchain_location']='run-metadata.json:runtime_toolchain'
        provenance['initial_state_audit_scope']='Original local four-revision validation, not a newly repeated cloud audit'
        (output/'adapter-provenance.json').write_text(json.dumps(provenance,indent=2))
        (output/'initial-state-audit.json').write_bytes((ROOT/'compatibility/initial-state-audit.json').read_bytes())
    return max(codes,default=2)
if __name__=='__main__':sys.exit(main())
