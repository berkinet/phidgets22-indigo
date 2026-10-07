import pathlib
import sys
import types
import unittest
from unittest import mock
from xml.etree import ElementTree

SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))
from phidget import PhidgetBase
from voltageratioinput import VoltageRatioInputPhidget
from voltageinput import VoltageInputPhidget


class SaturationSuppressionTests(unittest.TestCase):
    def wrapper(self, cls=VoltageRatioInputPhidget, setting=None, sensor=0):
        wrapper = object.__new__(cls)
        device = mock.Mock(pluginProps={})
        device.name = "Pool water level"
        device.id = 422331033
        PhidgetBase.__init__(wrapper, phidget=mock.Mock(), indigoDevice=device,
                             indigo_plugin=mock.Mock(pluginPrefs={}), logger=mock.Mock())
        wrapper._state = "attached"
        wrapper._attach_count = 1
        wrapper.sensorType = sensor
        if setting is not None:
            device.pluginProps["suppressSaturationErrors"] = setting
        return wrapper

    def test_only_opted_in_generic_ratio_devices_suppress_saturation(self):
        cases = [
            (VoltageRatioInputPhidget, None, 0, False),
            (VoltageRatioInputPhidget, False, 0, False),
            (VoltageRatioInputPhidget, "false", 0, False),
            (VoltageRatioInputPhidget, True, 0, True),
            (VoltageRatioInputPhidget, "true", 0, True),
            (VoltageRatioInputPhidget, True, 1101, False),
            (VoltageInputPhidget, True, 0, False),
            (PhidgetBase, True, 0, False),
        ]
        for cls, setting, sensor, suppressed in cases:
            with self.subTest(cls=cls, setting=setting, sensor=sensor):
                wrapper = self.wrapper(cls, setting, sensor)
                wrapper.onErrorHandler(wrapper.phidget, 4105, "Saturation Detected.")
                expected = wrapper.logger.debug if suppressed else wrapper.logger.error
                other = wrapper.logger.error if suppressed else wrapper.logger.debug
                expected.assert_called_once()
                other.assert_not_called()
                self.assertIn("Pool water level", expected.call_args.args[1])
                self.assertEqual(expected.call_args.args[2], " (suppressed)" if suppressed else "")
                wrapper.indigoDevice.updateStateOnServer.assert_not_called()
                wrapper.indigoDevice.setErrorStateOnServer.assert_not_called()
                wrapper.indigo_plugin.triggerEvent.assert_not_called()

    def test_other_errors_remain_visible_and_existing_out_of_range_option_works(self):
        wrapper = self.wrapper(setting=True)
        for code in (4098, 4099, 4103, 4104, 2):
            with self.subTest(code=code):
                wrapper.logger.reset_mock()
                wrapper.onErrorHandler(wrapper.phidget, code, "Other error")
                wrapper.logger.error.assert_called_once()
                wrapper.logger.debug.assert_not_called()
        wrapper.logger.reset_mock()
        wrapper.indigoDevice.pluginProps["suppressErrors"] = True
        wrapper.onErrorHandler(wrapper.phidget, 4103, "Out of range")
        wrapper.logger.debug.assert_called_once()
        wrapper.logger.error.assert_not_called()

    def test_custom_formula_does_not_affect_eligibility_and_sensor_change_disables(self):
        wrapper = self.wrapper(setting=True)
        wrapper.customFormula = "18.76 - 26.67*x"
        wrapper.onErrorHandler(wrapper.phidget, 4105, "Saturation Detected.")
        wrapper.logger.debug.assert_called_once()
        wrapper.logger.reset_mock()
        wrapper.sensorType = 1101
        wrapper.onErrorHandler(wrapper.phidget, 4105, "Saturation Detected.")
        wrapper.logger.error.assert_called_once()
        wrapper.logger.debug.assert_not_called()

    def test_dialog_option_is_default_off_and_only_visible_for_generic_ratio(self):
        root = ElementTree.parse(SERVER_PLUGIN / "Devices.xml").getroot()
        matches = root.findall(".//Field[@id='suppressSaturationErrors']")
        self.assertEqual(len(matches), 1)
        field = root.find("./Device[@id='voltageRatioInput']/ConfigUI/Field[@id='suppressSaturationErrors']")
        self.assertIsNotNone(field)
        self.assertEqual(field.get("defaultValue").lower(), "false")
        self.assertEqual(field.get("visibleBindingId"), "voltageRatioSensorType")
        self.assertEqual(field.get("visibleBindingValue"), "0")
        self.assertIn("does not extend the measurement range", field.findtext("Description"))
