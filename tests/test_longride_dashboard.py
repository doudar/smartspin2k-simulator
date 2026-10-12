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

class SprintRideDashboardTests(unittest.TestCase):
    def setUp(self):
        import copy
        self.copy=copy.deepcopy
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'input'
        (self.source/'paired').mkdir(parents=True);(self.source/'training').mkdir()
        self.experiment='continuous-long-ride-sprints-v2'
        self.check={'passed':True,'absolute_passed':True,'relative_passed':True,'failures':[]}
        pair={**self.check,'reported_power_comparison':dict(self.check)}
        self.manifest={'status':'complete','experiment':self.experiment,'runs':[],'requested_cases':[],'initial_fixtures':{'full':{'coverage':{'tested_range_supported':45,'tested_range_required':45}}}}
        for state in ('empty','full'):
            for sensitivity in (3,5,10):
                case={'minutes':90,'initial_state':state,'seed':7,'sensitivity':sensitivity}
                self.manifest['requested_cases'].append(case)
                row={**case,**self.copy(pair),'scores':{},'metadata':{},'window_comparisons':{n:self.copy(pair) for n in ('early','middle','late')},'sprint_comparisons':{n:self.copy(pair) for n in ('early','middle','late')}}
                self.manifest['runs'].append(row)
                for variant in ('baseline','candidate'):
                    path=self.source/'paired'/variant/f'long_90m_{state}_sensitivity{sensitivity}-7';path.mkdir(parents=True)
                    (path/'trace.csv').write_text('time_s,target_w,power_w,latest_delivered_sensor_power_w,motor_steps,cadence_rpm\n0,100,99,98,100,85\n390,500,499,498,200,85\n415,100,101,102,101,85\n5400,100,99,98,100,85\n')
        self.write()
        (self.source/'training/longride.json').write_text(json.dumps({'status':'complete','experiment':self.experiment,'runs':[],'training':{'full_fixture_created':True,'sensitivity':5}}))
        (self.source/'training/full.json').write_text('{"fixture":"original-v2"}')
        (self.source/'run-metadata.json').write_text(json.dumps({'candidate_ref':'erg-spike-gate','run_completed_at':'2026-10-12T18:00:00Z'}))
    def write(self):(self.source/'paired/longride.json').write_text(json.dumps(self.manifest))
    def tearDown(self):self.tmp.cleanup()
    def prepare(self):return prepare(self.source,self.root/'stage','sprint-batch')
    def test_all_six_cases_have_unique_sensitivity_archives_and_shared_training(self):
        sources=self.prepare();self.assertEqual(len(sources),7);self.assertEqual(len(set(p.name for p in sources)),7)
        history=self.root/'history'
        for source in sources:
            metadata=json.loads((source/'run-metadata.json').read_text())
            materialize(source,history/('sprint-batch-'+source.name),'sprint-batch-'+source.name,metadata)
        originals={str(p.relative_to(history)):p.read_bytes() for p in history.rglob('*') if p.is_file()}
        build(history,self.root/'site');entries=json.loads((self.root/'site/history.json').read_text())
        self.assertEqual(len(entries),6)
        self.assertEqual({(r['metadata']['initial_state'],r['metadata']['sensitivity']) for r in entries},{(state,s) for state in ('empty','full') for s in (3,5,10)})
        self.assertTrue(all(r['metadata']['experiment']==self.experiment for r in entries))
        self.assertTrue(all(r['metadata']['training_run_id']=='sprint-batch-training' for r in entries))
        for state in ('empty','full'):
            for sensitivity in (3,5,10):
                run=history/f'sprint-batch-long-90m-{state}-sensitivity{sensitivity}-7'
                data=json.loads((run/'data.json').read_text())
                row=data['comparison']['runs'][0]
                self.assertEqual(row['sensitivity'],sensitivity);self.assertTrue(row['overall_checks']['passed'])
                self.assertIn('all three sprint blocks',row['overall_checks_scope'])
                with zipfile.ZipFile(run/'evidence.zip') as archive:
                    self.assertIn(f'candidate/long_90m_{state}_sensitivity{sensitivity}-7/trace.csv',archive.namelist())
                    self.assertEqual(archive.read('longride.json'),(self.source/'paired/longride.json').read_bytes())
                motor=json.loads((self.root/f'site/motor-v1/{run.name}.json').read_text())
                self.assertEqual(motor['traces']['long_ride-7'][1],[390,200])
                cadence=json.loads((self.root/f'site/cadence-v1/{run.name}.json').read_text())
                self.assertEqual(cadence['traces']['long_ride-7'][1],[390,85,None])
        for name,raw in originals.items():self.assertEqual((history/name).read_bytes(),raw)
        training=json.loads((history/'sprint-batch-training/comparison.json').read_text())
        self.assertEqual(training['experiment'],'long-ride-training-sprints-v2')
        self.assertEqual(training['training']['sensitivity'],5)
    def test_single_sprint_signal_failure_defeats_whole_ride_and_all_other_passes(self):
        for flag in ('absolute_passed','relative_passed'):
            with self.subTest(flag=flag):
                row=self.manifest['runs'][0]
                row['sprint_comparisons']['late']['reported_power_comparison'][flag]=False
                self.write();sources=self.prepare()
                comparison=json.loads((sources[1]/'comparison.json').read_text());result=comparison['runs'][0]
                self.assertTrue(result[flag]);self.assertFalse(result['overall_checks'][flag]);self.assertFalse(result['overall_checks']['passed']);self.assertFalse(comparison['passed'])
                row['sprint_comparisons']['late']['reported_power_comparison'][flag]=True
    def test_missing_sensitivity_case_kept_separately_as_incomplete(self):
        self.manifest['runs'].pop();self.write();sources=self.prepare()
        missing=self.root/'stage/long-90m-full-sensitivity10-7'
        value=json.loads((missing/'comparison.json').read_text());self.assertEqual(value['status'],'incomplete');self.assertFalse(value['passed']);self.assertEqual(value['runs'],[])
        self.assertEqual(len(sources),7)
    def test_missing_unknown_or_unmeasured_sprint_decisions_rejected(self):
        row=self.manifest['runs'][0];original=self.copy(row['sprint_comparisons'])
        bad=[{}, {'unexpected':self.copy(self.check)}]
        omitted=self.copy(original);del omitted['early']['reported_power_comparison'];bad.append(omitted)
        nonbool=self.copy(original);nonbool['late']['absolute_passed']='true';bad.append(nonbool)
        invalid=self.copy(original);invalid['middle']['failures']=[1];bad.append(invalid)
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):
                row['sprint_comparisons']=value;self.write();self.prepare()
    def test_only_current_sensitivity_matrix_is_accepted(self):
        original=self.copy(self.manifest['runs'][0])
        for update in ({'minutes':30},{'initial_state':'partial'},{'sensitivity':None},{'sensitivity':True},{'sensitivity':4}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                self.manifest['runs'][0]={**original,**update};self.write();self.prepare()
    def test_duplicate_sensitivity_case_rejected(self):
        self.manifest['runs'].append(self.copy(self.manifest['runs'][0]));self.write()
        with self.assertRaises(ValueError):self.prepare()
    def test_training_version_must_match_paired_case(self):
        (self.source/'training/longride.json').write_text(json.dumps({'status':'complete','experiment':'continuous-long-ride-v1','runs':[]}))
        with self.assertRaisesRegex(ValueError,'versions differ'):self.prepare()
    def test_v2_extrema_and_sprint_edges_survive_chart_materialization(self):
        path=self.source/'paired/candidate/long_90m_empty_sensitivity3-7/trace.csv'
        rows=['time_s,target_w,power_w,latest_delivered_sensor_power_w,motor_steps,cadence_rpm']
        for i in range(5401):
            target=500 if 390<=i<415 else 100
            rows.append(f'{i},{target},{999 if i==401 else target},{888 if i==407 else target},{9999 if i==403 else 100},85')
        path.write_text('\n'.join(rows)+'\n');source=self.prepare()[1]
        history=self.root/'history';run=history/'sprint-case';metadata=json.loads((source/'run-metadata.json').read_text())
        materialize(source,run,'sprint-case',metadata);build(history,self.root/'site')
        data=json.loads((run/'data.json').read_text());trace=data['traces']['long_ride-7']['candidate']
        self.assertLessEqual(len(trace),1801)
        for point in ([389,100,100,100],[390,500,500,500],[414,500,500,500],[415,100,100,100],[401,500,999,500],[407,500,500,888]):self.assertIn(point,trace)
        motor=json.loads((self.root/'site/motor-v1/sprint-case.json').read_text())
        self.assertIn([403,9999],motor['traces']['long_ride-7']);self.assertLessEqual(len(motor['traces']['long_ride-7']),1801)

if __name__=='__main__':unittest.main()
