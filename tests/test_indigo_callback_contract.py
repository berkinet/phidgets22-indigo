import inspect
import pathlib
import sys
import threading
import types
import unittest
from unittest import mock
sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / 'Phidgets22.indigoPlugin/Contents/Server Plugin'))
sys.modules.setdefault('indigo', types.ModuleType('indigo'))
import indigo
from actions import ActionsMixin
from discovery_ui import DiscoveryUiMixin
from error_reporting import runtime_boundary
from adapter_gpio import AdapterGPIOInputPhidget
from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException


class IndigoCallbackContractTests(unittest.TestCase):
    def test_dispatch_argument_counts_and_defaults_match_original_callbacks(self):
        for callback in (ActionsMixin.lcdSetDisplay, ActionsMixin.lcdClear,
                         ActionsMixin.lcdWake, ActionsMixin.actionControlSensor,
                         ActionsMixin.validateActionConfigUi,
                         DiscoveryUiMixin.validateDeviceConfigUi,
                         DiscoveryUiMixin.validatePrefsConfigUi):
            with self.subTest(callback=callback.__name__):
                original = inspect.unwrap(callback)
                self.assertEqual(inspect.getfullargspec(callback), inspect.getfullargspec(original))
                self.assertEqual(callback.__code__.co_argcount, original.__code__.co_argcount)
                self.assertEqual(callback.__defaults__, original.__defaults__)

    def test_indigo_style_action_dispatch_uses_action_and_optional_device(self):
        plugin = types.SimpleNamespace(logger=mock.Mock(), _lcdForAction=mock.Mock())
        device = object()
        action = types.SimpleNamespace(deviceId=1)
        count = inspect.getfullargspec(ActionsMixin.lcdClear).args
        self.assertEqual(len(count), 3)
        ActionsMixin.lcdClear(plugin, action, device)
        plugin._lcdForAction.assert_called_once_with(action, device)
        plugin._lcdForAction.return_value.clear.assert_called_once()
        plugin.logger.error.assert_not_called()

    def test_default_values_are_not_executed_as_generated_source(self):
        value = "'); raise RuntimeError('should not execute')"
        @runtime_boundary('read')
        def callback(owner, text=value):
            return text
        self.assertEqual(callback(types.SimpleNamespace(logger=mock.Mock())), value)

    def test_gpio_unknown_initial_value_does_not_publish_invented_state(self):
        wrapper = object.__new__(AdapterGPIOInputPhidget)
        wrapper._lifecycle_epoch = 1
        wrapper._lifecycle_lock = threading.RLock()
        wrapper._state = 'attached'
        wrapper.logger = mock.Mock()
        wrapper.indigoDevice = mock.Mock()
        wrapper.indigoDevice.name = 'GPIO'
        wrapper.phidget = mock.Mock()
        wrapper.phidget.getState.side_effect = [PhidgetException(ErrorCode.EPHIDGET_UNKNOWNVAL), True]
        wrapper.inverted = False
        wrapper.onStateIcon, wrapper.offStateIcon = 'SensorOn', 'SensorOff'
        wrapper.updateStateOnServer = mock.Mock()
        with mock.patch('threading.Timer') as timer, \
                mock.patch.object(indigo, 'kStateImageSel', types.SimpleNamespace(Auto='auto', SensorOn='on', SensorOff='off'), create=True):
            wrapper._readInitialInput(1)
            wrapper.updateStateOnServer.assert_not_called()
            wrapper.logger.error.assert_not_called()
            wrapper.indigoDevice.setErrorStateOnServer.assert_called_with('Awaiting first input value')
            self.assertEqual(timer.call_args.args[0], 0.2)
            wrapper._readInitialInput(1, 1)
            wrapper.updateStateOnServer.assert_any_call('onOffState', value='on')
            wrapper.indigoDevice.setErrorStateOnServer.assert_called_with(None)
            self.assertFalse(wrapper._awaiting_initial_input)

    def test_initial_input_retry_from_previous_lifecycle_is_discarded(self):
        wrapper = object.__new__(AdapterGPIOInputPhidget)
        wrapper._lifecycle_epoch = 2
        wrapper._lifecycle_lock = threading.RLock()
        wrapper._state = 'attached'
        wrapper.logger = mock.Mock()
        wrapper.phidget = mock.Mock()
        wrapper._readInitialInput(1)
        wrapper.phidget.getState.assert_not_called()
