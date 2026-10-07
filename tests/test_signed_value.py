import pathlib
import sys
import types
import unittest
from unittest import mock

SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))
from signed_value import add_signed_value_state, format_signed_value, initialize_signed_value
from state_publisher import update_indigo_state


class SignedValueTests(unittest.TestCase):
    def owner(self, source="cmBelowFull", places=2):
        return types.SimpleNamespace(
            NUMERIC_DISPLAY=True, getDeviceDisplayStateId=lambda: source,
            customState="cmBelowFull", customOutputType="number",
            decimalPlaces=places, indigoDevice=mock.Mock(), logger=mock.Mock())

    def enable(self, owner):
        plugin = mock.Mock()
        plugin.getDeviceStateDictForStringType.side_effect = lambda *args: args
        states = []
        add_signed_value_state(plugin, owner, states)
        return states

    def test_startup_uses_retained_value_silently_then_accepts_live_reading(self):
        owner = self.owner()
        self.enable(owner)
        owner.indigoDevice.states = {"cmBelowFull": -7.6433, "signedValue": ""}
        initialize_signed_value(owner)
        owner.indigoDevice.updateStateOnServer.assert_called_once_with(
            "signedValue", value="-7.64", triggerEvents=False)
        self.assertEqual(owner.indigoDevice.states["cmBelowFull"], -7.6433)
        update_indigo_state(owner, "cmBelowFull", 1.23)
        owner.indigoDevice.updateStateOnServer.assert_called_with(
            "signedValue", value="+1.23", triggerEvents=False)
        update_indigo_state(owner, "cmBelowFull", 2.34)
        owner.indigoDevice.updateStateOnServer.assert_called_with(
            "signedValue", value="+2.34", triggerEvents=True)

    def test_startup_missing_invalid_or_nonnumeric_source(self):
        owner = self.owner()
        self.enable(owner)
        for retained in ({}, {"cmBelowFull": None}, {"cmBelowFull": float("nan")},
                         {"cmBelowFull": True}, {"cmBelowFull": "unknown"}):
            owner.indigoDevice.states = retained
            initialize_signed_value(owner)
            owner.indigoDevice.updateStateOnServer.assert_called_with(
                "signedValue", value="", triggerEvents=False)
        owner._signedValueSource = None
        owner.indigoDevice.updateStateOnServer.reset_mock()
        initialize_signed_value(owner)
        owner.indigoDevice.updateStateOnServer.assert_not_called()

    def test_initialization_failure_is_logged_without_aborting_startup(self):
        owner = self.owner()
        self.enable(owner)
        owner.indigoDevice.states = mock.Mock()
        owner.indigoDevice.states.get.side_effect = RuntimeError("read failed")
        initialize_signed_value(owner)
        owner.logger.error.assert_called_once()

    def test_sign_precision_zero_and_invalid_values(self):
        cases = [(7.66, 2, "+7.66"), (-7.66, 2, "-7.66"),
                 (0, 2, "+0.00"), (-0.004, 2, "+0.00"),
                 (-0.006, 2, "-0.01"), (7.6, 0, "+8"),
                 (7.123456789, -1, "+7.123456789"),
                 (-0.0, -1, "+0.0"), (12345678901234567890, -1, "+12345678901234567890"),
                 (False, 2, ""), ("invalid", 2, ""),
                 (float("nan"), 2, ""), (float("inf"), 2, "")]
        for value, places, expected in cases:
            with self.subTest(value=value, places=places):
                self.assertEqual(format_signed_value(value, places), expected)

    def test_selected_numeric_state_only_and_trigger_semantics(self):
        owner = self.owner()
        self.assertEqual(self.enable(owner), [("signedValue", "Signed display value (+/-)", "signedValue")])
        update_indigo_state(owner, "voltageRatio", 0.99)
        self.assertEqual(owner.indigoDevice.updateStateOnServer.call_count, 1)
        update_indigo_state(owner, "cmBelowFull", -7.6433, decimalPlaces=2)
        owner.indigoDevice.updateStateOnServer.assert_called_with("signedValue", value="-7.64", triggerEvents=False)
        update_indigo_state(owner, "cmBelowFull", 2.125, decimalPlaces=3, triggerEvents=False)
        owner.indigoDevice.updateStateOnServer.assert_called_with("signedValue", value="+2.125", triggerEvents=False)
        update_indigo_state(owner, "cmBelowFull", 1)
        owner.indigoDevice.updateStateOnServer.assert_called_with("signedValue", value="+1.00", triggerEvents=True)

    def test_reconfiguration_switches_source_and_excludes_nonnumeric_formulas(self):
        owner = self.owner("tempC")
        self.enable(owner)
        owner.getDeviceDisplayStateId = lambda: "tempF"
        self.enable(owner)
        update_indigo_state(owner, "tempC", 20)
        self.assertEqual(owner.indigoDevice.updateStateOnServer.call_count, 1)
        update_indigo_state(owner, "tempF", 68)
        owner.indigoDevice.updateStateOnServer.assert_called_with("signedValue", value="+68.00", triggerEvents=False)
        owner.getDeviceDisplayStateId = lambda: "cmBelowFull"
        for output_type in ("text", "boolean"):
            owner.customOutputType = output_type
            self.assertEqual(self.enable(owner), [])
            self.assertIsNone(owner._signedValueSource)

    def test_numeric_devices_opt_in_and_other_displays_do_not(self):
        from voltageinput import VoltageInputPhidget
        from voltageratioinput import VoltageRatioInputPhidget
        from temperaturesensor import TemperatureSensorPhidget
        from humiditysensor import HumiditySensorPhidget
        from frequencycounter import FrequencyCounterPhidget
        from bme280 import BME280Phidget
        from sgp41 import SGP41Phidget
        from digitalinput import DigitalInputPhidget
        from digitaloutput import DigitalOutputPhidget
        from rfid import RFIDPhidget
        from lcd import LCDPhidget
        for cls in (VoltageInputPhidget, VoltageRatioInputPhidget, TemperatureSensorPhidget,
                    HumiditySensorPhidget, FrequencyCounterPhidget, BME280Phidget, SGP41Phidget):
            self.assertIs(cls.NUMERIC_DISPLAY, True)
        for cls in (DigitalInputPhidget, DigitalOutputPhidget, RFIDPhidget, LCDPhidget):
            owner = object.__new__(cls)
            self.assertEqual(self.enable(owner), [])

    def test_failed_companion_does_not_fail_original_numeric_publication(self):
        owner = self.owner()
        self.enable(owner)
        owner.indigoDevice.updateStateOnServer.side_effect = [None, RuntimeError("missing\nstate")]
        update_indigo_state(owner, "cmBelowFull", 7.66)
        self.assertIn("cmBelowFull", owner._initializedIndigoStates)
        owner.logger.error.assert_called_once()
        self.assertEqual(owner.logger.error.call_args.args[-1], "missing state")

    def test_reserved_existing_custom_state_is_not_duplicated(self):
        owner = self.owner("signedValue")
        self.assertEqual(self.enable(owner), [])
        self.assertIsNone(owner._signedValueSource)
