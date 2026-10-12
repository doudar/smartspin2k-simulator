"""Real FTMS target commands and production sensitivity initialization contract."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from ss2k_sim.adapter import load_adapter
from ss2k_sim.longride import run_one, sprint_block
from ss2k_sim.model import BikeConfig
from ss2k_sim.workout import Workout

ROOT=Path(os.environ['SS2K_FIRMWARE_ROOT']) if os.environ.get('SS2K_FIRMWARE_ROOT') else None

@unittest.skipUnless(ROOT and shutil.which('g++') and shutil.which('gcc'), 'Trusted firmware adapter and native compilers required')
class SprintIngressTests(unittest.TestCase):
    def test_exact_successful_ftms_commands_and_three_actual_sensitivities(self):
        adapter,_=load_adapter(ROOT)
        profile=json.loads((Path(__file__).parents[1]/'ss2k_sim/profiles/ride_20260927.json').read_text())
        config=BikeConfig(**profile['bike'])
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);exe=adapter.build(folder/'build',packet_ingress=True)
            traces=[]
            for sensitivity in (3,5,10):
                dest=folder/str(sensitivity)
                window={'name':'test','start_s':0,'duration_s':85,'sprint_start_s':30,'recovery_start_s':55,'cadence_rpm':85}
                trace,meta,score,_=run_one(adapter,exe,config,profile,dest,Workout(sprint_block()),7,sprints=[window],sensitivity=sensitivity)
                packets=json.loads((dest/'ftms_control_packets.json').read_text())
                targets=[(p['time_s'],p['payload_hex'],p['response']) for p in packets if p['payload_hex'].startswith('05')]
                self.assertEqual(targets,[(0,'056400','success'),(30,'05f401','success'),(55,'056400','success')])
                self.assertEqual(meta['sensitivity'],sensitivity)
                self.assertEqual(meta['simulation_seconds'],85)
                self.assertEqual(meta['packet_ingress_evidence']['rejected'],0)
                self.assertEqual(meta['controller_processes'],1)
                self.assertEqual(len(score['sprints']),1)
                self.assertEqual(sum(trace[:,1]==500),1250)
                traces.append(trace[:,5].tolist())
            self.assertNotEqual(traces[0],traces[1])
            self.assertNotEqual(traces[1],traces[2])

if __name__=='__main__':unittest.main()
