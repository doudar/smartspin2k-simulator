import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from ss2k_sim.longride import long_workout, probe, coverage, observed_bridge, log_events, digest

class LongRideTests(unittest.TestCase):
    def table(self):
        return {'cadence_min':60,'cadence_increment':5,'watt_increment':30,'columns':30,
                'rows':10,'cells':[[-32768,0] for _ in range(300)]}
    def test_continuous_exact_duration_and_identical_probes(self):
        for minutes in (30,60,90):
            workout,windows=long_workout(minutes)
            self.assertEqual(workout.duration,minutes*60)
            self.assertEqual(len(windows),3)
            for window in windows:
                for t in range(360):
                    self.assertEqual(workout.at(window['start_s']+t),long_workout(30)[0].at(t))
        with self.assertRaises(ValueError): long_workout(120)
    def test_full_is_observed_range_not_time_or_projection(self):
        table=self.table()
        self.assertEqual(coverage(table)['supported_cells'],0)
        for cad in (80,85,90):
            for watt in (150,180,210,240,270):
                table['cells'][((cad-60)//5)*30+watt//30]=[1000,1]
        self.assertFalse(coverage(table)['fully_supported_tested_range'])
        for cell in table['cells']:
            if cell[0]!=-32768: cell[1]=2
        self.assertTrue(coverage(table)['fully_supported_tested_range'])
        self.assertEqual(coverage(table)['supported_cells'],15)
    def test_snapshot_preload_and_pause_do_not_restart_process(self):
        table=self.table(); calls=[]
        class Bridge:
            def __init__(self,*a,**kw): calls.append('init')
            def load_power_table(self,t): calls.append(('load',digest(t)))
            def power_table(self): calls.append('snapshot'); return table
            def control(self,p): calls.append(('control',p))
            def tick(self,n,*a,**kw): calls.append(('tick',n)); return n
        snapshots=[]
        bridge=observed_bridge(SimpleNamespace(Bridge=Bridge),snapshots,initial_table=table,
            snapshot_times=(0,60),pause_events=((30,False),(45,True)))()
        for stamp in (1000,31000,46000,61000,61000): bridge.tick(stamp)
        self.assertEqual(calls.count('init'),1)
        self.assertEqual(calls[1],('load',digest(table)))
        self.assertEqual([s['time_s'] for s in snapshots],[0,60])
        self.assertIn(('control',bytes([8,2])),calls)
        self.assertIn(('control',bytes([7])),calls)
    def test_log_counts_have_explicit_meaning_and_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'firmware.log'
            path.write_text('[1000](PTable): Raw observation: watts=150\n[2000](ERG): Kp: 2.0 (table)\n[3000](ERG): Kp: 2.0 (fallback: sparse)\n')
            self.assertEqual(log_events(path),[{'time_s':0,'kind':'learning_observation'},
                {'time_s':1,'kind':'table_gain_log'},{'time_s':2,'kind':'fallback_gain_log'}])

if __name__=='__main__': unittest.main()
