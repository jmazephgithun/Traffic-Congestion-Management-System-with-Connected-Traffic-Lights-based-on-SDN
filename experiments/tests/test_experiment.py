import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.analyze_iperf import parse_file, summarize
from tools.analyze_sumo import parse_tripinfo
from scripts.evaluate import parse_seeds


class ExperimentTests(unittest.TestCase):
    def test_seed_ranges_are_deduplicated(self):
        self.assertEqual(parse_seeds("42,1-3,2"), [42, 1, 2, 3])

    def test_sumo_kpis(self):
        xml = '<root><tripinfo duration="10" waitingTime="2" timeLoss="3" routeLength="100" depart="0" arrival="10"/></root>'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trip.xml"; path.write_text(xml)
            result = parse_tripinfo(path)
        self.assertEqual(result["total_vehicles"], 1)
        self.assertEqual(result["mean_speed_mps"], 10.0)

    def test_iperf_server_log(self):
        line = "[  3] 0.0- 1.0 sec  100 KBytes  800 Kbits/sec  0.500 ms 1/100 (1%)\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "iperf.log"; path.write_text(line)
            parsed = parse_file(path)
        result = summarize(parsed["intervals"])
        self.assertEqual(parsed["role_hint"], "server")
        self.assertEqual(result["loss_pct_mean"], 1.0)

    def test_iperf_final_summary_is_not_an_interval(self):
        lines = ("[  1] 0.0000-1.0000 sec  24.4 KBytes   200 Kbits/sec   0.050 ms 0/17 (0%)\n"
                 "[  1] 1.0000-2.0000 sec  24.4 KBytes   200 Kbits/sec   0.070 ms 0/17 (0%)\n"
                 "[  1] 0.0000-120.0000 sec  2.86 MBytes   200 Kbits/sec   0.900 ms 9/2041 (0.44%)\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "iperf.log"; path.write_text(lines)
            parsed = parse_file(path)
        result = summarize(parsed["intervals"])
        self.assertEqual(result["samples"], 2)
        self.assertAlmostEqual(result["jitter_ms_mean"], 0.06)
        self.assertEqual(result["loss_pct_mean"], 0.0)


if __name__ == "__main__":
    unittest.main()
