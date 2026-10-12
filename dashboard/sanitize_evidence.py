"""Reject links/special files before host-side cache or artifact tools read data."""
import argparse,json,os,re,shutil,stat
from pathlib import Path
ALLOWED={'.json','.csv','.log','.ptab','.txt'}
SAFE=re.compile(r'[A-Za-z0-9_.-]+')
def sanitize(root):
    root=Path(root)
    if root.is_symlink():raise ValueError('Evidence root must not be a symlink')
    root.mkdir(parents=True,exist_ok=True)
    unsafe=False;total=0
    for directory,dirs,files in os.walk(root,topdown=True,followlinks=False):
        for name in list(dirs):
            p=Path(directory)/name
            if p.is_symlink():p.unlink();dirs.remove(name);unsafe=True
            elif not SAFE.fullmatch(name):shutil.rmtree(p);dirs.remove(name);unsafe=True
        for name in files:
            p=Path(directory)/name;mode=p.lstat().st_mode
            if not stat.S_ISREG(mode) or not SAFE.fullmatch(name):p.unlink();unsafe=True;continue
            size=p.stat().st_size
            if p.suffix not in ALLOWED:p.unlink();continue
            total+=size
            if size>32*1024*1024 or total>768*1024*1024:p.unlink();unsafe=True
    if unsafe:
        for p in root.iterdir():
            if p.is_dir():shutil.rmtree(p)
            else:p.unlink()
        (root/'comparison.json').write_text(json.dumps({'status':'failed','passed':False,'runs':[],'error':'Unsafe or oversized evidence was rejected before artifact upload.'}))
        raise ValueError('Unsafe evidence rejected')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);sanitize(p.parse_args().root)
