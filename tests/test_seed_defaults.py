"""Production experiment defaults are seed 7; diagnostic overrides stay explicit."""
import importlib.util
import inspect
from pathlib import Path
import unittest
from ss2k_sim.cli import parser
from ss2k_sim.longride import parser as long_parser
from ss2k_sim.runner import run
from ss2k_sim.model import Bike, Rider

class SeedDefaultsTests(unittest.TestCase):
    def test_short_default_and_explicit_diagnostic_override(self):
        args=['compare','--firmware-root','a','--candidate-root','c','--baseline-root','b','--output','o']
        self.assertEqual(parser().parse_args(args).seeds,[7])
        self.assertEqual(parser().parse_args(args+['--seeds','27']).seeds,[27])
    def test_long_default(self):
        for command in ('train','compare'):
            args=long_parser().parse_args([command,'--firmware-root','a','--candidate-root','c','--output','o'])
            self.assertEqual(args.seeds,[7])
    def test_low_level_rng_defaults(self):
        for obj in (run,Bike,Rider):
            self.assertEqual(inspect.signature(obj).parameters['seed'].default,7)
    def test_published_long_matrix_is_nine_seed_seven_cases(self):
        path=Path(__file__).resolve().parents[1]/'dashboard/longride_experiment.py'
        spec=importlib.util.spec_from_file_location('long_experiment',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(len(module.CASES),9)
        self.assertEqual({r['seed'] for r in module.CASES},{7})

if __name__=='__main__': unittest.main()
