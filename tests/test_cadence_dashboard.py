"""Recorded-cadence lineage, bounded presentation, and immutable backfill tests."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

SPEC = importlib.util.spec_from_file_location(
    'cadence_dashboard_build', Path(__file__).resolve().parents[1] / 'dashboard/build.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class CadenceChartTests(unittest.TestCase):
    def test_uses_modeled_trace_cadence_and_never_invents_received(self):
        raw = b'time_s,cadence_rpm,reported_rpm,callout_rpm,desired_rpm\n0,83,84,90,89\n1,0,85,91,92\n'
        self.assertEqual(m.cadence_chart(raw), [[0,83,None],[1,0,None]])

    def test_zero_is_valid_and_missing_invalid_or_negative_values_are_gaps(self):
        raw = b'time_s,cadence_rpm\n0,0\n1,\n2,nan\n3,inf\n4,-1\n5,invalid\n6,1000000000\n7,82.5\n'
        self.assertEqual(m.cadence_chart(raw),
                         [[0,0,None]] + [[i,None,None] for i in range(1,7)] + [[7,82.5,None]])

    def test_missing_column_or_empty_trace_is_unavailable(self):
        for raw in (b'', b'time_s,cadence_rpm\n', b'time_s,reported_rpm\n0,90\n',
                    b'time_s,callout_rpm,desired_rpm\n0,90,89\n'):
            with self.subTest(raw=raw):
                self.assertEqual(m.cadence_chart(raw), [])

    def test_invalid_clock_or_duplicate_fields_rejected(self):
        for raw in (b'time_s,cadence_rpm\n-1,80\n', b'time_s,cadence_rpm\nnan,80\n',
                    b'time_s,cadence_rpm\ninf,80\n', b'time_s,cadence_rpm\n,80\n',
                    b'time_s,cadence_rpm\n1,80\n1,90\n', b'time_s,cadence_rpm\n1,80\n0,90\n',
                    b'cadence_rpm\n80\n', b'time_s,cadence_rpm,cadence_rpm\n0,80,90\n'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                m.cadence_chart(raw)

    def test_extrema_endpoints_zero_and_internal_gap_survive_decimation(self):
        values = ['80'] * 9000
        values[31] = ''
        values[123] = '0'
        values[8642] = '130'
        raw = 'time_s,cadence_rpm\n' + ''.join(f'{i},{value}\n' for i,value in enumerate(values))
        result = m.cadence_chart(raw.encode())
        self.assertLessEqual(len(result),1801)
        self.assertEqual(result[0],[0,80,None])
        self.assertEqual(result[-1],[8999,80,None])
        for point in ([31,None,None],[123,0,None],[8642,130,None]):
            self.assertIn(point,result)
        self.assertEqual([r[0] for r in result],sorted({r[0] for r in result}))

    def test_all_missing_remains_missing_and_bounded(self):
        raw = 'time_s,cadence_rpm\n' + ''.join(f'{i},\n' for i in range(9000))
        result = m.cadence_chart(raw.encode())
        self.assertLessEqual(len(result),1801)
        self.assertTrue(all(r[1] is None and r[2] is None for r in result))


class CadenceBackfillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root/'input'
        self.source.mkdir()
        self.history = self.root/'history'
        self.run = self.history/'run-1'
        self.output = self.root/'site'
        self.payload = {'status':'complete','runs':[{'scenario':'long_ride','seed':27,
                        'artifact_key':'long_30m_empty-27','scores':{'rmse_w':12.34}}]}
        (self.source/'comparison.json').write_text(json.dumps(self.payload))

    def tearDown(self):
        self.tmp.cleanup()

    def trace(self,variant='candidate',cadence=True):
        path = self.source/variant/'long_30m_empty-27/trace.csv'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('time_s,target_w,power_w,latest_delivered_sensor_power_w,motor_steps'
                        + (',cadence_rpm' if cadence else '') + '\n'
                        + '0,100,99,98,120' + (',85' if cadence else '') + '\n'
                        + '1,100,99,98,140' + (',0' if cadence else '') + '\n')
        return path

    def build(self):
        m.materialize(self.source,self.run,'run-1',{})
        m.build(self.history,self.output)
        return json.loads((self.output/'cadence-v1/run-1.json').read_text())

    def test_backfill_uses_artifact_key_and_preserves_all_immutable_bytes(self):
        self.trace()
        m.materialize(self.source,self.run,'run-1',{})
        originals = {p.name:p.read_bytes() for p in self.run.iterdir()}
        m.build(self.history,self.output)
        display = json.loads((self.output/'cadence-v1/run-1.json').read_text())
        self.assertEqual(display, {'source_field':'cadence_rpm','received_source_field':None,
                         'units':'rpm','renderer':'cadence-v1',
                         'traces':{'long_ride-27':[[0,85,None],[1,0,None]]}})
        for name,raw in originals.items():
            self.assertEqual((self.run/name).read_bytes(),raw)
            self.assertEqual((self.output/'runs/run-1'/name).read_bytes(),raw)
        first = (self.output/'cadence-v1/run-1.json').read_bytes()
        m.build(self.history,self.output)
        self.assertEqual((self.output/'cadence-v1/run-1.json').read_bytes(),first)

    def test_missing_candidate_is_not_replaced_by_baseline(self):
        self.trace(variant='baseline')
        self.assertEqual(self.build()['traces'],{})

    def test_hover_script_is_copied_and_content_versioned(self):
        self.build()
        source = Path(m.__file__).parent/'hover.js'
        self.assertEqual((self.output/'hover.js').read_bytes(),source.read_bytes())
        version = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        self.assertIn('"hover.js?v='+version+'"',(self.output/'index.html').read_text())

    def test_no_reconstruction_from_plan_packets_or_intermittent_logs(self):
        trace = self.trace(cadence=False)
        (trace.parent/'cadence.csv').write_text('time_s,callout_rpm,desired_rpm,reported_rpm\n0,90,89,85\n')
        (trace.parent/'sensor_packets.csv').write_text('delivered_s,acquired_s,characteristic,payload_hex\n0,0,2a5b,0200000000\n')
        (trace.parent/'firmware.log').write_text('[1000](ERG_Mode_CSV): 100;100;100;100;100;100;90;90\n')
        display = self.build()
        self.assertEqual(display['traces'],{'long_ride-27':[]})
        self.assertIsNone(display['received_source_field'])

    def test_corrupt_clock_marks_presentation_unavailable_without_losing_run(self):
        self.trace()
        m.materialize(self.source,self.run,'run-1',{})
        # Simulate a damaged archived cadence trace without depending on the
        # ingestion power parser, which intentionally rejects invalid clocks.
        with zipfile.ZipFile(self.run/'evidence.zip','w') as z:
            z.writestr('candidate/long_30m_empty-27/trace.csv','time_s,cadence_rpm\nnan,80\n')
        m.build(self.history,self.output)
        display = json.loads((self.output/'cadence-v1/run-1.json').read_text())
        self.assertEqual(display['status'],'unavailable')
        self.assertEqual(display['traces'],{})
        self.assertEqual(json.loads((self.output/'history.json').read_text())[0]['status'],'complete')

    def test_duplicate_or_oversized_archive_member_is_rejected(self):
        trace = self.trace()
        m.materialize(self.source,self.run,'run-1',{})
        data = json.loads((self.run/'data.json').read_text())
        with patch.object(m,'MAX_FILE',1), self.assertRaises(ValueError):
            m.cadence_display(self.run,data)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(self.run/'evidence.zip','a') as z:
                z.writestr('candidate/long_30m_empty-27/trace.csv',trace.read_bytes())
        with self.assertRaises(ValueError):
            m.cadence_display(self.run,data)


if __name__ == '__main__':
    unittest.main()
