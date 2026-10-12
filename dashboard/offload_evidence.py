#!/usr/bin/env python3
"""Publish NEW validated evidence archives as append-only public Release assets.

Runs only in the trusted publisher job. Never executes any artifact content.
Existing immutable Pages records are untouched. Remove a local ZIP only after
GitHub confirms the uploaded SHA-256, byte count, state, and exact public URL.
"""
import argparse,hashlib,json,os,re,shutil,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from build import SAFE,read_json,valid_tree,MOTOR_RENDERER,CADENCE_RENDERER,validate_display,validate_evidence_location

REPOSITORY='doudar/smartspin2k-simulator'
API='https://api.github.com/repos/'+REPOSITORY
MAX_SITE=900_000_000

class GitHub:
    def __init__(self,token):self.token=token
    def call(self,path,method='GET',payload=None,raw=None):
        url=API+path if not path or path.startswith('/') else path
        if not (url==API or url.startswith(API+'/') or url.startswith('https://uploads.github.com/repos/'+REPOSITORY+'/releases/')):raise ValueError('Unexpected API destination')
        body=raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'SmartSpin2k-evidence-publisher'}
        if body is not None:headers['Content-Type']='application/zip' if raw is not None else 'application/json'
        request=urllib.request.Request(url,data=body,headers=headers,method=method)
        with urllib.request.urlopen(request,timeout=180) as response:return json.load(response)
    def release(self,tag,commit):
        try:result=self.call('/releases/tags/'+tag)
        except urllib.error.HTTPError as exc:
            if exc.code!=404:raise
            result=self.call('/releases','POST',{'tag_name':tag,'target_commitish':commit,'name':'Simulator evidence '+tag,'body':'Public raw simulator evidence, with SHA-256 verified before dashboard publication. Append-only archive; not a firmware release.','draft':False,'prerelease':True,'make_latest':'false'})
        if result.get('tag_name')!=tag or result.get('draft') is not False or type(result.get('id')) is not int:raise ValueError('Unexpected release identity')
        return result
    def assets(self,release_id):
        result=[]
        for page in range(1,12):
            rows=self.call(f'/releases/{release_id}/assets?per_page=100&page={page}')
            if not isinstance(rows,list):raise ValueError('Invalid assets response')
            result.extend(rows)
            if len(rows)<100:return result
        raise ValueError('Release asset count exceeds supported bound')
    def upload(self,release_id,name,data):return self.call('https://uploads.github.com/repos/'+REPOSITORY+f'/releases/{release_id}/assets?name='+urllib.parse.quote(name,safe=''),'POST',raw=data)

def verify_asset(asset,tag,name,digest,size):
    expected=f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
    if not isinstance(asset,dict) or asset.get('name')!=name or asset.get('state')!='uploaded' or asset.get('size')!=size or asset.get('digest')!='sha256:'+digest or asset.get('browser_download_url')!=expected or type(asset.get('id')) is not int:raise ValueError('Release asset verification failed; ZIP retained')
    return {'schema_version':1,'url':expected,'sha256':digest,'size':size,'asset_id':asset['id']}

def offload(site,existing,run,attempt,commit,github):
    site=Path(site)
    if not run.isdigit() or not attempt.isdigit() or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Invalid trusted workflow identity')
    if not isinstance(existing,list) or any(not isinstance(v,str) or not SAFE.fullmatch(v) for v in existing):raise ValueError('Invalid existing record catalog')
    existing=set(existing);tag=f'evidence-{run}-{attempt}';release=None;assets={};index={}
    for folder in sorted((site/'runs').iterdir()):
        if folder.is_symlink() or not folder.is_dir() or not SAFE.fullmatch(folder.name):raise ValueError('Unsafe run directory')
        pointer=folder/'evidence-location.json'
        if pointer.exists():
            value=read_json(pointer);valid_tree(value)
            # Reuse the renderer's strict pointer validator once available.
            index[folder.name]=validate_evidence_location(value,folder.name)['url'];continue
        if folder.name in existing:continue
        archive=folder/'evidence.zip'
        if archive.is_symlink() or not archive.is_file():raise ValueError('Missing new evidence ZIP')
        if not 0<archive.stat().st_size<2*1024**3:raise ValueError('Evidence ZIP exceeds Release limits')
        data=archive.read_bytes();digest=hashlib.sha256(data).hexdigest();name=folder.name+'-'+digest+'.zip'
        # Validate chart snapshots BEFORE any upload or local removal.
        display={}
        for renderer,target in ((MOTOR_RENDERER,'motor-display.json'),(CADENCE_RENDERER,'cadence-display.json')):
            source=site/renderer/(folder.name+'.json');value=read_json(source);validate_display(value,read_json(folder/'data.json'),renderer);display[target]=source
        if release is None:
            if github.call('').get('private') is not False:raise ValueError('Evidence destination must be public')
            release=github.release(tag,commit);assets={a['name']:a for a in github.assets(release['id'])}
        asset=assets.get(name) or github.upload(release['id'],name,data)
        # Re-fetch by ID rather than relying only on the upload acknowledgment.
        if type(asset.get('id')) is not int:raise ValueError('Missing uploaded asset ID')
        asset=github.call('/releases/assets/'+str(asset['id']))
        location=validate_evidence_location(verify_asset(asset,tag,name,digest,len(data)),folder.name)
        for target,source in display.items():shutil.copyfile(source,folder/target)
        pointer.write_text(json.dumps(location,sort_keys=True)+'\n')
        archive.unlink() # NEW local packaging only. Never an existing archive.
        index[folder.name]=location['url']
    (site/'evidence-index.json').write_text(json.dumps(index,sort_keys=True)+'\n')
    size=sum(p.stat().st_size for p in site.rglob('*') if p.is_file() and not p.is_symlink())
    if size>MAX_SITE:raise ValueError(f'Pages package {size} bytes exceeds safe 900MB limit; verified Release evidence is retained, prior site remains live')
    return {'pages_bytes':size,'external_archives':len(index),'new_release':tag if release else None}

def main():
    p=argparse.ArgumentParser();p.add_argument('--site',type=Path,required=True);p.add_argument('--existing',type=Path,required=True);a=p.parse_args()
    result=offload(a.site,json.loads(a.existing.read_text()),os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'],os.environ['GITHUB_SHA'],GitHub(os.environ['GH_TOKEN']))
    print(json.dumps(result))
if __name__=='__main__':main()
