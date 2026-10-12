import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ss2k_sim.adapter import load_adapter, ADAPTER_FILES
from ss2k_sim.model import Bike, BikeConfig
from ss2k_sim.ble.protocol import CrankState, encode_csc, encode_power


class PackageContractTests(unittest.TestCase):
    def test_cli_help_without_firmware_or_bluetooth(self):
        result = subprocess.run([sys.executable, '-m', 'ss2k_sim', '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('compare', result.stdout)

    def test_missing_adapter_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'lacks native packet adapter'):
                load_adapter(folder)

    def test_adapter_hash_checked_before_executing_code(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter = Path(folder)/'scripts/erg_sim'
            adapter.mkdir(parents=True)
            for name in ADAPTER_FILES:
                (adapter/name).write_text('raise AssertionError("must not execute")')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                load_adapter(folder, '0'*64)

    def test_plant_never_uses_target_watts(self):
        # The plant API has only elapsed time, physical pulses and rider cadence.
        import inspect
        self.assertEqual(list(inspect.signature(Bike.advance).parameters), ['self', 'now', 'dt', 'pulses', 'cadence'])
        bike = Bike(BikeConfig(noise_w=0), 10000)
        before = bike.position
        bike.advance(.02, .02, 37, 80)
        self.assertEqual(bike.position, before+37)

    def test_sensor_encoding_is_standard_binary(self):
        crank = CrankState()
        crank.advance(1, 60)
        self.assertEqual(encode_csc(crank), bytes.fromhex('0201000004'))
        self.assertEqual(encode_power(250), bytes.fromhex('0000fa00'))


if __name__ == '__main__':
    unittest.main()
