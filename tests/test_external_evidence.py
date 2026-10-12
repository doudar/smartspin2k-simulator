"""Mixed local/Release evidence rebuilds preserve immutable bytes and charts."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('external_evidence_build',Path(__file__).resolve().parents[1]/'dashboard/build.py')
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)


class ExternalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.history=self.root/'history';self.site=self.root/'site';self.source=self.root/'input';self.source.mkdir()
        self.manifest={'status':'complete','runs':[{'scenario':'steps','seed':7}]}
        (self.source/'comparison.json').write_text(json.dumps(self.manifest))
        trace=self.source/'candidate/steps-7/trace.csv';trace.parent.mkdir(parents=True)
        trace.write_text('time_s,target_w,power_w,latest_delivered_sensor_power_w,motor_steps,cadence_rpm\n0,100,99,98,120,85\n1,100,100,99,-10,0\n2,100,101,100,,\n')
        for run_id in ('old','new','shared-training'):
            m.materialize(self.source,self.history/run_id,run_id,{'evidence_only':True} if run_id=='shared-training' else {})
        m.build(self.history,self.site)

    def tearDown(self): self.tmp.cleanup()

    def offload(self,run_id='new'):
        run=self.history/run_id;archive=run/'evidence.zip';raw=archive.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        value={'schema_version':1,'url':f'{m.EVIDENCE_RELEASE_ROOT}evidence-12345678901-2/{run_id}-{digest}.zip',
               'sha256':digest,'size':len(raw),'asset_id':12345}
        (run/'evidence-location.json').write_text(json.dumps(value))
        for renderer,name in ((m.MOTOR_RENDERER,'motor-display.json'),(m.CADENCE_RENDERER,'cadence-display.json')):
            shutil.copyfile(self.site/renderer/(run_id+'.json'),run/name)
        archive.unlink()
        return value

    def test_mixed_rebuild_preserves_all_record_bytes_and_plots(self):
        before={renderer:(self.site/renderer/'new.json').read_bytes() for renderer in (m.MOTOR_RENDERER,m.CADENCE_RENDERER)}
        new=self.offload();training=self.offload('shared-training')
        originals={p.relative_to(self.history):p.read_bytes() for p in self.history.rglob('*') if p.is_file()}
        m.build(self.history,self.site)
        for relative,raw in originals.items():
            self.assertEqual((self.history/relative).read_bytes(),raw)
            self.assertEqual((self.site/'runs'/relative).read_bytes(),raw)
        self.assertFalse((self.site/'runs/new/evidence.zip').exists())
        self.assertTrue((self.site/'runs/old/evidence.zip').is_file())
        for renderer,raw in before.items(): self.assertEqual((self.site/renderer/'new.json').read_bytes(),raw)
        self.assertEqual(json.loads((self.site/'evidence-index.json').read_text()),{'new':new['url'],'shared-training':training['url']})
        self.assertEqual({row['id'] for row in json.loads((self.site/'history.json').read_text())},{'old','new'})
        # A clean, offline rebuild needs no raw ZIP and regenerates identical plots.
        fresh=self.root/'fresh';m.build(self.history,fresh)
        for renderer,raw in before.items(): self.assertEqual((fresh/renderer/'new.json').read_bytes(),raw)

    def test_missing_zip_requires_valid_pointer_and_both_displays(self):
        (self.history/'new/evidence.zip').unlink()
        with self.assertRaisesRegex(ValueError,'Missing local or external'): m.build(self.history,self.site)

    def test_offloaded_record_requires_each_display(self):
        self.offload()
        for name in ('motor-display.json','cadence-display.json'):
            path=self.history/'new'/name;raw=path.read_bytes();path.unlink()
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'Missing persisted display'): m.build(self.history,self.site)
            path.write_bytes(raw)

    def test_malformed_pointer_fails_even_when_local_zip_exists(self):
        (self.history/'new/evidence-location.json').write_text('{}')
        with self.assertRaises(ValueError): m.build(self.history,self.site)

    def test_pointer_bounds_types_and_exact_url_identity(self):
        value=self.offload();self.assertEqual(m.validate_evidence_location(value),value)
        self.assertEqual(m.validate_evidence_location(value,'new'),value)
        cases=[('schema_version',True),('schema_version',2),('size',0),('size',-1),('size',True),('size',2**31),
               ('asset_id',0),('asset_id',False),('asset_id',2**53),('sha256','x'*64),('sha256','A'*64),('url',None)]
        for key,replacement in cases:
            bad={**value,key:replacement}
            with self.subTest(key=key,replacement=replacement),self.assertRaises(ValueError): m.validate_evidence_location(bad,'new')
        attacks=[value['url'].replace('github.com','github.com.evil.test'),value['url'].replace('doudar/','other/'),
                 value['url'].replace('https:','http:'),value['url']+'?download=1',value['url']+'#fragment',value['url']+'\n',
                 value['url'].replace('/new-','/old-'),value['url'].replace('evidence-12345678901-2','evidence-12345678901-0'),
                 value['url'].replace('evidence-12345678901-2','evidence-run-2'),value['url'].replace('/new-','/../new-'),
                 value['url'].replace(value['sha256'],'b'*64)]
        for url in attacks:
            with self.subTest(url=url),self.assertRaises(ValueError): m.validate_evidence_location({**value,'url':url},'new')

    def test_sidecars_reject_unbounded_unknown_or_fabricated_series(self):
        self.offload();data=m.read_json(self.history/'new/data.json')
        base=m.read_json(self.history/'new/cadence-display.json')
        cases=[]
        for key,value in [('renderer','cadence-v2'),('source_field','desired_rpm'),('units','watts'),('received_source_field','invented')]:
            bad=copy.deepcopy(base);bad[key]=value;cases.append(bad)
        for rows in ([[0,85,85]],[[0,True,None]],[[0,-1,None]],[[0,float('nan'),None]],[[0,1e9,None]],
                     [[1,85,None],[0,85,None]],[[0,85,None],[0,85,None]],[[None,85,None]],[[0,85]],[[i,85,None] for i in range(1802)]):
            bad=copy.deepcopy(base);bad['traces']['steps-7']=rows;cases.append(bad)
        bad=copy.deepcopy(base);bad['traces']['unrecorded-7']=[];cases.append(bad)
        for bad in cases:
            with self.subTest(bad=str(bad)[:160]),self.assertRaises(ValueError): m.validate_display(bad,data,m.CADENCE_RENDERER)
        (self.history/'new/cadence-display.json').write_text(json.dumps(cases[0]))
        with self.assertRaises(ValueError): m.build(self.history,self.site)

    def test_symlink_pointer_or_display_is_rejected(self):
        self.offload()
        for name in ('evidence-location.json','motor-display.json','cadence-display.json'):
            path=self.history/'new'/name;raw=path.read_bytes();target=self.root/name;target.write_bytes(raw);path.unlink();path.symlink_to(target)
            with self.subTest(name=name),self.assertRaises(ValueError): m.build(self.history,self.site)
            path.unlink();path.write_bytes(raw)


if __name__=='__main__': unittest.main()
