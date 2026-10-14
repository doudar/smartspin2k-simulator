import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from ss2k_sim.cadence import CadencePlan
from ss2k_sim.high_power import (diagnostic_workout, phase_response, response_summary,
                                  target_table_support, load_fixture)
from ss2k_sim.longride import long_workout, run_one, coverage, TRAINING_CADENCES, TRAINING_WATTS


class HighPowerTests(unittest.TestCase):
    def trace(self,duration=25):
        trace=np.zeros((duration,15)); trace[:,0]=np.arange(duration)
        trace[:,2]=trace[:,14]=500
        return trace

    def test_exact_published_early_prefix_and_cadence_for_every_target(self):
        published,_=long_workout(90); original_plan=CadencePlan(published)
        for target in (500,700,1000):
            workout=diagnostic_workout(target); plan=CadencePlan(workout)
            self.assertEqual(workout.duration,445)
            for t in np.arange(0,445,.25):
                original=published.at(t)
                self.assertEqual(workout.at(t), (target,85) if 390<=t<415 else original)
                self.assertEqual(plan.at(t)[:2],original_plan.at(t)[:2])
        for target in (240,1001,float('inf'),float('nan')):
            with self.assertRaises(ValueError): diagnostic_workout(target)

    def test_first_crossing_dwell_confirmation_and_final_settle_are_distinct(self):
        trace=self.trace(); trace[:2,2]=400; trace[3:5,2]=530; trace[12:14,2]=540
        response=phase_response(trace,500,0,25)
        band=response['bands']['10']
        self.assertEqual(response['rise_to_90pct_target_s'],2)
        self.assertEqual(band['first_entry_s'],2)
        self.assertEqual(band['first_dwell_entry_s'],5)
        self.assertEqual(band['first_dwell_confirmed_s'],10)
        self.assertEqual(band['final_settling_s'],14)
        self.assertEqual(band['later_excursion_count'],1)
        self.assertEqual(band['later_excursion_s'],2)
        self.assertEqual(band['later_max_absolute_error_w'],40)
        self.assertEqual(band['outside_band_s'],6)
        self.assertEqual(response['peak_overshoot_w'],40)
        self.assertFalse(response['goal']['met'])

    def test_null_if_no_dwell_or_final_run_too_short(self):
        trace=self.trace(); trace[::4,2]=550
        response=phase_response(trace,500,0,25)
        band=response['bands']['10']
        for key in ('first_dwell_entry_s','first_dwell_confirmed_s','final_settling_s',
                    'later_excursion_count','later_excursion_s'):
            self.assertIsNone(band[key])
        self.assertFalse(response['goal']['met'])
        trace[:,2]=500; trace[-2,2]=550
        band=phase_response(trace,500,0,25)['bands']['10']
        self.assertEqual(band['first_dwell_entry_s'],0)
        self.assertIsNone(band['final_settling_s'])
        self.assertEqual(band['later_excursion_count'],1)

    def test_inclusive_band_strict_goal_and_exact_dwell(self):
        trace=self.trace(); trace[:10,2]=550; trace[10:,2]=510
        response=phase_response(trace,500,0,25)
        self.assertEqual(response['bands']['10']['final_settling_s'],10)
        self.assertFalse(response['goal']['met'])
        trace[9,2]=510
        self.assertTrue(phase_response(trace,500,0,25)['goal']['met'])
        trace[:20,2]=550
        self.assertEqual(phase_response(trace,500,0,25)['bands']['10']['final_settling_s'],20)
        trace[20,2]=550
        self.assertIsNone(phase_response(trace,500,0,25)['bands']['10']['final_settling_s'])

    def test_bands_and_signals_are_independent_and_time_weighted(self):
        trace=self.trace(); trace[:,2]=515; trace[:,14]=540
        response=phase_response(trace,500,0,25)
        self.assertIsNone(response['bands']['10']['first_dwell_entry_s'])
        self.assertEqual(response['bands']['20']['first_dwell_entry_s'],0)
        sensor=phase_response(trace,500,0,25,column=14)
        self.assertEqual(sensor['bands']['20']['outside_band_s'],25)
        trace=self.trace(); trace[:,0]=np.arange(25)*.2; trace[:10,2]=550
        response=phase_response(trace,500,0,5,dwell_s=2)
        self.assertAlmostEqual(response['bands']['10']['outside_band_s'],2)
        self.assertAlmostEqual(response['bands']['10']['first_dwell_entry_s'],2)
        self.assertAlmostEqual(response['bands']['10']['first_dwell_confirmed_s'],4)
        self.assertIn('at least 2 s',response['goal']['meaning'])

    def test_invalid_trace_is_not_silently_scored(self):
        trace=self.trace()
        for bad in (trace[1:],trace[::-1],trace[[0,3,4]],np.empty((0,15))):
            with self.assertRaises(ValueError): phase_response(bad,500,0,25)
        trace[3,2]=np.nan
        with self.assertRaises(ValueError): phase_response(trace,500,0,25)

    def table(self):
        table={'cadence_min':60,'cadence_increment':5,'watt_increment':30,
               'columns':30,'rows':10,'cells':[[-32768,0] for _ in range(300)]}
        for cad in TRAINING_CADENCES:
            for watts in TRAINING_WATTS:
                table['cells'][(cad-60)//5*30+watts//30]=[1000,2]
        return table

    def test_full_grid_stays_45_cells_and_high_targets_are_honest(self):
        table=self.table()
        self.assertEqual(coverage(table)['tested_range_required'],45)
        self.assertTrue(target_table_support(table,500)['declared_sprint_brackets_supported'])
        self.assertFalse(target_table_support(table,700)['declared_sprint_brackets_supported'])
        high=target_table_support(table,1000)
        self.assertFalse(high['within_table_axis'])
        self.assertFalse(high['declared_sprint_brackets_supported'])
        self.assertEqual(high['table_max_w'],870)
        self.assertEqual(coverage(table)['supported_cells'],45)

    def test_summary_covers_recovery_and_unchanged_low_targets(self):
        workout=diagnostic_workout(700)
        trace=np.zeros((445,15)); trace[:,0]=np.arange(445)
        trace[:,1]=[workout.at(t)[0] for t in trace[:,0]]
        trace[:,2]=trace[:,14]=trace[:,1]
        response=response_summary(trace,700,[{'time_s':390,'table':self.table()}])
        for signal in response['signals'].values():
            self.assertEqual(len(signal['low_power_prefix']),6)
            self.assertTrue(all(p['target_w']<=240 for p in signal['low_power_prefix']))
            self.assertEqual(signal['sprint']['rise_threshold_w'],630)
            self.assertEqual(signal['recovery']['bands']['10']['final_settling_s'],0)
            self.assertNotIn('rise_to_90pct_target_s',signal['recovery'])


ROOT=Path(os.environ['SS2K_FIRMWARE_ROOT']) if os.environ.get('SS2K_FIRMWARE_ROOT') else None

@unittest.skipUnless(ROOT and shutil.which('g++') and shutil.which('gcc'), 'Trusted firmware adapter and native compilers required')
class HighPowerIngressTests(unittest.TestCase):
    def test_1000w_target_and_read_only_sprint_snapshot(self):
        from ss2k_sim.adapter import load_adapter
        from ss2k_sim.model import BikeConfig
        from ss2k_sim.workout import Segment, Workout
        adapter,_=load_adapter(ROOT)
        profile=json.loads((Path(__file__).parents[1]/'ss2k_sim/profiles/ride_20260927.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); exe=adapter.build(folder/'build',packet_ingress=True)
            # Boundary contract only; full diagnostic duration is separately tested.
            workout=Workout([Segment(1,100,100,85),Segment(1,1000,1000,85),Segment(1,100,100,85)])
            trace,meta,score,snapshots=run_one(adapter,exe,BikeConfig(**profile['bike']),profile,
                folder/'ride',workout,7,extra_snapshot_times=(1,))
            packets=json.loads((folder/'ride/ftms_control_packets.json').read_text())
            targets=[p['payload_hex'] for p in packets if p['payload_hex'].startswith('05')]
            self.assertEqual(targets,['056400','05e803','056400'])
            self.assertEqual([s['time_s'] for s in snapshots],[0,1,3])
            self.assertEqual(meta['packet_ingress_evidence']['rejected'],0)
            self.assertEqual(meta['controller_processes'],1)
            self.assertEqual(sum(trace[:,1]==1000),50)

if __name__=='__main__': unittest.main()
