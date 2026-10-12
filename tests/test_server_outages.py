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

from connection_identity import PhysicalDeviceIdentity, PortIdentity
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
            netInfo=types.SimpleNamespace(
                isRemote=True,
                serverName="Test-Server-B._phidget22server._tcp.local"),
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

    def test_manual_scan_reports_each_device_without_touching_timers(self):
        import threading
        first = FakePhidget(1, 100)
        second = FakePhidget(2, 100, hub_port=0)
        attached = FakePhidget(3, 200, state="attached")
        from network_server import NetworkServerDevice
        server = NetworkServerDevice.__new__(NetworkServerDevice)
        peripheral = types.SimpleNamespace(channelInfo=first.channelInfo)
        self.plugin.activePhidgets = {
            4: server, 5: peripheral, 1: first, 2: second, 3: attached}
        for phidget in (first, second, attached):
            phidget._lifecycle_lock = threading.RLock()
            phidget._detached_at = 100.0
            phidget.timer = mock.Mock()
            phidget._timer_generation = 7
            phidget._daily_reminder_reported = False
        self.plugin.runtimeRegistry = types.SimpleNamespace(
            snapshot=lambda: list(self.plugin.activePhidgets.values()))
        self.plugin.outageCoordinator = self.coordinator
        with mock.patch.object(plugin_module.time, "monotonic", return_value=10900), \
                mock.patch("outage_coordinator.threading.Timer") as timer:
            self.plugin.scanDetachedPhidgets()
            timer.assert_not_called()
        self.assertEqual(self.plugin.logger.error.call_count, 2)
        for call, phidget in zip(self.plugin.logger.error.call_args_list, (first, second)):
            self.assertEqual(call.args[1], phidget.indigoDevice.name)
            self.assertEqual(call.args[2], "03:00 hours/minutes")
        for phidget in (first, second, attached):
            self.assertEqual(phidget._detached_at, 100.0)
            self.assertEqual(phidget._timer_generation, 7)
            self.assertFalse(phidget._daily_reminder_reported)
            self.assertEqual(phidget.timer.mock_calls, [])
        self.assertFalse(any(self.coordinator._batches.values()))

    def test_manual_scan_reports_when_no_channels_are_detached(self):
        from network_server import NetworkServerDevice
        self.plugin.runtimeRegistry = types.SimpleNamespace(snapshot=lambda: [
            NetworkServerDevice.__new__(NetworkServerDevice)])
        self.plugin.scanDetachedPhidgets()
        self.plugin.logger.info.assert_called_once()
        self.plugin.logger.error.assert_not_called()

    def test_coalesced_report_rechecks_native_attachment(self):
        first = self.plugin.activePhidgets[1]
        second = FakePhidget(3, 100)
        self.plugin.activePhidgets[3] = second
        first.isChannelDetached = lambda: False
        second.isChannelDetached = lambda: True
        key = PhysicalDeviceIdentity.from_wrapper(first)
        self.coordinator.report_unavailable(key, {
            first: (120, 'detached'), second: (120, 'detached')})
        self.plugin.logger.error.assert_called_once()
        args = self.plugin.logger.error.call_args.args
        self.assertEqual(args[1], second.indigoDevice.name)
        self.assertEqual(args[4], '')

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

    def test_network_server_monitor_does_not_abort_channel_warning(self):
        detached = self.plugin.activePhidgets[1]
        self.plugin.activePhidgets[2]._state = "attached"
        self.plugin.activePhidgets[2]._detach_announced = False
        self.plugin.activePhidgets[99] = types.SimpleNamespace(
            indigoDevice=types.SimpleNamespace(
                id=99, deviceTypeId="networkServer"))
        self.coordinator._batches["detach"][self.server_key] = {detached}

        self.coordinator.flush_detach(self.server_key)

        self.plugin.logger.warning.assert_called_once()
        self.assertIn(
            "Phidget remains detached",
            self.plugin.logger.warning.call_args.args[0])

    def test_startup_contention_is_grouped_by_physical_phidget(self):
        first = FakePhidget(1, 100, channel=0)
        second = FakePhidget(2, 100, channel=1)
        first._startup_contention_message = "device is in use"
        second._startup_contention_message = "device is in use"
        physical_key = PortIdentity.from_wrapper(first)
        self.coordinator._batches["startup-contention"][physical_key] = {
            first: 5.0, second: 5.1,
        }

        self.coordinator.flush_startup_contention(physical_key)

        self.plugin.logger.error.assert_called_once()
        arguments = self.plugin.logger.error.call_args.args
        self.assertIn("remained in use", arguments[0])
        self.assertIn("'Test device 1' (channel 0)", arguments[-1])
        self.assertIn("'Test device 2' (channel 1)", arguments[-1])

    def test_all_startup_timeouts_report_each_indigo_device(self):
        first = FakePhidget(1, 622666, state="starting", channel=0, hub_port=0)
        second = FakePhidget(2, 622666, state="starting", channel=0, hub_port=1)
        self.plugin.activePhidgets = {1: first, 2: second}
        physical_key = PhysicalDeviceIdentity.from_wrapper(first)
        self.coordinator._batches["startup-unavailable"][physical_key] = {
            first: (7200.0, "starting"), second: (7200.1, "starting")}

        self.coordinator.flush_startup_unavailable(physical_key)

        self.assertEqual(self.plugin.logger.error.call_count, 2)
        for call, name, port in zip(self.plugin.logger.error.call_args_list,
                                    ("Test device 1", "Test device 2"), (0, 1)):
            arguments = call.args
            self.assertIn("Indigo device '%s'", arguments[0])
            self.assertIn("automatic attachment remains active", arguments[0])
            self.assertEqual(arguments[1], name)
            self.assertEqual(arguments[2], "02:00 hours/minutes")
            self.assertEqual(arguments[3], 622666)
            self.assertEqual(arguments[4], "")
            self.assertEqual(arguments[5:], ("Test-Server-B", port, 0))

    def test_two_indigo_definitions_on_same_phidget_count_as_two(self):
        first = FakePhidget(1, 742134, channel=0, hub_port=0)
        second = FakePhidget(2, 742134, channel=1, hub_port=0)
        reader = FakePhidget(3, 742134, channel=0, hub_port=1)
        self.plugin.activePhidgets = {1: first, 2: second, 3: reader}
        self.coordinator.report_unavailable(PhysicalDeviceIdentity.from_wrapper(first), {
            first: (120, 'detached'), second: (120, 'detached'),
            reader: (120, 'detached')})
        calls = self.plugin.logger.error.call_args_list
        self.assertEqual(len(calls), 3)
        for call in calls[:2]:
            self.assertEqual(call.args[4],
                "both Indigo devices configured for this Phidget are unavailable; ")
        self.assertEqual(calls[2].args[4], '')

    def test_partial_startup_timeout_remains_channel_specific(self):
        first = FakePhidget(1, 622666, state="starting")
        second = FakePhidget(2, 622666, state="attached")
        self.plugin.activePhidgets = {1: first, 2: second}
        physical_key = PhysicalDeviceIdentity.from_wrapper(first)
        self.coordinator._batches["startup-unavailable"][physical_key] = {
            first: (7200.0, "starting")}

        self.coordinator.flush_startup_unavailable(physical_key)

        self.plugin.logger.error.assert_called_once()
        self.assertIn("Indigo device", self.plugin.logger.error.call_args.args[0])
        self.assertIn("automatic attachment remains active",
                      self.plugin.logger.error.call_args.args[0])

    def test_startup_open_failures_are_grouped_by_server_and_physical_device(self):
        first = FakePhidget(1, 623318, state="starting", channel=0, hub_port=0)
        second = FakePhidget(2, 623318, state="starting", channel=0, hub_port=1)
        first._startup_error_message = "Network device open failed."
        second._startup_error_message = "Network device open failed."
        self.plugin.activePhidgets = {1: first, 2: second}
        physical_key = PhysicalDeviceIdentity.from_wrapper(first)
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
        physical_key = PhysicalDeviceIdentity.from_wrapper(phidget)
        self.coordinator._open_failure_last_logged[physical_key] = 100.0
        self.coordinator._batches["startup-open-failure"][physical_key] = {
            phidget: (31.0, phidget._startup_error_message)}

        self.coordinator._clock = lambda: 101.0
        self.coordinator.flush_startup_open_failure(physical_key)

        self.plugin.logger.error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
