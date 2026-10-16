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
import adapter_gpio


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

    def test_digital_input_option_logs_each_raw_callback_before_update(self):
        wrapper = object.__new__(digitalinput.DigitalInputPhidget)
        wrapper.logRawStateChanges = True
        wrapper._rawStateChangeSequence = 0
        wrapper.indigoDevice = mock.Mock(name="indigo_device")
        wrapper.indigoDevice.name = "GiBiDi Lock 1"
        wrapper.indigoDevice.id = 42
        wrapper.channelInfo = mock.Mock(
            serialNumber=12345, hubPort=-1, channel=7)
        wrapper.updateIndigoStatus = mock.Mock()

        with mock.patch.object(digitalinput.Log, "log") as log:
            wrapper.onStateChangeHandler(object(), True)
            wrapper.onStateChangeHandler(object(), False)

        self.assertEqual(wrapper._rawStateChangeSequence, 2)
        self.assertEqual(log.call_count, 2)
        self.assertIn("sequence=1 state=True", log.call_args_list[0].args[1])
        self.assertIn("sequence=2 state=False", log.call_args_list[1].args[1])
        self.assertEqual(
            wrapper.updateIndigoStatus.call_args_list,
            [mock.call(True), mock.call(False)])

    def test_digital_input_option_disabled_skips_raw_callback_log(self):
        wrapper = object.__new__(digitalinput.DigitalInputPhidget)
        wrapper.logRawStateChanges = False
        wrapper._rawStateChangeSequence = 0
        wrapper.updateIndigoStatus = mock.Mock()

        with mock.patch.object(digitalinput.Log, "log") as log:
            wrapper.onStateChangeHandler(object(), True)

        log.assert_not_called()
        wrapper.updateIndigoStatus.assert_called_once_with(True)

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

    def test_frequency_counter_publishes_session_cumulative_count(self):
        wrapper = object.__new__(frequencycounter.FrequencyCounterPhidget)
        wrapper.indigoDevice = mock.Mock()
        wrapper.decimalPlaces = 2
        phidget = mock.Mock()
        phidget.getCount.side_effect = [100, 102, 105]

        for interval_count in (1, 2, 3):
            wrapper.onCountChangeHandler(phidget, interval_count, 32.0)

        count_updates = [call for call in wrapper.indigoDevice.updateStateOnServer.call_args_list
                         if call.args[0] == "count"]
        self.assertEqual(
            count_updates,
            [mock.call("count", value=100, triggerEvents=False),
             mock.call("count", value=102, triggerEvents=True),
             mock.call("count", value=105, triggerEvents=True)])

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

    def test_digital_output_does_not_read_status_after_failed_async_write(self):
        wrapper = object.__new__(digitaloutput.DigitalOutputPhidget)
        wrapper.logger = mock.Mock()
        wrapper.updateIndigoStatus = mock.Mock()

        wrapper.asyncSetResult(None, 52, "Device not Attached")

        wrapper.logger.error.assert_called_once()
        wrapper.updateIndigoStatus.assert_not_called()

    def test_digital_output_async_context_survives_overlapping_requests(self):
        wrapper = object.__new__(digitaloutput.DigitalOutputPhidget)
        wrapper.logger = mock.Mock()
        wrapper.updateIndigoStatus = mock.Mock()
        wrapper._identity = mock.Mock(return_value="device='Close door' id=354290814 server=CM-Poulailler serial=744571 hubPort=5 channel=0")
        on = wrapper._result_callback("Turn On", True)
        off = wrapper._result_callback("Turn Off", False)
        off(None, 52, "Device not Attached")
        on(None, 52, "Device not Attached")
        messages = wrapper.logger.error.call_args_list
        self.assertEqual(messages[0].args[-2:], ("Turn Off", False))
        self.assertEqual(messages[1].args[-2:], ("Turn On", True))
        self.assertIn("354290814", messages[0].args[3])
        wrapper.updateIndigoStatus.assert_not_called()
        on(None, 0, "OK")
        wrapper.updateIndigoStatus.assert_called_once()

    def test_repeated_detached_async_errors_are_suppressed_until_recovery(self):
        wrapper = object.__new__(digitaloutput.DigitalOutputPhidget)
        wrapper.logger = mock.Mock()
        wrapper.updateIndigoStatus = mock.Mock()
        wrapper._identity = mock.Mock(return_value="Close door")
        for _ in range(100):
            wrapper.asyncSetResult(None, 52, "Device not Attached", "Turn Off", False)
        wrapper.logger.error.assert_called_once()
        wrapper.updateIndigoStatus.assert_not_called()
        wrapper.asyncSetResult(None, 0, "OK", "Turn Off", False)
        wrapper.asyncSetResult(None, 52, "Device not Attached", "Turn Off", False)
        self.assertEqual(wrapper.logger.error.call_count, 2)
        wrapper._state = "detached"
        with mock.patch.object(digitaloutput.PhidgetBase, "onAttachHandler",
                               side_effect=lambda ph: setattr(wrapper, '_state', 'attached')):
            wrapper.onAttachHandler(object())
        wrapper.asyncSetResult(None, 52, "Device not Attached", "Turn Off", False)
        self.assertEqual(wrapper.logger.error.call_count, 3)

    def test_first_attachment_write_failures_warn_then_promote_after_startup_grace(self):
        for output_type in (digitaloutput.DigitalOutputPhidget,
                            adapter_gpio.AdapterGPIOOutputPhidget):
            with self.subTest(output=output_type.__name__):
                wrapper = object.__new__(output_type)
                wrapper.logger = mock.Mock()
                wrapper.phidget = mock.Mock()
                wrapper.updateIndigoStatus = mock.Mock()
                wrapper._identity = lambda: "Door output"
                wrapper._state = "starting"
                wrapper._attach_count = 0
                wrapper._started_at = 100
                wrapper._detached_at = -90000  # A restored outage cannot shorten grace.
                wrapper.initial_connection_timeout = 30
                with mock.patch.object(digitaloutput.time, "monotonic", return_value=101):
                    for _ in range(20):
                        wrapper.asyncSetResult(None, 52, "Device not Attached", "Turn Off", False)
                wrapper.logger.warning.assert_called_once()
                wrapper.logger.error.assert_not_called()
                message = wrapper.logger.warning.call_args.args
                self.assertIn("Command was not applied or queued", message[0])
                self.assertEqual(message[-2:], ("Turn Off", False))
                with mock.patch.object(digitaloutput.time, "monotonic", return_value=130):
                    for _ in range(20):
                        wrapper.asyncSetResult(None, 52, "Device not Attached", "Turn Off", False)
                wrapper.logger.error.assert_called_once()
                wrapper.updateIndigoStatus.assert_not_called()
                wrapper.phidget.assert_not_called()
                self.assertEqual(wrapper.phidget.mock_calls, [])

    def test_startup_grace_never_masks_operational_or_other_write_failures(self):
        for count, result in ((1, 52), (0, 3)):
            with self.subTest(previous_attachments=count, result=result):
                wrapper = object.__new__(digitaloutput.DigitalOutputPhidget)
                wrapper.logger = mock.Mock()
                wrapper.updateIndigoStatus = mock.Mock()
                wrapper._identity = lambda: "Door output"
                wrapper._state = "detached"
                wrapper._attach_count = count
                wrapper._started_at = 100
                wrapper.initial_connection_timeout = 30
                with mock.patch.object(digitaloutput.time, "monotonic", return_value=101):
                    wrapper.asyncSetResult(None, result, "Write failed", "Turn Off", False)
                wrapper.logger.error.assert_called_once()
                wrapper.logger.warning.assert_not_called()
                wrapper.updateIndigoStatus.assert_not_called()

    def test_async_completion_from_old_lifecycle_is_ignored(self):
        wrapper = object.__new__(digitaloutput.DigitalOutputPhidget)
        wrapper._identity = lambda: "Door"
        wrapper._lifecycle_epoch = 1
        wrapper._state = "attached"
        wrapper.logger = mock.Mock()
        wrapper.updateIndigoStatus = mock.Mock()
        old = wrapper._result_callback("Turn On", True)
        wrapper._lifecycle_epoch = 2
        wrapper._state = "detached"
        wrapper._detached_write_failures = {("Turn Off", "False")}
        old(None, 0, "OK")
        old(None, 52, "Device not Attached")
        self.assertEqual(wrapper._detached_write_failures, {("Turn Off", "False")})
        wrapper.updateIndigoStatus.assert_not_called()
        wrapper.logger.error.assert_not_called()

    def test_repeated_non_detach_errors_are_bounded_but_distinct_errors_visible(self):
        wrapper = object.__new__(digitaloutput.DigitalOutputPhidget)
        wrapper.logger = mock.Mock()
        wrapper.updateIndigoStatus = mock.Mock()
        for _ in range(2):
            wrapper.asyncSetResult(None, 3, "Timed Out", "Turn Off", False)
        self.assertEqual(wrapper.logger.error.call_count, 1)
        wrapper.asyncSetResult(None, 2, "Invalid argument", "Turn Off", False)
        self.assertEqual(wrapper.logger.error.call_count, 2)
        wrapper.updateIndigoStatus.assert_not_called()

    def test_successful_writes_do_not_rearm_a_continuing_status_read_fault(self):
        wrapper = object.__new__(digitaloutput.DigitalOutputPhidget)
        wrapper.logger = mock.Mock()
        wrapper._identity = lambda: 'Door'
        wrapper.phidget = mock.Mock()
        wrapper.phidget.getDutyCycle.side_effect = RuntimeError('cannot read status')
        for _ in range(20):
            wrapper.asyncSetResult(None, 0, 'OK', 'Turn Off', False)
        wrapper.logger.error.assert_called_once()

    def test_adapter_gpio_input_configures_pullup_and_inverts_switch_state(self):
        wrapper = object.__new__(adapter_gpio.AdapterGPIOInputPhidget)
        wrapper.inputMode = "pullup"
        wrapper.inverted = True
        wrapper.debounceMilliseconds = 0
        wrapper.updateIndigoStatus = mock.Mock()
        phidget = mock.Mock()

        wrapper.configureAttachedPhidget(phidget)
        wrapper.onStateChangeHandler(phidget, False)

        phidget.setInputMode.assert_called_once_with(
            adapter_gpio.InputMode.INPUT_MODE_PULLUP)
        wrapper.updateIndigoStatus.assert_called_once_with(True)

    def test_adapter_gpio_output_publishes_only_relay_state(self):
        wrapper = object.__new__(adapter_gpio.AdapterGPIOOutputPhidget)
        wrapper.phidget = mock.Mock()
        wrapper.phidget.getState.return_value = True
        wrapper.indigoDevice = mock.Mock()

        wrapper.updateIndigoStatus()

        wrapper.indigoDevice.updateStateOnServer.assert_called_once_with(
            "onOffState", value=True, uiValue="on", triggerEvents=False)


if __name__ == "__main__":
    unittest.main()
