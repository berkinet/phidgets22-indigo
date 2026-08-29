import pathlib
import sys
import types
import unittest
from unittest import mock


SERVER_PLUGIN = (pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" /
                 "Contents" / "Server Plugin")
sys.path.insert(0, str(SERVER_PLUGIN))

indigo = sys.modules.setdefault("indigo", types.ModuleType("indigo"))
indigo.List = list
indigo.Dict = dict
indigo.PluginBase = type("PluginBase", (object,), {"__del__": lambda self: None})

import voltageinput
import voltageratioinput
from Phidget22.VoltageRatioSensorType import VoltageRatioSensorType
from Phidget22.VoltageSensorType import VoltageSensorType


class FakeChannel(object):
    pass


class SensorFormulaTests(unittest.TestCase):
    def wrapper_arguments(self):
        return {
            "dataInterval": 1000, "sensorValueChangeTrigger": 0.0,
            "customState": "converted", "customFormula": "x * 2 + 1",
            "indigo_plugin": types.SimpleNamespace(
                pluginPrefs={"attachTimeout": "5", "suppressErrors": False}),
            "indigoDevice": mock.Mock(name="Sensor"), "logger": mock.Mock(),
        }

    def test_voltage_input_uses_shared_restricted_formula(self):
        arguments = self.wrapper_arguments()
        arguments.update(sensorType=VoltageSensorType.SENSOR_TYPE_VOLTAGE,
                         voltageChangeTrigger=0.0)
        with mock.patch.object(voltageinput, "VoltageInput",
                               return_value=FakeChannel()):
            wrapper = voltageinput.VoltageInputPhidget(**arguments)

        wrapper.onVoltageChangeHandler(None, 2.5)

        self.assertEqual(
            wrapper.indigoDevice.updateStateOnServer.call_args_list[-1],
            mock.call("converted", value=6.0, decimalPlaces=-1))

    def test_voltage_ratio_input_uses_shared_restricted_formula(self):
        arguments = self.wrapper_arguments()
        arguments.update(
            sensorType=VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO,
            voltageRatioChangeTrigger=0.0)
        with mock.patch.object(voltageratioinput, "VoltageRatioInput",
                               return_value=FakeChannel()):
            wrapper = voltageratioinput.VoltageRatioInputPhidget(**arguments)

        wrapper.setOnVoltageRatioChangeHandler(None, 0.25)

        self.assertEqual(
            wrapper.indigoDevice.updateStateOnServer.call_args_list[-1],
            mock.call("converted", value=1.5, decimalPlaces=-1))

    def test_sensor_formula_rejects_code_execution_during_construction(self):
        arguments = self.wrapper_arguments()
        arguments.update(sensorType=VoltageSensorType.SENSOR_TYPE_VOLTAGE,
                         voltageChangeTrigger=0.0,
                         customFormula="__import__('os').system('id')")
        with (mock.patch.object(voltageinput, "VoltageInput",
                                return_value=FakeChannel()),
              self.assertRaisesRegex(ValueError, "unsupported operation")):
            voltageinput.VoltageInputPhidget(**arguments)

    def test_boolean_sensor_formula_publishes_numeric_on_off(self):
        arguments = self.wrapper_arguments()
        arguments.update(sensorType=VoltageSensorType.SENSOR_TYPE_VOLTAGE,
                         voltageChangeTrigger=0.0,
                         customFormula="x > 2.5")
        with mock.patch.object(voltageinput, "VoltageInput",
                               return_value=FakeChannel()):
            wrapper = voltageinput.VoltageInputPhidget(**arguments)

        wrapper.onVoltageChangeHandler(None, 3.0)

        self.assertEqual(
            wrapper.indigoDevice.updateStateOnServer.call_args_list[-1],
            mock.call("converted", value=1.0, decimalPlaces=-1))


if __name__ == "__main__":
    unittest.main()
