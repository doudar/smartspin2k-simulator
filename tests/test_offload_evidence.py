import hashlib,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'dashboard'))
import offload_evidence as o
from build import MOTOR_RENDERER,CADENCE_RENDERER
class FakeGitHub:
    def __init__(self):self.rows={};self.uploads=0;self.bad=False
    def call(self,path,*args,**kwargs):
        if not path:return {'private':False}
        if path.startswith('/releases/assets/'):
            row=dict(self.rows[int(path.rsplit('/',1)[1])])
            if self.bad:row['digest']='sha256:'+'0'*64
            return row
        raise AssertionError(path)
    def release(self,tag,commit):self.tag=tag;return {'id':1}
    def assets(self,rid):return list(self.rows.values())
    def upload(self,rid,name,data):
        self.uploads+=1;row={'id':self.uploads,'name':name,'state':'uploaded','size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest(),'browser_download_url':f'https://github.com/{o.REPOSITORY}/releases/download/{self.tag}/{name}'};self.rows[row['id']]=row;return row
class OffloadTests(unittest.TestCase):
    def setup_site(self,root,name='actions-123-1-case'):
        record=root/'runs'/name;record.mkdir(parents=True);(record/'evidence.zip').write_bytes(b'inert zip test');(record/'data.json').write_text(json.dumps({'comparison':{'runs':[]}}))
        for renderer in (MOTOR_RENDERER,CADENCE_RENDERER):
            p=root/renderer;p.mkdir(exist_ok=True);(p/(name+'.json')).write_text(json.dumps({'traces':{},'renderer':renderer,'source_field':'motor_steps' if renderer==MOTOR_RENDERER else 'cadence_rpm','units':'steps' if renderer==MOTOR_RENDERER else 'rpm',**({'received_source_field':None} if renderer==CADENCE_RENDERER else {})}))
        return record
    def test_verified_upload_then_pointer(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);record=self.setup_site(root);g=FakeGitHub();result=o.offload(root,[],'456','1','a'*40,g)
            self.assertFalse((record/'evidence.zip').exists());self.assertEqual(1,g.uploads);self.assertTrue((record/'motor-display.json').exists());self.assertEqual(1,result['external_archives'])
            pointer=json.loads((record/'evidence-location.json').read_text());self.assertEqual('sha256:'+pointer['sha256'],g.rows[1]['digest'])
    def test_failed_digest_retains_zip(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);record=self.setup_site(root);g=FakeGitHub();g.bad=True
            with self.assertRaises(ValueError):o.offload(root,[],'456','1','a'*40,g)
            self.assertTrue((record/'evidence.zip').exists());self.assertFalse((record/'evidence-location.json').exists())
    def test_existing_record_untouched(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);record=self.setup_site(root);g=FakeGitHub();before=(record/'evidence.zip').read_bytes();o.offload(root,[record.name],'456','1','a'*40,g)
            self.assertEqual(before,(record/'evidence.zip').read_bytes());self.assertEqual(0,g.uploads)
    def test_pointer_and_public_url_constraints(self):
        asset={'id':1,'name':'safe.zip','state':'uploaded','size':4,'digest':'sha256:'+'a'*64,'browser_download_url':'https://evil.invalid/safe.zip'}
        with self.assertRaises(ValueError):o.verify_asset(asset,'evidence-1-1','safe.zip','a'*64,4)
    def test_symlink_never_uploaded(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);record=self.setup_site(root);(record/'evidence.zip').unlink();(record/'evidence.zip').symlink_to('/etc/passwd');g=FakeGitHub()
            with self.assertRaises(ValueError):o.offload(root,[],'456','1','a'*40,g)
            self.assertEqual(0,g.uploads)
if __name__=='__main__':unittest.main()
