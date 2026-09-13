import importlib.util
import pathlib
import sys
import time
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))

indigo = types.ModuleType("indigo")


class FakePluginBase(object):
    def __del__(self):
        pass


indigo.PluginBase = FakePluginBase
indigo.Dict = dict
indigo.List = list
sys.modules.setdefault("indigo", indigo)

SPEC = importlib.util.spec_from_file_location("plugin_under_test", SERVER_PLUGIN / "plugin.py")
plugin_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin_module)

from outage_coordinator import OutageCoordinator


class FakePhidget(object):
    def __init__(self, device_id, serial, state="detached", channel=0,
                 hub_port=1):
        self.indigoDevice = types.SimpleNamespace(
            id=device_id, name="Test device %s" % device_id)
        self.channelInfo = types.SimpleNamespace(
            serialNumber=serial,
            hubPort=hub_port,
            channel=channel,
            netInfo=types.SimpleNamespace(isRemote=True),
        )
        self._state = state
        self._detach_announced = state == "detached"
        self._detached_at = time.monotonic() - 3
        self._startup_contention_message = None
        self._startup_error_message = None
        self.detached_reminder_interval = 3600

    def serverKey(self):
        return "Test-Server-B._phidget22server._tcp.local"

    def serverDisplayName(self):
        return "Test-Server-B"

    def _identity(self):
        return "device=%s" % self.indigoDevice.id


