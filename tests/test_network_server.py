import logging
import pathlib
import sys
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))

if "indigo" not in sys.modules:
    sys.modules["indigo"] = types.ModuleType("indigo")
if not hasattr(sys.modules["indigo"], "Dict"):
    sys.modules["indigo"].Dict = dict
if not hasattr(sys.modules["indigo"], "devices"):
    sys.modules["indigo"].devices = []
if not hasattr(sys.modules["indigo"], "kStateImageSel"):
    sys.modules["indigo"].kStateImageSel = types.SimpleNamespace(
        SensorOn="green", Error="red")

from Phidget22.Net import Net
from Phidget22.PhidgetServer import PhidgetServer
from Phidget22.PhidgetServerType import PhidgetServerType
from network_server import NetworkServerDevice
import discovery_ui


class FakeIndigoDevice(object):
    def __init__(self):
        self.id = 17
        self.name = "CM-Spare server"
        self.states = {}
        self.error = None
        self.state_list_ready = False
        self.update_before_state_list = False
        self.image = None

    def stateListOrDisplayStateIdChanged(self):
        self.state_list_ready = True

    def updateStateOnServer(self, key, value):
        if not self.state_list_ready:
            self.update_before_state_list = True
        self.states[key] = value

    def setErrorStateOnServer(self, value):
        self.error = value

    def updateStateImageOnServer(self, value):
        self.image = value


class FakePlugin(object):
    def __init__(self):
        self.events = []
        self.registered = set()

    def registerNetworkServerDevice(self, monitor):
        self.registered.add(monitor)

    def unregisterNetworkServerDevice(self, monitor):
        self.registered.discard(monitor)

    def triggerEvent(self, monitor, event):
        self.events.append(event)

    def getDeviceStateDictForBoolOnOffType(self, *args):
        return args

    def getDeviceStateDictForNumberType(self, *args):
        return args

    def getDeviceStateDictForStringType(self, *args):
        return args


def server():
    return PhidgetServer(
        name="CM-Spare", stype="_phidget22server._tcp",
        type=PhidgetServerType.PHIDGETSERVER_DEVICEREMOTE,
        flags=Net.AUTHREQUIRED, addr="192.0.2.15",
        host="CM-Spare.local", port=5661)


class NetworkServerDeviceTests(unittest.TestCase):
    def setUp(self):
        self.plugin = FakePlugin()
        self.device = FakeIndigoDevice()
        self.logger = mock.Mock(spec=logging.Logger)
        self.monitor = NetworkServerDevice(
            self.plugin, self.device, "CM-Spare", self.logger)
        self.monitor.start()

    def tearDown(self):
        self.monitor.stop()

    def test_discovery_publishes_read_only_server_metadata_and_attach(self):
        self.monitor.serverAvailable(server())

        self.assertTrue(self.device.states["onOffState"])
        self.assertEqual(self.device.states["availability"], "attached")
        self.assertEqual(self.device.states["serverName"], "CM-Spare")
        self.assertEqual(self.device.states["serviceType"], "_phidget22server._tcp")
        self.assertEqual(self.device.states["address"], "192.0.2.15")
        self.assertEqual(self.device.states["host"], "CM-Spare.local")
        self.assertEqual(self.device.states["port"], 5661)
        self.assertTrue(self.device.states["authenticationRequired"])
        self.assertEqual(self.device.states["flags"], Net.AUTHREQUIRED)
        self.assertEqual(self.plugin.events, ["deviceAttached"])
        self.assertIsNone(self.device.error)
        self.assertFalse(self.device.update_before_state_list)
        self.assertEqual(self.device.image, "green")

    def test_persistent_removal_detaches_after_grace_and_reconnects(self):
        self.monitor.serverAvailable(server())
        self.monitor.serverUnavailable()
        generation = self.monitor._detach_generation
        self.monitor._confirmUnavailable(generation)

        self.assertFalse(self.device.states["onOffState"])
        self.assertEqual(self.device.states["availability"], "detached")
        self.assertEqual(self.device.error, "Detached")
        self.assertEqual(self.device.image, "red")
        self.assertEqual(
            self.plugin.events, ["deviceAttached", "deviceDetached"])

        self.monitor.serverAvailable(server())
        self.assertEqual(self.device.states["reconnectCount"], 1)
        self.assertEqual(
            self.plugin.events,
            ["deviceAttached", "deviceDetached", "deviceAttached"])

    def test_rediscovery_cancels_transient_removal(self):
        self.monitor.serverAvailable(server())
        self.monitor.serverUnavailable()
        stale_generation = self.monitor._detach_generation
        self.monitor.serverAvailable(server())
        self.monitor._confirmUnavailable(stale_generation)

        self.assertTrue(self.device.states["onOffState"])
        self.assertEqual(self.plugin.events, ["deviceAttached"])

    def test_state_list_includes_monitoring_fields(self):
        state_ids = [definition[0] for definition in self.monitor.getDeviceStateList()]
        self.assertEqual(state_ids, [
            "onOffState", "availability", "serverName", "serviceType",
            "serverType", "address", "host", "port",
            "authenticationRequired", "flags", "lastAttached",
            "lastDetached", "lastOutageSeconds", "reconnectCount"])


class NetworkServerConfigurationTests(unittest.TestCase):
    def test_empty_server_selection_is_rejected(self):
        coordinator = object.__new__(discovery_ui.DiscoveryUiMixin)
        coordinator.pluginId = "com.yikes.eric.phidgets-indigo"
        with mock.patch.object(discovery_ui.indigo, "devices", []):
            valid, _, errors = coordinator._validateNetworkServerConfig(
                {"networkServerSelection": ""}, 0)

        self.assertFalse(valid)
        self.assertIn("networkServerSelection", errors)

    def test_menu_has_no_manual_server_entry(self):
        coordinator = object.__new__(discovery_ui.DiscoveryUiMixin)
        coordinator.pluginId = "com.yikes.eric.phidgets-indigo"
        coordinator._networkServerLock = __import__("threading").RLock()
        coordinator._discoveredServers = {"CM-Spare": object()}
        with mock.patch.object(discovery_ui.indigo, "devices", []):
            menu = coordinator.getNetworkServerMenu()

        self.assertEqual(menu, [("CM-Spare", "CM-Spare")])
        self.assertNotIn("manual", [value for value, _ in menu])


if __name__ == "__main__":
    unittest.main()
