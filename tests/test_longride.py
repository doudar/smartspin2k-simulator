import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from ss2k_sim.longride import long_workout, probe, coverage, observed_bridge, log_events, digest, sprint_windows, sprint_block, sprint_response, TRAINING_WATTS, TRAINING_CADENCES

class LongRideTests(unittest.TestCase):
    def table(self):
        return {'cadence_min':60,'cadence_increment':5,'watt_increment':30,'columns':30,
                'rows':10,'cells':[[-32768,0] for _ in range(300)]}
    def test_continuous_exact_duration_and_identical_probes(self):
        for minutes in (30,45,60,90):
            workout,windows=long_workout(minutes)
            self.assertEqual(workout.duration,minutes*60)
            self.assertEqual(len(windows),3)
            for window in windows:
                for t in range(360):
                    self.assertEqual(workout.at(window['start_s']+t),long_workout(30)[0].at(t))
        with self.assertRaises(ValueError): long_workout(120)
    def test_physical_pause_is_separate_from_identical_probes(self):
        for minutes in (30,45,60,90):
            workout,windows=long_workout(minutes,stress=True)
            at=minutes*60*.25+30
            self.assertEqual(workout.at(at)[1],0)
            self.assertEqual(workout.at(at+59)[1],0)
            self.assertGreater(workout.at(at+60)[1],0)
            self.assertEqual(workout.duration,minutes*60)
            normal,_=long_workout(minutes)
            for w in windows:
                for t in range(360): self.assertEqual(workout.at(w['start_s']+t),normal.at(w['start_s']+t))
    def test_sprints_have_exact_timing_and_identical_cadence_plan(self):
        from ss2k_sim.cadence import CadencePlan
        for minutes in (30,45,60,90):
            workout,probes=long_workout(minutes,stress=True)
            blocks=sprint_windows(minutes); plan=CadencePlan(workout)
            self.assertEqual(workout.duration,minutes*60)
            self.assertEqual(sum(s.duration_s for s in workout.segments if s.start_w==500),75)
            for block in blocks:
                start=block['start_s']; end=start+85
                for t,target in ((0,100),(29.98,100),(30,500),(54.98,500),(55,100),(84.98,100)):
                    self.assertEqual(workout.at(start+t),(target,85))
                for t in range(85):
                    self.assertEqual(plan.at(start+t)[:2],plan.at(blocks[0]['start_s']+t)[:2])
                for probe in probes:
                    self.assertTrue(end<=probe['start_s'] or start>=probe['start_s']+360)
                for a,b in ((minutes*60*.25,minutes*60*.25+12),(minutes*60*.25+30,minutes*60*.25+90)):
                    self.assertTrue(end<=a or start>=b)
    def test_missed_sprint_cannot_hide_in_long_ride_average(self):
        import numpy as np
        times=np.arange(0,85,.02); trace=np.zeros((len(times),15));trace[:,0]=times
        trace[:,2]=100;trace[:,14]=100
        report=sprint_response(trace)
        self.assertIsNone(report['rise_to_450w_s'])
        self.assertIsNone(report['sprint_settling_s'])
        self.assertAlmostEqual(report['outside_20w_s'],25)
        self.assertEqual(report['recovery_settling_s'],0)
        trace[(times>=32)&(times<55),2]=530
        report=sprint_response(trace)
        self.assertEqual(report['rise_to_450w_s'],2)
        self.assertEqual(report['peak_overshoot_w'],30)
        self.assertAlmostEqual(report['above_520w_s'],23)
        self.assertIsNone(report['sprint_settling_s'])
    def test_sprint_recovery_and_five_second_dwell(self):
        import numpy as np
        times=np.arange(0,85,.02); trace=np.zeros((len(times),15));trace[:,0]=times;trace[:,2]=100
        trace[(times>=30)&(times<35),2]=400
        trace[(times>=35)&(times<55),2]=500
        trace[(times>=55)&(times<59),2]=200
        report=sprint_response(trace)
        self.assertAlmostEqual(report['sprint_settling_s'],5)
        self.assertAlmostEqual(report['recovery_settling_s'],4)
        self.assertAlmostEqual(report['recovery_above_120w_s'],4)
    def test_full_is_observed_range_not_time_or_projection(self):
        table=self.table()
        self.assertEqual(coverage(table)['supported_cells'],0)
        for cad in TRAINING_CADENCES:
            for watt in TRAINING_WATTS:
                table['cells'][((cad-60)//5)*30+watt//30]=[1000,1]
        self.assertFalse(coverage(table)['fully_supported_tested_range'])
        for cell in table['cells']:
            if cell[0]!=-32768: cell[1]=2
        self.assertTrue(coverage(table)['fully_supported_tested_range'])
        self.assertEqual(coverage(table)['supported_cells'],45)
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
