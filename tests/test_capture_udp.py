import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("capture_udp", Path(__file__).parents[1] / "tools" / "capture_udp.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class CaptureUdpTests(unittest.TestCase):
    def test_payload_is_lossless_and_equal_values_not_deduplicated(self):
        payload = b"[  1000][E](Main): W=100 C=80 H=0 G=1 R=0 P=-3->9\xff"
        a = capture.record_datagram(payload, 20, 0)
        b = capture.record_datagram(payload, 30, 1)
        self.assertEqual(base64.b64decode(a["payload_base64"]), payload)
        self.assertEqual(a["kind"], "status_snapshot")
        self.assertEqual(a["firmware_log_ms"], 1000)
        self.assertNotEqual(a["sequence"], b["sequence"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            path.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n")
            self.assertEqual(capture.inspect(path)["datagrams"], 2)

    def test_processing_not_arrival(self):
        entry = capture.record_datagram(b"[23][E](BLE_Common): 00 00<- 1818 | 2a63 | sensor[ PW(100) POS(2) ]", 10, 0)
        self.assertEqual(entry["kind"], "sensor_processing")
        self.assertNotIn("ble_arrival_ms", entry)
        entry = capture.record_datagram(b"[25][E](FTMS): ERG Mode Target: 120", 20, 1)
        self.assertEqual(entry["kind"], "target_processing")

    def test_gaps_and_reset_are_warnings(self):
        records = [capture.record_datagram(f"[{stamp}][E](Main): W=100 C=80 H=0 G=1 R=0 P=3->9".encode(), i, i)
                   for i, stamp in enumerate((1000, 5000, 10))]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            path.write_text("\n".join(map(json.dumps, records)) + "\n")
            report = capture.inspect(path)
            self.assertEqual(report["backward_firmware_times"], 1)
            self.assertEqual(report["status_gaps_over_2500ms"], 1)

    def test_unstructured_packet_still_preserved(self):
        entry = capture.record_datagram(b"\x00\xff", 0, 0)
        self.assertIsNone(entry["firmware_log_ms"])
        self.assertEqual(entry["kind"], "other_log")


if __name__ == "__main__":
    unittest.main()