class ServerOutageTests(unittest.TestCase):
    def setUp(self):
        self.plugin = plugin_module.Plugin.__new__(plugin_module.Plugin)
        self.plugin.activePhidgets = {
            1: FakePhidget(1, 100),
            2: FakePhidget(2, 200),
        }
        self.plugin.logger = mock.Mock()
        self.coordinator = OutageCoordinator(
            self.plugin.logger,
            lambda: list(self.plugin.activePhidgets.values()))
        self.server_key = "Test-Server-B._phidget22server._tcp.local"

    def test_batch_timer_is_replaced_and_shutdown_cancels_it(self):
        timers = []

        class FakeTimer(object):
            def __init__(self, delay, callback, args):
                self.delay = delay
                self.callback = callback
                self.args = args
                self.daemon = False
                self.started = False
                self.cancelled = False
                timers.append(self)

            def start(self):
                self.started = True

            def cancel(self):
                self.cancelled = True

        coordinator = OutageCoordinator(
            self.plugin.logger,
            lambda: list(self.plugin.activePhidgets.values()),
            timer_factory=FakeTimer)
        phidget = self.plugin.activePhidgets[1]

        coordinator.detach_announced(phidget)
        coordinator.detach_announced(phidget)

        self.assertEqual(len(timers), 2)
        self.assertTrue(timers[0].cancelled)
        self.assertTrue(timers[1].started)
        self.assertEqual(timers[1].delay, coordinator.COALESCE_SECONDS)

        timers[0].callback(*timers[0].args)
        self.assertIn(self.server_key, coordinator._batches["detach"])

        coordinator.stop()

        self.assertTrue(timers[1].cancelled)
        self.assertEqual(coordinator._batches["detach"], {})

    def test_all_channels_detached_produces_one_server_warning_and_recovery(self):
        channels = set(self.plugin.activePhidgets.values())
        self.coordinator._batches["detach"][self.server_key] = channels

        self.coordinator.flush_detach(self.server_key)

        self.plugin.logger.warning.assert_called_once()
        warning = self.plugin.logger.warning.call_args.args[0]
        self.assertIn("server '%s' disconnected", warning)
        self.assertIn(self.server_key, self.coordinator._server_outages)

        for phidget in channels:
            phidget._state = "attached"
            phidget._detach_announced = False
        self.coordinator._batches["recovery"][self.server_key] = {
            phidget: 73.0 for phidget in channels
        }

        self.coordinator.flush_recovery(self.server_key)

        self.plugin.logger.info.assert_called_once()
        self.assertNotIn(self.server_key, self.coordinator._server_outages)

    def test_partial_detach_keeps_channel_level_warning(self):
        attached = self.plugin.activePhidgets[2]
        attached._state = "attached"
        attached._detach_announced = False
        detached = self.plugin.activePhidgets[1]
        self.coordinator._batches["detach"][self.server_key] = {detached}

        self.coordinator.flush_detach(self.server_key)

        self.plugin.logger.warning.assert_called_once()
        self.assertIn("Phidget remains detached", self.plugin.logger.warning.call_args.args[0])
        self.assertNotIn(self.server_key, self.coordinator._server_outages)

    def test_startup_contention_is_grouped_by_physical_phidget(self):
        first = FakePhidget(1, 100, channel=0)
        second = FakePhidget(2, 100, channel=1)
        first._startup_contention_message = "device is in use"
        second._startup_contention_message = "device is in use"
        physical_key = (self.server_key, 100, 1)
        self.coordinator._batches["startup-contention"][physical_key] = {
            first: 5.0, second: 5.1,
        }

        self.coordinator.flush_startup_contention(physical_key)

        self.plugin.logger.error.assert_called_once()
        arguments = self.plugin.logger.error.call_args.args
        self.assertIn("remained in use", arguments[0])
        self.assertIn("'Test device 1' (channel 0)", arguments[-1])
        self.assertIn("'Test device 2' (channel 1)", arguments[-1])

    def test_all_startup_timeouts_for_serial_are_one_physical_device_error(self):
        first = FakePhidget(1, 622666, state="starting", channel=0, hub_port=0)
        second = FakePhidget(2, 622666, state="starting", channel=0, hub_port=1)
        self.plugin.activePhidgets = {1: first, 2: second}
        self.coordinator._batches["startup-unavailable"][622666] = {
            first: (7200.0, "starting"), second: (7200.1, "starting")}

        self.coordinator.flush_startup_unavailable(622666)

        self.plugin.logger.error.assert_called_once()
        arguments = self.plugin.logger.error.call_args.args
        self.assertIn("Physical Phidget serial %s remains unavailable", arguments[0])
        self.assertIn("all %d configured channels are detached", arguments[0])
        self.assertIn("automatic attachment remains active", arguments[0])
        self.assertEqual(arguments[1:5], (622666, 7200.1, 2, "Test-Server-B"))
        self.assertIn("'Test device 1' (hub port 0, channel 0)", arguments[5])
        self.assertIn("'Test device 2' (hub port 1, channel 0)", arguments[5])

    def test_partial_startup_timeout_remains_channel_specific(self):
        first = FakePhidget(1, 622666, state="starting")
        second = FakePhidget(2, 622666, state="attached")
        self.plugin.activePhidgets = {1: first, 2: second}
        self.coordinator._batches["startup-unavailable"][622666] = {
            first: (7200.0, "starting")}

        self.coordinator.flush_startup_unavailable(622666)

        self.plugin.logger.error.assert_called_once()
        self.assertIn("Phidget remains detached", self.plugin.logger.error.call_args.args[0])
        self.assertIn("automatic attachment remains active",
                      self.plugin.logger.error.call_args.args[0])

    def test_startup_open_failures_are_grouped_by_server_and_physical_device(self):
        first = FakePhidget(1, 623318, state="starting", channel=0, hub_port=0)
        second = FakePhidget(2, 623318, state="starting", channel=0, hub_port=1)
        first._startup_error_message = "Network device open failed."
        second._startup_error_message = "Network device open failed."
        self.plugin.activePhidgets = {1: first, 2: second}
        physical_key = (self.server_key, 623318)
        self.coordinator._batches["startup-open-failure"][physical_key] = {
            first: (30.0, first._startup_error_message),
            second: (30.1, second._startup_error_message),
        }

        self.coordinator._clock = lambda: 100.0
        self.coordinator.flush_startup_open_failure(physical_key)

        self.plugin.logger.error.assert_called_once()
        arguments = self.plugin.logger.error.call_args.args
        self.assertIn("Phidget open failed", arguments[0])
        self.assertEqual(arguments[1:5], (30.1, "Test-Server-B", 623318, 2))
        self.assertIn("'Test device 1' (hub port 0, channel 0)", arguments[5])
        self.assertIn("'Test device 2' (hub port 1, channel 0)", arguments[5])

    def test_identical_open_failure_is_suppressed_until_reminder_interval(self):
        phidget = self.plugin.activePhidgets[1]
        phidget._startup_error_message = "Network device open failed."
        physical_key = (self.server_key, phidget.channelInfo.serialNumber)
        self.coordinator._open_failure_last_logged[physical_key] = 100.0
        self.coordinator._batches["startup-open-failure"][physical_key] = {
            phidget: (31.0, phidget._startup_error_message)}

        self.coordinator._clock = lambda: 101.0
        self.coordinator.flush_startup_open_failure(physical_key)

        self.plugin.logger.error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
