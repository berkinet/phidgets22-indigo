import pathlib
import sys
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))

import digitalinput
import digitaloutput
import frequencycounter


class FakeFrequencyCounter(object):
    def __init__(self):
        self.handlers = {}

    def __getattr__(self, name):
        if name.startswith("setOn") and name.endswith("Handler"):
            return lambda handler: self.handlers.__setitem__(name, handler)
        raise AttributeError(name)


class DeviceWrapperTests(unittest.TestCase):
    def test_digital_input_uses_declared_display_state(self):
        wrapper = object.__new__(digitalinput.DigitalInputPhidget)

        self.assertEqual(wrapper.getDeviceDisplayStateId(), "onOffState")

    def test_frequency_counter_registers_frequency_and_count_handlers(self):
        wrapper = object.__new__(frequencycounter.FrequencyCounterPhidget)
        wrapper.phidget = FakeFrequencyCounter()

        wrapper.addPhidgetHandlers()

        self.assertEqual(
            wrapper.phidget.handlers["setOnFrequencyChangeHandler"].__func__,
            frequencycounter.FrequencyCounterPhidget.onFrequencyChangeHandler)
        self.assertEqual(
            wrapper.phidget.handlers["setOnCountChangeHandler"].__func__,
            frequencycounter.FrequencyCounterPhidget.onCountChangeHandler)

    def test_digital_output_refreshes_state_after_successful_attach(self):
        wrapper = object.__new__(digitaloutput.DigitalOutputPhidget)
        wrapper._state = "starting"
        wrapper.updateIndigoStatus = mock.Mock()

        def complete_attach(instance, phidget):
            instance._state = "attached"

        with mock.patch.object(digitaloutput.PhidgetBase, "onAttachHandler",
                               autospec=True, side_effect=complete_attach):
            wrapper.onAttachHandler(object())

        wrapper.updateIndigoStatus.assert_called_once_with()

    def test_digital_output_does_not_refresh_after_failed_attach(self):
        wrapper = object.__new__(digitaloutput.DigitalOutputPhidget)
        wrapper._state = "starting"
        wrapper.updateIndigoStatus = mock.Mock()

        def fail_attach(instance, phidget):
            instance._state = "detached"

        with mock.patch.object(digitaloutput.PhidgetBase, "onAttachHandler",
                               autospec=True, side_effect=fail_attach):
            wrapper.onAttachHandler(object())

        wrapper.updateIndigoStatus.assert_not_called()


if __name__ == "__main__":
    unittest.main()
