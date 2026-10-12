"""Security and immutable-history tests for the trusted Pages renderer."""
import importlib.util,json,os,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('dashboard_build',Path(__file__).resolve().parents[1]/'dashboard/build.py')
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'input';self.source.mkdir();self.history=self.root/'history';self.dest=self.history/'run-1'
        self.payload={'status':'complete','passed':False,'runs':[{'scenario':'steps','seed':7,'absolute_passed':False,'relative_passed':True,'scores':{}}]}
        (self.source/'comparison.json').write_text(json.dumps(self.payload))
    def tearDown(self):self.tmp.cleanup()
    def test_inert_only_and_complete_history(self):
        (self.source/'evil.html').write_text('<script>alert(1)</script>');(self.source/'evil.svg').write_text('<svg onload="alert(1)">');(self.source/'evil.js').write_text('alert(1)')
        m.materialize(self.source,self.dest,'run-1',{'notes':'<img onerror=alert(1)>'})
        m.build(self.history,self.root/'site')
        with zipfile.ZipFile(self.dest/'evidence.zip')as z:self.assertEqual(z.namelist(),['comparison.json'])
        self.assertIn('textContent', (self.root/'site/app.js').read_text());self.assertNotIn('innerHTML', (self.root/'site/app.js').read_text())
        self.assertEqual(json.loads((self.root/'site/history.json').read_text())[0]['status'],'complete')
    def test_branch_display_keeps_immutable_id(self):
        self.payload['firmware']={'candidate':{'commit':'782c2b5e303115f90bf8f81b724da5717362de39'}}
        (self.source/'comparison.json').write_text(json.dumps(self.payload))
        m.materialize(self.source,self.dest,'run-1',{'run_completed_at':'2026-10-12T17:20:30Z'})
        m.build(self.history,self.root/'site')
        entry=json.loads((self.root/'site/history.json').read_text())[0]
        self.assertEqual(entry['display_ref'],'erg-spike-gate');self.assertEqual(entry['id'],'run-1')
    def test_unknown_ref_uses_commit_not_main(self):
        self.payload['firmware']={'candidate':{'commit':'abcdef0123456789abcdef0123456789abcdef01'}}
        (self.source/'comparison.json').write_text(json.dumps(self.payload))
        m.materialize(self.source,self.dest,'run-1',{})
        m.build(self.history,self.root/'site')
        entry=json.loads((self.root/'site/history.json').read_text())[0]
        self.assertEqual(entry['display_ref'],'commit abcdef012345')
    def test_cannot_overwrite_run(self):
        m.materialize(self.source,self.dest,'run-1',{})
        with self.assertRaises(ValueError):m.materialize(self.source,self.dest,'run-1',{})
    def test_missing_manifest_preserved_as_incomplete(self):
        (self.source/'comparison.json').unlink();m.materialize(self.source,self.dest,'run-1',{})
        self.assertEqual(json.loads((self.dest/'comparison.json').read_text())['status'],'incomplete')
    def test_unsafe_paths_rejected(self):
        with self.assertRaises(ValueError):m.materialize(self.source,self.dest,'../evil',{})
    def test_symlink_rejected(self):
        (self.source/'secret.txt').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):m.materialize(self.source,self.dest,'run-1',{})
    def test_nonfinite_rejected(self):
        self.payload['score']=float('nan');(self.source/'comparison.json').write_text(json.dumps(self.payload))
        with self.assertRaises(ValueError):m.materialize(self.source,self.dest,'run-1',{})
    def test_invalid_metadata_date_rejected(self):
        with self.assertRaises(ValueError):m.materialize(self.source,self.dest,'run-1',{'run_completed_at':{}})
    def test_invalid_failure_list_rejected(self):
        self.payload['runs'][0]['failures']={}
        with self.assertRaises(ValueError):m.validate(self.payload)
    def test_nonobject_row_rejected(self):
        self.payload['runs']=[1]
        with self.assertRaises(ValueError):m.validate(self.payload)
    def test_duplicate_scenario_rejected(self):
        self.payload['runs']*=2
        with self.assertRaises(ValueError):m.validate(self.payload)
    def test_decisions_must_be_boolean(self):
        self.payload['runs'][0]['relative_passed']='true'
        with self.assertRaises(ValueError):m.validate(self.payload)
    def test_chart_decimation_preserves_endpoints(self):
        data='time_s,target_w,power_w,latest_delivered_sensor_power_w\n'+''.join(f'{i},100,99,98\n'for i in range(4000))
        chart=m.chart(data.encode());self.assertLessEqual(len(chart),1801);self.assertEqual(chart[0][0],0);self.assertEqual(chart[-1][0],3999)
    def test_invalid_metadata_becomes_incomplete(self):
        (self.source/'run-metadata.json').write_text('{broken')
        script=Path(__file__).resolve().parents[1]/'dashboard/ingest.py'
        env={**os.environ,'EVENT_NAME':'workflow_run','SOURCE_RUN_ID':'123','SOURCE_ATTEMPT':'1'}
        subprocess.run([sys.executable,str(script),'--input',str(self.source),'--history',str(self.history),'--output',str(self.root/'site')],env=env,check=True)
        data=json.loads((self.history/'actions-123-1'/'comparison.json').read_text())
        self.assertEqual(data['status'],'incomplete')
    def test_failed_manifest_retained(self):
        self.payload.update(status='failed',error='Adapter API unavailable');(self.source/'comparison.json').write_text(json.dumps(self.payload))
        m.materialize(self.source,self.dest,'run-1',{});self.assertEqual(json.loads((self.dest/'data.json').read_text())['comparison']['status'],'failed')
if __name__=='__main__':unittest.main()
