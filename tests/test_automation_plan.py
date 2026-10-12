import importlib.util, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('automation_plan',ROOT/'dashboard/automation_plan.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
SHA='a'*40
class RequestTests(unittest.TestCase):
    def request(self):return {'schema_version':1,'repository':p.REPOSITORY,'pull_request':123,'head_sha':SHA}
    def pr(self):return {'state':'open','base':{'repo':{'full_name':p.REPOSITORY}},'head':{'sha':SHA,'repo':{'full_name':p.REPOSITORY}}}
    def test_exact_head(self):self.assertEqual(SHA,p.validate_request('requests/pr-123/'+SHA+'.json',self.request(),lambda _:self.pr())['commit'])
    def test_stale_closed_wrong_repo(self):
        for mutate in (lambda d:d.update(state='closed'),lambda d:d['head'].update(sha='b'*40),lambda d:d['base']['repo'].update(full_name='attacker/repo')):
            pr=self.pr();mutate(pr)
            with self.assertRaises(ValueError):p.validate_request('requests/pr-123/'+SHA+'.json',self.request(),lambda _:pr)
    def test_injection_and_unknown_fields(self):
        for path in ('../../x','requests/pr-123/'+SHA+'.json;id','requests/pr-124/'+SHA+'.json'):
            with self.assertRaises(ValueError):p.validate_request(path,self.request(),lambda _:self.pr())
        v=self.request();v['command']='echo unsafe'
        with self.assertRaises(ValueError):p.validate_request('requests/pr-123/'+SHA+'.json',v,lambda _:self.pr())
    def test_fork_requires_existing_approved_ci(self):
        pr=self.pr();pr['head']['repo']['full_name']='contributor/fork'
        def fetch(path):return pr if path.startswith('pulls/') else {'workflow_runs':[]}
        with self.assertRaisesRegex(ValueError,'explicit maintainer'):p.validate_request('requests/pr-123/'+SHA+'.json',self.request(),fetch)
        def approved(path):return pr if path.startswith('pulls/') else {'workflow_runs':[{'name':'ride-performance','head_sha':SHA,'conclusion':'success'}]}
        with self.assertRaisesRegex(ValueError,'explicit maintainer'):p.validate_request('requests/pr-123/'+SHA+'.json',self.request(),approved)
    def test_fingerprint_ignores_requests(self):self.assertRegex(p.code_fingerprint(ROOT),r'^[0-9a-f]{64}$')
if __name__=='__main__':unittest.main()

class EvidenceSanitizerTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('sanitize_evidence',ROOT/'dashboard/sanitize_evidence.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def test_inert_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'safe.json').write_text('{}');(p/'execute').write_text('not allowed');self.module().sanitize(p)
            self.assertTrue((p/'safe.json').exists());self.assertFalse((p/'execute').exists())
    def test_symlink_never_followed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);outside=p/'secret.txt';outside.write_text('secret');root=p/'output';root.mkdir();(root/'steal.json').symlink_to(outside)
            with self.assertRaises(ValueError):self.module().sanitize(root)
            self.assertEqual('secret',outside.read_text());self.assertFalse((root/'steal.json').exists());self.assertIn('Unsafe',(root/'comparison.json').read_text())
