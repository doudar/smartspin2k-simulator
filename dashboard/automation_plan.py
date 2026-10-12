#!/usr/bin/env python3
"""Validate relay requests and freeze every revision before any firmware executes."""
import argparse, datetime, hashlib, json, os, re, subprocess, urllib.request, urllib.parse
from pathlib import Path
from ss2k_sim import baseline, releases

REPOSITORY='doudar/SmartSpin2k'
HEX=re.compile(r'[0-9a-f]{40}')
REQUEST=re.compile(r'requests/pr-([1-9][0-9]*)/([0-9a-f]{40})\.json')

def api(path):
    headers={'Accept':'application/vnd.github+json','User-Agent':'SmartSpin2k-simulator'}
    if os.getenv('GITHUB_TOKEN'): headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
    with urllib.request.urlopen(urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+'/'+path,headers=headers),timeout=30) as response:return json.load(response)

def validate_request(path, value, fetch=api):
    match=REQUEST.fullmatch(path)
    if not match or not isinstance(value,dict) or set(value)!={'schema_version','repository','pull_request','head_sha'}:raise ValueError('Invalid relay request schema/path')
    if type(value['schema_version']) is not int or value['schema_version']!=1 or value['repository']!=REPOSITORY or type(value['pull_request']) is not int or value['pull_request']!=int(match[1]) or value['head_sha']!=match[2]:raise ValueError('Relay request identity mismatch')
    pr=fetch('pulls/'+str(value['pull_request']))
    if pr.get('state')!='open' or pr.get('base',{}).get('repo',{}).get('full_name')!=REPOSITORY or pr.get('head',{}).get('sha')!=value['head_sha']:raise ValueError('PR is closed, stale, or targets another repository')
    # Successful PR workflow names are mutable by the PR itself and cannot
    # establish maintainer approval. Fail closed; use explicit workflow_dispatch.
    if pr.get('head',{}).get('repo',{}).get('full_name')!=REPOSITORY:
        raise ValueError('Fork PR requires explicit maintainer workflow_dispatch of this exact head SHA; the relay never approves or executes forks automatically')
    return {'commit':value['head_sha'],'ref':'refs/pull/'+str(value['pull_request'])+'/head','pull_request':value['pull_request'],'repository':REPOSITORY}

def code_fingerprint(root):
    h=hashlib.sha256()
    for folder in ('ss2k_sim','dashboard/compatibility','profiles'):
        for p in sorted((root/folder).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:h.update(str(p.relative_to(root)).encode()+b'\0'+p.read_bytes()+b'\0')
    for name in ('dashboard/experiment.py','dashboard/longride_experiment.py','dashboard/automation_batch.py','dashboard/sanitize_evidence.py','ci/Dockerfile','ci/run-isolated.sh','pyproject.toml'):
        p=root/name;h.update(name.encode()+b'\0'+p.read_bytes()+b'\0')
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('experiment-plan.json'));p.add_argument('--request');p.add_argument('--candidate-ref',default='erg-spike-gate');p.add_argument('--suite',choices=('short','long','both'),default='both');p.add_argument('--github-output',action='store_true');a=p.parse_args()
    root=Path(__file__).resolve().parent.parent
    if a.request:candidate=validate_request(a.request,json.loads((root/a.request).read_text()))
    else:
        item=api('commits/'+urllib.parse.quote(a.candidate_ref,safe=''))
        candidate={'commit':item['sha'],'ref':a.candidate_ref,'repository':REPOSITORY}
    if not HEX.fullmatch(candidate['commit']):raise ValueError('Invalid candidate SHA')
    selected_baseline=baseline.resolve()
    selected_releases=releases.resolve_releases(count=3)
    versions=[{'id':'candidate-'+candidate['commit'][:12],**candidate}]
    seen={candidate['commit']}
    for item in selected_releases['releases']:
        if item['commit'] not in seen:
            versions.append({'id':'release-'+item['commit'][:12],'ref':item['tag'],**item});seen.add(item['commit'])
    plan={'schema_version':1,'suite':a.suite,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate':candidate,'baseline_selection':selected_baseline,'release_selection':selected_releases,'versions':versions,'engine_sha256':code_fingerprint(root),'matrix':{'short_seeds':[7],'minutes':[90],'states':['empty','full'],'sensitivities':[3,5,10],'long_seeds':[7],'stress':True},'fixture_policy':'Shared production-learned fixture trained once on resolved develop; identical across all revisions.'}
    a.output.write_text(json.dumps(plan,indent=2)+'\n')
    if a.github_output:
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:
            f.write('baseline='+selected_baseline['commit']+'\n')
            f.write('matrix='+json.dumps({'include':versions},separators=(',',':'))+'\n')
            f.write('engine='+plan['engine_sha256']+'\n')
    return 0
if __name__=='__main__':raise SystemExit(main())
