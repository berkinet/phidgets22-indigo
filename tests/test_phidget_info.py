import pathlib
import sys
import unittest
from enum import IntEnum
from unittest import mock


SERVER_PLUGIN = (pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" /
                 "Contents" / "Server Plugin")
sys.path.insert(0, str(SERVER_PLUGIN))

import PhidgetInfo


class PhidgetInfoTests(unittest.TestCase):
    def test_runtime_enum_menus_preserve_stable_labels(self):
        info = PhidgetInfo.PhidgetInfo()

        voltage = dict(info.getPhidgetTypeMenu(["VoltageSensorType"]))
        ratio = dict(info.getPhidgetTypeMenu(["VoltageRatioSensorType"]))

        self.assertEqual(len(voltage), 41)
        self.assertEqual(len(ratio), 49)
        self.assertEqual(voltage[11301], "1130 - pH Adapter")
        self.assertEqual(
            voltage[41160], "VCP4116 - +-100A DC Current Transducer")
        self.assertEqual(ratio[11011], (
            "1101 - IR Distance Adapter, with Sharp Distance Sensor "
            "2D120X (4-30cm)"))

    def test_new_sdk_enum_values_appear_without_regenerating_metadata(self):
        supplies = dict(PhidgetInfo.PhidgetInfo().getPhidgetTypeMenu(
            ["PowerSupply"]))

        self.assertEqual(supplies[4], "The sensor is provided with 5 volts")

    def test_installed_enum_values_have_reviewed_stable_labels(self):
        for class_name, enum_type in PhidgetInfo.ENUM_TYPES.items():
            with self.subTest(class_name=class_name):
                self.assertEqual(
                    set(enum_type.__members__),
                    set(PhidgetInfo.LABEL_OVERRIDES[class_name]))

    def test_unknown_enum_names_receive_readable_fallback_labels(self):
        class FutureMode(IntEnum):
            INPUT_MODE_FUTURE_SENSOR = 99

        with mock.patch.dict(
                PhidgetInfo.ENUM_TYPES, {"FutureMode": FutureMode}):
            menu = PhidgetInfo.PhidgetInfo().getPhidgetTypeMenu(["FutureMode"])

        self.assertEqual(menu, [(99, "Future Sensor")])


if __name__ == "__main__":
    unittest.main()
