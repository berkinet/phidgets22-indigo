import pathlib
import sys
import unittest


SERVER_PLUGIN = (pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" /
                 "Contents" / "Server Plugin")
sys.path.insert(0, str(SERVER_PLUGIN))

from sensirion_gas_index_algorithm import (  # noqa: E402
    ALGORITHM_TYPE_NOX, ALGORITHM_TYPE_VOC, GasIndexAlgorithm)


class GasIndexAlgorithmTests(unittest.TestCase):
    def test_voc_reference_reaches_expected_baseline(self):
        algorithm = GasIndexAlgorithm(ALGORITHM_TYPE_VOC)
        outputs = [algorithm.process(1337) for _ in range(201)]

        self.assertEqual(outputs[:46], [0] * 46)
        self.assertEqual(outputs[-1], 100)

    def test_nox_reference_reaches_expected_baseline(self):
        algorithm = GasIndexAlgorithm(ALGORITHM_TYPE_NOX)
        outputs = [algorithm.process(1337) for _ in range(201)]

        self.assertEqual(outputs[:46], [0] * 46)
        self.assertEqual(outputs[-1], 1)

    def test_vendored_module_retains_license_and_upstream_version(self):
        source = (SERVER_PLUGIN / "sensirion_gas_index_algorithm.py").read_text()

        self.assertIn("SPDX-License-Identifier: BSD-3-Clause", source)
        self.assertEqual(GasIndexAlgorithm.get_version(), "3.2.0")


if __name__ == "__main__":
    unittest.main()
