import importlib.util,json,sys,tempfile,unittest,zipfile
from pathlib import Path
DASHBOARD=Path(__file__).resolve().parents[1]/'dashboard'
sys.path.insert(0,str(DASHBOARD))
from build import build,materialize,decimate_extrema,validate
from longride_import import prepare

class LongRideDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'input';(self.source/'paired').mkdir(parents=True);(self.source/'training').mkdir()
        self.check={'passed':True,'absolute_passed':True,'relative_passed':True,'failures':[]}
        row={'minutes':90,'initial_state':'full','seed':27,'scores':{},'metadata':{},**self.check,'reported_power_comparison':dict(self.check),'window_comparisons':{name:{**self.check,'reported_power_comparison':dict(self.check)}for name in ('early','middle','late')}}
        self.manifest={'status':'complete','experiment':'continuous-long-ride-v1','runs':[row],'requested_cases':[{'minutes':90,'initial_state':'full','seed':27},{'minutes':30,'initial_state':'empty','seed':27}],'initial_fixtures':{'full':{'coverage':{'tested_range_supported':25,'tested_range_required':25}}}}
        self.write()
        (self.source/'training/longride.json').write_text(json.dumps({'status':'complete','experiment':'continuous-long-ride-v1','runs':[],'training':{'full_fixture_created':True}}))
        (self.source/'training/full.json').write_text('{"fixture":"original"}')
        for variant in ('baseline','candidate'):
            path=self.source/'paired'/variant/'long_90m_full-27';path.mkdir(parents=True)
            (path/'trace.csv').write_text('time_s,target_w,power_w,latest_delivered_sensor_power_w,motor_steps\n0,200,199,198,100\n1,200,201,202,101\n')
        (self.source/'run-metadata.json').write_text(json.dumps({'candidate_ref':'erg-spike-gate','run_completed_at':'2026-10-12T18:00:00Z'}))
    def write(self):(self.source/'paired/longride.json').write_text(json.dumps(self.manifest))
    def tearDown(self):self.tmp.cleanup()
    def test_split_preserves_raw_names_links_training_and_missing_case(self):
        sources=prepare(self.source,self.root/'stage','actions-1-1');self.assertEqual(len(sources),3)
        history=self.root/'history'
        for source in sources:
            metadata=json.loads((source/'run-metadata.json').read_text());materialize(source,history/('actions-1-1-'+source.name),'actions-1-1-'+source.name,metadata)
        build(history,self.root/'site');entries=json.loads((self.root/'site/history.json').read_text());self.assertEqual(len(entries),2)
        case=history/'actions-1-1-long-90m-full-27';data=json.loads((case/'data.json').read_text())
        self.assertEqual(data['metadata']['training_run_id'],'actions-1-1-training');self.assertEqual(data['comparison']['runs'][0]['scenario'],'long_ride');self.assertIn('long_ride-27',data['traces'])
        with zipfile.ZipFile(case/'evidence.zip')as z:
            self.assertIn('candidate/long_90m_full-27/trace.csv',z.namelist());self.assertIn('longride.json',z.namelist());self.assertNotIn('full.json',z.namelist())
        self.assertEqual(json.loads((history/'actions-1-1-long-30m-empty-27/comparison.json').read_text())['status'],'incomplete')
    def test_probe_failure_cannot_be_hidden_by_whole_ride_pass(self):
        self.manifest['runs'][0]['window_comparisons']['early']['absolute_passed']=False;self.write()
        sources=prepare(self.source,self.root/'stage','actions-1-1');row=json.loads((sources[1]/'comparison.json').read_text())['runs'][0]
        self.assertTrue(row['absolute_passed']);self.assertFalse(row['overall_checks']['absolute_passed']);self.assertFalse(row['overall_checks']['passed'])
    def test_unsafe_artifact_key_rejected(self):
        with self.assertRaises(ValueError):validate({'status':'complete','runs':[{'scenario':'long_ride','seed':27,'artifact_key':'../../secret'}]})
    def test_target_transitions_and_brief_extrema_survive(self):
        rows=[[i,100 if i<2456 else 250,100,99]for i in range(9000)];rows[123][2]=999;rows[8642][3]=-100
        result=decimate_extrema(rows);self.assertLessEqual(len(result),1801);self.assertIn(rows[123],result);self.assertIn(rows[8642],result);self.assertIn(rows[2455],result);self.assertIn(rows[2456],result)
        self.assertEqual(result[0],rows[0]);self.assertEqual(result[-1],rows[-1])
    def test_duplicate_case_rejected(self):
        self.manifest['runs']*=2;self.write()
        with self.assertRaises(ValueError):prepare(self.source,self.root/'stage','actions-1-1')
    def test_symlink_rejected(self):
        (self.source/'paired/candidate/long_90m_full-27/private.txt').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):prepare(self.source,self.root/'stage','actions-1-1')
if __name__=='__main__':unittest.main()
