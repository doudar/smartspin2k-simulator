#!/usr/bin/env python3
"""Bounded official release matrix; never change firmware/controller sources."""
import json,subprocess,sys
from pathlib import Path
from ss2k_sim import baseline, releases

ROOT=Path(__file__).resolve().parent

ADAPTER=json.loads((ROOT/'compatibility/longride-adapter-provenance.json').read_text())['compatible_adapter_fingerprint']
def main():
    selection=baseline.establish(Path('output')/'baseline-selection.json')
    release_file=Path('release-selection.json')
    resolved=releases.validate(json.loads(release_file.read_text())) if release_file.exists() else releases.resolve_releases()
    release_file.write_text(json.dumps(resolved,indent=2)+'\n')
    codes=[]
    for item in resolved['releases']:
        label,candidate,published=item['tag'],'candidate-'+item['commit'][:12],item['published_at']
        if not Path(candidate).exists():
            subprocess.run(['git','clone','--no-checkout',resolved['repository'],candidate],check=True)
        subprocess.run(['git','-C',candidate,'checkout','--detach',item['commit']],check=True)
        output=Path('output')/label
        cmd=[sys.executable,str(ROOT/'experiment.py'),'--firmware-root','adapter','--baseline-root','baseline','--candidate-root',candidate,'--output',str(output),'--adapter-sha256',ADAPTER,'--adapter-patch',str(ROOT/'compatibility/history-adapter.patch')]
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
        provenance=json.loads((ROOT/'compatibility/longride-adapter-provenance.json').read_text())
        if 'toolchain' in provenance: provenance['original_validation_toolchain']=provenance.pop('toolchain')
        provenance['runtime_toolchain_location']='run-metadata.json:runtime_toolchain'
        provenance['initial_state_audit_scope']='Original compatibility smoke validation; fresh production-source audit is separate'
        (output/'adapter-provenance.json').write_text(json.dumps(provenance,indent=2))
        (output/'initial-state-audit.json').write_bytes((ROOT/'compatibility/initial-state-audit.json').read_bytes())
    return max(codes,default=2)
if __name__=='__main__':sys.exit(main())
