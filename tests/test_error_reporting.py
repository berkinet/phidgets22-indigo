import ast
import pathlib
import sys
import types
import unittest
from unittest import mock

SERVER = pathlib.Path(__file__).parents[1] / 'Phidgets22.indigoPlugin/Contents/Server Plugin'
sys.path.insert(0, str(SERVER))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))
from error_reporting import FaultReporter, runtime_boundary


class ErrorReportingTests(unittest.TestCase):
    def test_first_reminder_daily_transition_and_clear(self):
        now = [0]
        logger = mock.Mock()
        faults = FaultReporter(logger, clock=lambda: now[0])
        for _ in range(100):
            faults.report('error', 'read', 'Read failed: %s', RuntimeError('bad\nread'))
        logger.error.assert_called_once_with('Read failed: %s', 'bad read')
        now[0] = 3600
        faults.report('error', 'read', 'Read failed: %s', 'bad read')
        self.assertEqual(logger.error.call_count, 2)
        now[0] = 90000
        faults.report('error', 'read', 'Read failed: %s', 'bad read')
        now[0] = 93600
        faults.report('error', 'read', 'Read failed: %s', 'bad read')
        self.assertEqual(logger.error.call_count, 3)
        faults.clear('read')
        faults.report('error', 'read', 'Read failed: %s', 'bad read')
        self.assertEqual(logger.error.call_count, 4)

    def test_callback_failures_are_concise_and_distinct_from_success(self):
        owner = types.SimpleNamespace(logger=mock.Mock(), indigoDevice=types.SimpleNamespace(name='Door', id=1))
        @runtime_boundary('Read')
        def callback(owner, fail):
            if fail:
                raise RuntimeError('bad\nread')
            return 12
        for _ in range(5):
            self.assertIsNone(callback(owner, True))
        owner.logger.error.assert_called_once()
        text = owner.logger.error.call_args.args[0] % owner.logger.error.call_args.args[1:]
        self.assertNotIn('\n', text)
        self.assertNotIn('Traceback', text)
        self.assertEqual(callback(owner, False), 12)
        callback(owner, True)
        self.assertEqual(owner.logger.error.call_count, 2)

    def test_runtime_source_does_not_emit_python_tracebacks(self):
        for path in SERVER.glob('*.py'):
            tree = ast.parse(path.read_text())
            for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
                if isinstance(call.func, ast.Attribute):
                    self.assertNotIn(call.func.attr, ('format_exc', 'print_exc', 'exception'), str(path))
                for keyword in call.keywords:
                    if keyword.arg == 'exc_info':
                        self.assertFalse(isinstance(keyword.value, ast.Constant) and keyword.value.value, str(path))

    def test_gpio_failed_write_does_not_read_status_and_reports_request_context(self):
        import adapter_gpio
        output = object.__new__(adapter_gpio.AdapterGPIOOutputPhidget)
        output.logger = mock.Mock()
        output.updateIndigoStatus = mock.Mock(side_effect=RuntimeError('detached'))
        output._identity = lambda: "device='GPIO' id=42"
        output.asyncSetResult(None, 52, 'Device not Attached', 'Turn Off', False)
        output.updateIndigoStatus.assert_not_called()
        output.logger.error.assert_called_once()
        self.assertEqual(output.logger.error.call_args.args[-2:], ('Turn Off', False))

    def test_sensor_publication_failure_does_not_escape_sdk_callback(self):
        import temperaturesensor
        output = object.__new__(temperaturesensor.TemperatureSensorPhidget)
        output.logger = mock.Mock()
        output._state = 'attached'
        output.decimalPlaces = 2
        output.updateStateOnServer = mock.Mock(side_effect=RuntimeError('Indigo unavailable'))
        output.indigoDevice = types.SimpleNamespace(name='Temperature', id=42)
        output.onTemperatureChangeHandler(None, 20)
        output.logger.error.assert_called_once()

    def test_poll_keeps_retry_timer_when_indigo_error_publication_fails(self):
        from test_sgp41 import SGP41Tests, i2c_peripheral
        output, adapter, device = SGP41Tests().wrapper()
        device.setErrorStateOnServer.side_effect = RuntimeError('Indigo temporarily unavailable')
        with mock.patch.object(i2c_peripheral.threading, 'Timer') as timer:
            output.start()
            self.assertEqual(output._state, 'attached')
            timer.return_value.start.assert_called()
            self.assertGreaterEqual(output.logger.error.call_count, 1)

    def test_repeated_queue_warning_is_bounded(self):
        from error_reporting import log_warning
        output = types.SimpleNamespace(logger=mock.Mock())
        for _ in range(100):
            log_warning(output, "Display queued for '%s'", 'LCD')
        output.logger.warning.assert_called_once()
