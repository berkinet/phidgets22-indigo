import sys
import pathlib
import unittest
from unittest import mock
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_phidget_lifecycle import TestPhidget, phidget_module
import test_sgp41 as sgp_fixtures
from test_sgp41 import i2c_peripheral
from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException


class AvailabilityRecoveryTests(unittest.TestCase):
    def test_transient_initialization_retries_then_clears_failure(self):
        wrapper = TestPhidget()
        wrapper.native.getAttached = lambda: True
        wrapper.configureAttachedPhidget = mock.Mock(side_effect=[
            PhidgetException(ErrorCode.EPHIDGET_TIMEOUT), None])
        with mock.patch.object(phidget_module.threading, 'Timer') as timers:
            wrapper.start()
            wrapper.onAttachHandler(wrapper.native)
            self.assertEqual(wrapper._state, 'detached')
            self.assertIsNotNone(wrapper._initialization_error)
            self.assertEqual(timers.call_args.args[0], 5)
            wrapper._retry_initialization(wrapper._lifecycle_epoch)
            self.assertEqual(wrapper._state, 'attached')
            self.assertIsNone(wrapper._initialization_error)
            self.assertEqual(wrapper.device.errors[-1], None)
            self.assertEqual(wrapper.configureAttachedPhidget.call_count, 2)
            wrapper.stop()

    def test_retry_limit_and_shutdown_cancellation(self):
        wrapper = TestPhidget()
        wrapper.native.getAttached = lambda: True
        wrapper.configureAttachedPhidget = mock.Mock(side_effect=PhidgetException(ErrorCode.EPHIDGET_TIMEOUT))
        with mock.patch.object(phidget_module.threading, 'Timer'):
            wrapper.start()
            wrapper.onAttachHandler(wrapper.native)
            for _ in range(5):
                wrapper._retry_initialization(wrapper._lifecycle_epoch)
            self.assertEqual(wrapper._initialization_retry_attempts, 5)
            self.assertIsNone(wrapper._initialization_retry_timer)
            old = wrapper._lifecycle_epoch
            wrapper.stop()
            wrapper._retry_initialization(old)
            self.assertEqual(wrapper._state, 'stopped')
            self.assertEqual(wrapper.configureAttachedPhidget.call_count, 6)

    def test_programming_error_is_reported_and_not_blindly_retried(self):
        wrapper = TestPhidget(fail_initialization=True)
        wrapper.native.getAttached = lambda: True
        with mock.patch.object(phidget_module.threading, 'Timer'):
            wrapper.start()
            wrapper.onAttachHandler(wrapper.native)
            self.assertIsNotNone(wrapper._initialization_error)
            self.assertIsNone(wrapper._initialization_retry_timer)
            self.assertFalse(wrapper.isReady())
            wrapper.test_logger.reset_mock()
            wrapper.connectionTimeoutHandler(wrapper._timer_generation)
            self.assertFalse(wrapper.isReady())
            wrapper.stop()

    def test_logical_sensor_unavailable_startup_and_verified_recovery(self):
        wrapper, adapter, device = sgp_fixtures.SGP41Tests().wrapper()
        adapter._state = 'detached'
        wrapper.start()
        device.setErrorStateOnServer.assert_called_with('Provider unavailable')
        adapter._state = 'attached'
        with mock.patch.object(i2c_peripheral.threading, 'Timer'):
            wrapper.providerReattached()
        device.setErrorStateOnServer.assert_called_with(None)
        wrapper.providerStopping()
        device.setErrorStateOnServer.assert_called_with('Provider unavailable')

    def test_reinitialization_after_operational_fault_clears_indigo_error(self):
        wrapper = TestPhidget()
        wrapper.native.getAttached = lambda: True
        with mock.patch.object(phidget_module.threading, 'Timer'):
            wrapper.start()
            wrapper.onAttachHandler(wrapper.native)
            wrapper.onDetachHandler(wrapper.native)
            wrapper.configureAttachedPhidget = mock.Mock(side_effect=[
                PhidgetException(ErrorCode.EPHIDGET_TIMEOUT), None])
            wrapper.onAttachHandler(wrapper.native)
            self.assertEqual(wrapper.device.errors[-1], 'Initialization failed')
            wrapper._retry_initialization(wrapper._lifecycle_epoch)
            self.assertEqual(wrapper.device.errors[-1], None)
            wrapper.stop()

    def test_duplicate_attach_callback_does_not_run_initialization_twice(self):
        wrapper = TestPhidget()
        wrapper.configureAttachedPhidget = mock.Mock()
        with mock.patch.object(phidget_module.threading, 'Timer'):
            wrapper.start()
            wrapper.onAttachHandler(wrapper.native)
            wrapper.onAttachHandler(wrapper.native)
            wrapper.configureAttachedPhidget.assert_called_once()
            self.assertEqual(wrapper._attach_count, 1)
            wrapper.stop()
