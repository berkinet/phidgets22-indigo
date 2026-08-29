import importlib.util
import logging
import pathlib
import sys
import time
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
SPEC = importlib.util.spec_from_file_location("phidget", SERVER_PLUGIN / "phidget.py")
phidget_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phidget_module)


class FakeNativePhidget(object):
    def __init__(self, fail_open=False):
        self.fail_open = fail_open
        self.closed = False
        self.values = {}

    def __getattr__(self, name):
        if name.startswith("set"):
            return lambda value: self.values.__setitem__(name, value)
        raise AttributeError(name)

    def open(self):
        if self.fail_open:
            raise RuntimeError("open failed")

    def close(self):
        self.closed = True

    def getServerName(self):
        return "Test-Server-C"

    def getServerUniqueName(self):
        return "Test-Server-C._phidget22server._tcp.local"

    def getServerHostname(self):
        return "Test-Server-C.local"

    def getServerPeerName(self):
        return "192.0.2.10:5661"

    def getDeviceName(self):
        return "Phidget VINT Hub"

    def getDeviceSKU(self):
        return "HUB0000"

    def getChannelName(self):
        return "Digital Input"


class FakeDevice(object):
    def __init__(self):
        self.name = "Test device"
        self.id = 42
        self.pluginProps = {}
        self.errors = []
        self.states = {}

    def setErrorStateOnServer(self, value):
        self.errors.append(value)

    def updateStateOnServer(self, key, value):
        self.states[key] = value


class FakePlugin(object):
    def __init__(self, attach_timeout="30"):
        self.pluginPrefs = {"attachTimeout": attach_timeout}
        self.events = []

    def triggerEvent(self, device, event):
        self.events.append(event)


class TestPhidget(phidget_module.PhidgetBase):
    __test__ = False

    def __init__(self, fail_initialization=False, fail_open=False,
                 peripheral_unavailable=False, attach_timeout="30"):
        self.fail_initialization = fail_initialization
        self.peripheral_unavailable = peripheral_unavailable
        self.handlers_added = False
        self.native = FakeNativePhidget(fail_open=fail_open)
        self.device = FakeDevice()
        self.plugin = FakePlugin(attach_timeout=attach_timeout)
        self.test_logger = mock.Mock()
        super(TestPhidget, self).__init__(
            phidget=self.native,
            indigo_plugin=self.plugin,
            channelInfo=phidget_module.ChannelInfo(
                serialNumber=123, hubPort=2, isHubPortDevice=1, channel=0,
                netInfo=phidget_module.NetInfo(isRemote=True, serverName="server")),
            indigoDevice=self.device,
            logger=self.test_logger)

    def addPhidgetHandlers(self):
        self.handlers_added = True

    def configureAttachedPhidget(self, ph):
        if self.peripheral_unavailable:
            raise phidget_module.PeripheralUnavailableError(
                "No I2C display responded at 0x27")
        if self.fail_initialization:
            raise RuntimeError("configuration failed")


