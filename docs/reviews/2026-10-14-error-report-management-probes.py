"""Read-only review probes using existing test doubles, never real hardware.
Run with: python3 docs/reviews/2026-10-14-error-report-management-probes.py
These reproduce defects in 2026.1.39; they are not passing regression tests.
"""
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
import test_device_wrappers as wrappers
from test_phidget_lifecycle import TestPhidget, phidget_module
from test_sgp41 import SGP41Tests, i2c_peripheral


def show(name, result):
    print(name, result)


p = TestPhidget()
with mock.patch.object(phidget_module.threading, 'Timer'):
    p.start()
    p.configureAttachedPhidget = lambda ph: p.stop()
    p.onAttachHandler(p.native)
    assert p._state == 'attached' and p.native.closed
    show('Attachment completing after stop', dict(state=p._state, closed=p.native.closed))

p = object.__new__(wrappers.adapter_gpio.AdapterGPIOOutputPhidget)
p.logger = mock.Mock()
p.updateIndigoStatus = mock.Mock(side_effect=RuntimeError('Device not attached'))
try:
    p.asyncSetResult(None, 52, 'Device not Attached')
except RuntimeError as error:
    show('Failed GPIO callback raises another exception', str(error))
else:
    raise AssertionError('Expected the callback boundary defect')

p = TestPhidget()
with mock.patch.object(phidget_module.threading, 'Timer'):
    p.start()
    p.native.getAttached = lambda: True
    p.configureAttachedPhidget = mock.Mock(side_effect=RuntimeError('configuration failed'))
    p.onAttachHandler(p.native)
    p.test_logger.reset_mock()
    p.connectionTimeoutHandler(p._timer_generation)
    assert p._state == 'detached' and not p.isChannelDetached()
    assert p.configureAttachedPhidget.call_count == 1
    assert p.test_logger.error.call_count == 0
    show('Initialization failure hidden from detach scan and not retried', p._state)

p, adapter, device = SGP41Tests().wrapper()
adapter.i2cCommandResponse = mock.Mock(side_effect=RuntimeError('transport unavailable'))
with mock.patch.object(i2c_peripheral.threading, 'Timer'):
    p.start()
    for _ in range(2):
        p._poll(p._generation)
logs = p.logger.error.call_args_list
assert len(logs) == 3 and all('Traceback' in call.args[-1] for call in logs)
show('Three failed polls produce three tracebacks', len(logs))

p, adapter, device = SGP41Tests().wrapper()
adapter._state = 'detached'
p.start()
assert p._state == 'starting' and device.setErrorStateOnServer.call_count == 0
show('Offline I2C provider at startup publishes no device error', p._state)

p, adapter, device = SGP41Tests().wrapper()
p._state = 'attached'
p.providerStopping()
assert p._state == 'detached' and device.setErrorStateOnServer.call_count == 0
show('I2C provider detach publishes no dependent device error', p._state)

p = object.__new__(wrappers.digitaloutput.DigitalOutputPhidget)
p.logger = mock.Mock()
p.updateIndigoStatus = mock.Mock()
p._identity = lambda: 'device=Door'
p.asyncSetResult(None, 52, 'Device not Attached', 'Turn Off', False)
p.asyncSetResult(None, 0, 'OK', 'Earlier command', True)
p.asyncSetResult(None, 52, 'Device not Attached', 'Turn Off', False)
assert p.logger.error.call_count == 2
show('An older success callback resets duplicate suppression', p.logger.error.call_count)