class PhidgetLifecycleTests(unittest.TestCase):
    def tearDown(self):
        phidget = getattr(self, "phidget", None)
        if phidget is not None:
            phidget.stop()

    def test_attach_is_healthy_only_after_initialization(self):
        self.phidget = TestPhidget(fail_initialization=True)
        self.phidget.start()
        self.phidget.onAttachHandler(self.phidget.native)

        self.assertEqual(self.phidget._state, "detached")
        self.assertEqual(self.phidget.device.errors[-1], "Initialization failed")
        self.assertEqual(self.phidget.plugin.events, [])

    def test_expected_missing_peripheral_logs_without_a_traceback(self):
        self.phidget = TestPhidget(peripheral_unavailable=True)
        self.phidget.start()

        self.phidget.onAttachHandler(self.phidget.native)

        self.assertEqual(self.phidget._state, "detached")
        self.assertEqual(self.phidget.device.errors[-1], "Initialization failed")
        self.phidget.test_logger.error.assert_called_once()
        log_args = self.phidget.test_logger.error.call_args.args
        self.assertNotIn("Traceback", " ".join(map(str, log_args)))
        self.assertIn(
            "No I2C display responded at 0x27",
            " ".join(map(str, log_args)))

    def test_successful_attach_caches_actual_server_identity(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        self.phidget.onAttachHandler(self.phidget.native)

        self.assertEqual(self.phidget.serverDisplayName(), "Test-Server-C")
        self.assertEqual(
            self.phidget.serverKey(), "Test-Server-C._phidget22server._tcp.local")
        self.assertEqual(self.phidget.device.states["connectionType"], "remote")
        self.assertEqual(self.phidget.device.states["serverPeer"], "192.0.2.10:5661")
        self.assertEqual(
            self.phidget.device.states["connectionPath"],
            "Test-Server-C→VINT Hub→Port 2→Digital Input")

    def test_brief_detach_is_silent_and_reuses_the_open_handle(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        self.phidget.onAttachHandler(self.phidget.native)
        self.phidget.onDetachHandler(self.phidget.native)
        self.phidget.onAttachHandler(self.phidget.native)

        self.assertEqual(self.phidget._state, "attached")
        self.assertEqual(self.phidget.device.errors, [None])
        self.assertEqual(self.phidget.plugin.events, ["deviceAttached"])
        self.assertEqual(self.phidget._attach_count, 2)

    def test_persistent_detach_sets_error_and_emits_events_after_grace(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        self.phidget.onAttachHandler(self.phidget.native)
        self.phidget.onDetachHandler(self.phidget.native)
        generation = self.phidget._detach_generation

        self.phidget.detachGraceHandler(generation)

        self.assertEqual(self.phidget.device.errors, [None, "Detached"])
        self.assertEqual(self.phidget.plugin.events,
                         ["deviceAttached", "deviceDetached"])

        self.phidget.onAttachHandler(self.phidget.native)
        self.assertEqual(self.phidget.device.errors, [None, "Detached", None])
        self.assertEqual(self.phidget.plugin.events,
                         ["deviceAttached", "deviceDetached", "deviceAttached"])

    def test_stale_detach_grace_cannot_publish_after_reattach(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        self.phidget.onAttachHandler(self.phidget.native)
        self.phidget.onDetachHandler(self.phidget.native)
        stale_generation = self.phidget._detach_generation
        self.phidget.onAttachHandler(self.phidget.native)

        self.phidget.detachGraceHandler(stale_generation)

        self.assertEqual(self.phidget.device.errors, [None])
        self.assertEqual(self.phidget.plugin.events, ["deviceAttached"])

    def test_cancelled_timeout_cannot_overwrite_successful_attach(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        stale_generation = self.phidget._timer_generation
        self.phidget.onAttachHandler(self.phidget.native)
        self.phidget.connectionTimeoutHandler(stale_generation)

        self.assertEqual(self.phidget.device.errors, [None])
        self.assertEqual(self.phidget._state, "attached")

    def test_transient_startup_contention_is_quiet_when_attachment_recovers(self):
        self.phidget = TestPhidget()
        self.phidget.start()

        self.phidget.onErrorHandler(
            self.phidget.native, 2,
            "open failed because device is in use")
        self.phidget.onAttachHandler(self.phidget.native)

        self.assertEqual(self.phidget._state, "attached")
        self.assertEqual(self.phidget.device.errors, [None])
        self.phidget.test_logger.error.assert_not_called()
        self.assertIsNone(self.phidget._startup_contention_message)

    def test_transient_startup_open_error_is_quiet_when_attachment_recovers(self):
        self.phidget = TestPhidget()
        self.phidget.start()

        self.phidget.onErrorHandler(
            self.phidget.native, 5,
            "Network device: <DIGITALOUTPUT_PORT> on Server: <CM-Maison> "
            "open failed. Error details from server: Device not attached")
        self.phidget.onAttachHandler(self.phidget.native)

        self.assertEqual(self.phidget._state, "attached")
        self.assertEqual(self.phidget.device.errors, [None])
        self.phidget.test_logger.error.assert_not_called()

    def test_startup_open_error_is_concise_after_grace_and_wait_continues(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        generation = self.phidget._timer_generation
        message = (
            "Network device: <DIGITALOUTPUT_PORT> on Server: <CM-Maison> "
            "open failed. Error details from server: Device not attached")
        self.phidget.onErrorHandler(self.phidget.native, 5, message)

        self.phidget.connectionTimeoutHandler(generation)

        self.assertEqual(self.phidget.device.errors, ["Detached"])
        self.phidget.test_logger.error.assert_called_once_with(
            "%s on %s", "device='Test device' id=42",
            "Network device: <DIGITALOUTPUT_PORT> on Server: <CM-Maison> "
            "open failed.")
        self.assertEqual(self.phidget._state, "starting")
        self.assertFalse(self.phidget.native.closed)

        self.phidget.onErrorHandler(self.phidget.native, 5, message)
        self.phidget.test_logger.error.assert_called_once()
        self.phidget.onAttachHandler(self.phidget.native)
        self.assertEqual(self.phidget._state, "attached")
        self.assertEqual(self.phidget.device.errors, ["Detached", None])

    def test_startup_grace_is_at_least_thirty_seconds(self):
        self.phidget = TestPhidget(attach_timeout="5")
        self.assertEqual(self.phidget.initial_connection_timeout, 30)

    def test_startup_detach_callback_does_not_bypass_thirty_second_grace(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        self.phidget.onDetachHandler(self.phidget.native)
        generation = self.phidget._detach_generation

        self.phidget.detachGraceHandler(generation)

        self.assertEqual(self.phidget.device.errors, [])
        self.assertEqual(self.phidget.plugin.events, [])
        self.phidget.test_logger.warning.assert_not_called()

    def test_persistent_startup_contention_becomes_actionable_error(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        generation = self.phidget._timer_generation
        self.phidget.onErrorHandler(
            self.phidget.native, 2,
            "open failed because device is in use")

        self.phidget.connectionTimeoutHandler(generation)

        self.assertEqual(self.phidget.device.errors, ["Channel in use"])
        self.assertIn("another Indigo plugin instance",
                      self.phidget.test_logger.error.call_args.args[0])

        self.phidget.onAttachHandler(self.phidget.native)
        self.assertEqual(self.phidget.device.errors,
                         ["Channel in use", None])
        self.assertEqual(self.phidget._state, "attached")

    def test_runtime_device_in_use_error_is_not_suppressed(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        self.phidget.onAttachHandler(self.phidget.native)
        self.phidget._started_at = time.monotonic() - 61

        self.phidget.onErrorHandler(
            self.phidget.native, 2,
            "open failed because device is in use")

        self.phidget.test_logger.error.assert_called_once()

    def test_start_failure_cancels_timer_and_closes_handle(self):
        self.phidget = TestPhidget(fail_open=True)
        with self.assertRaises(RuntimeError):
            self.phidget.start()

        self.assertEqual(self.phidget._state, "stopped")
        self.assertIsNone(self.phidget.timer)
        self.assertTrue(self.phidget.native.closed)

    def test_stop_is_repeatable(self):
        self.phidget = TestPhidget()
        self.phidget.start()
        self.phidget.stop()
        self.phidget.stop()
        self.assertEqual(self.phidget._state, "stopped")


if __name__ == "__main__":
    unittest.main()
