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
        SensorOn="green", SensorTripped="red", Error="generic-error")

from Phidget22.Net import Net
from Phidget22.PhidgetServer import PhidgetServer
from Phidget22.PhidgetServerType import PhidgetServerType
from network_server import NetworkServerDevice
from server_discovery import channel_server_records
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

    def updateStateOnServer(self, key, value, **kwargs):
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
        self.pluginPrefs = {
            "attachTimeout": "30",
            "detachedReminderInterval": "3600",
        }
        self.channels_seen = False

    def registerNetworkServerDevice(self, monitor):
        self.registered.add(monitor)

    def unregisterNetworkServerDevice(self, monitor):
        self.registered.discard(monitor)

    def triggerEvent(self, monitor, event):
        self.events.append(event)

    def networkServerHasChannels(self, server_name):
        return self.channels_seen

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

    def test_initially_unavailable_server_shows_red_circle(self):
        self.device.error = "Offline"  # Persisted error from earlier releases.
        self.monitor.serverInitiallyUnavailable()
        self.assertEqual(self.device.states["availability"], "Offline")
        self.assertIsNone(self.device.error)
        self.assertEqual(self.device.image, "red")

    def test_discovery_publishes_read_only_server_metadata_and_attach(self):
        self.monitor.serverAvailable(server())

        self.assertTrue(self.device.states["onOffState"])
        self.assertEqual(self.device.states["availability"], "Online")
        self.assertEqual(self.device.states["serverName"], "CM-Spare")
        self.assertEqual(self.device.states["serviceType"], "_phidget22server._tcp")
        self.assertEqual(self.device.states["address"], "192.0.2.15")
        self.assertEqual(self.device.states["host"], "CM-Spare.local")
        self.assertEqual(self.device.states["port"], 5661)
        self.assertTrue(self.device.states["authenticationRequired"])
        self.assertEqual(self.device.states["flags"], Net.AUTHREQUIRED)
        self.assertEqual(self.plugin.events, [])
        self.assertIsNone(self.device.error)
        self.assertFalse(self.device.update_before_state_list)
        self.assertEqual(self.device.image, "green")

    def test_persistent_removal_detaches_after_grace_and_reconnects(self):
        self.monitor.serverAvailable(server())
        self.monitor.serverUnavailable()
        generation = self.monitor._detach_generation
        self.monitor._confirmUnavailable(generation)

        self.assertFalse(self.device.states["onOffState"])
        self.assertEqual(self.device.states["availability"], "Offline")
        self.assertIsNone(self.device.error)
        self.assertEqual(self.device.image, "red")
        self.assertEqual(
            self.plugin.events, ["deviceDetached"])

        self.monitor.serverAvailable(server())
        self.assertEqual(self.device.states["reconnectCount"], 1)
        self.assertEqual(self.device.image, "green")
        self.assertEqual(
            self.plugin.events,
            ["deviceDetached", "deviceAttached"])

    def test_rediscovery_cancels_transient_removal(self):
        self.monitor.serverAvailable(server())
        self.monitor.serverUnavailable()
        stale_generation = self.monitor._detach_generation
        self.monitor.serverAvailable(server())
        self.monitor._confirmUnavailable(stale_generation)

        self.assertTrue(self.device.states["onOffState"])
        self.assertEqual(self.plugin.events, [])

    @mock.patch("network_server.socket.create_connection")
    def test_two_failed_reachability_checks_detect_hard_loss(self, connect):
        connect.side_effect = OSError("network unreachable")
        self.monitor.serverAvailable(server())
        generation = self.monitor._liveness_generation

        with mock.patch.object(self.monitor, "_schedule_liveness_check"):
            self.monitor._check_liveness(generation)
            self.monitor._check_liveness(generation)

        self.assertEqual(self.monitor._liveness_failures, 2)
        self.assertIsNotNone(self.monitor._detach_timer)
        self.monitor._confirmUnavailable(self.monitor._detach_generation)
        self.assertEqual(self.device.states["availability"], "Offline")
        self.assertEqual(
            self.plugin.events, ["deviceDetached"])

    @mock.patch("network_server.socket.create_connection")
    def test_successful_reachability_check_resets_failure_count(self, connect):
        connection = mock.Mock()
        connect.return_value = connection
        self.monitor.serverAvailable(server())
        self.monitor._liveness_failures = 1
        generation = self.monitor._liveness_generation

        with mock.patch.object(self.monitor, "_schedule_liveness_check"):
            self.monitor._check_liveness(generation)

        connection.close.assert_called_once_with()
        self.assertEqual(self.monitor._liveness_failures, 0)
        self.assertEqual(self.device.states["availability"], "Online")

    @mock.patch("network_server.socket.create_connection")
    def test_recovery_requires_reachable_server_and_discovered_channel(
            self, connect):
        connection = mock.Mock()
        connect.return_value = connection
        self.monitor.serverAvailable(server())
        self.monitor.serverUnavailable()
        self.monitor._confirmUnavailable(self.monitor._detach_generation)

        with mock.patch.object(self.monitor, "_schedule_liveness_check"):
            generation = self.monitor._liveness_generation
            self.monitor._check_liveness(generation)
            self.assertEqual(self.device.states["availability"], "Offline")

            self.plugin.channels_seen = True
            self.monitor._check_liveness(generation)

        self.assertEqual(self.device.states["availability"], "Online")
        self.assertEqual(self.device.error, None)
        self.assertEqual(
            self.plugin.events,
            ["deviceDetached", "deviceAttached"])

    @mock.patch("network_server.socket.create_connection")
    def test_missing_announcement_recovers_from_channels_and_detects_later_loss(self, connect):
        self.plugin.discoveryInventory = types.SimpleNamespace(
            snapshot=lambda: [{"isRemote": True, "serverName": "CM-Spare",
                               "serverPeerName": "192.0.2.20:5661"}])
        self.monitor.serverInitiallyUnavailable()
        self.assertIsNotNone(self.monitor._liveness_timer)
        with mock.patch.object(self.monitor, "_schedule_liveness_check"):
            self.monitor._check_liveness(self.monitor._liveness_generation)
        connect.assert_called_with(("192.0.2.20", 5661), timeout=2.0)
        self.assertEqual(self.device.states["availability"], "Online")
        self.assertEqual(self.device.image, "green")
        self.assertNotIn("authenticationRequired", self.device.states)
        connect.side_effect = OSError("unreachable")
        with mock.patch.object(self.monitor, "_schedule_liveness_check"):
            self.monitor._check_liveness(self.monitor._liveness_generation)
            self.monitor._check_liveness(self.monitor._liveness_generation)
        self.monitor._confirmUnavailable(self.monitor._detach_generation)
        self.assertEqual(self.device.states["availability"], "Offline")
        self.assertEqual(self.device.image, "red")

    @mock.patch("network_server.socket.create_connection")
    def test_missing_announcement_waits_for_inventory_and_reachability(self, connect):
        channels = []
        self.plugin.discoveryInventory = types.SimpleNamespace(snapshot=lambda: channels)
        self.monitor.serverInitiallyUnavailable()
        with mock.patch.object(self.monitor, "_schedule_liveness_check") as schedule:
            self.monitor._check_liveness(self.monitor._liveness_generation)
            connect.assert_not_called()
            schedule.assert_called_once()
        channels.append({"isRemote": True, "serverName": "CM-Spare",
                         "serverPeerName": "192.0.2.20:5661"})
        connect.side_effect = OSError("unreachable")
        with mock.patch.object(self.monitor, "_schedule_liveness_check"):
            self.monitor._check_liveness(self.monitor._liveness_generation)
        self.assertEqual(self.device.states["availability"], "Offline")
        connect.side_effect = None
        with mock.patch.object(self.monitor, "_schedule_liveness_check"):
            self.monitor._check_liveness(self.monitor._liveness_generation)
        self.assertEqual(self.device.states["availability"], "Online")

    @mock.patch("network_server.socket.create_connection")
    def test_recovery_uses_new_channel_endpoint_after_address_change(self, connect):
        self.monitor.serverAvailable(server())
        self.monitor.serverUnavailable()
        self.monitor._confirmUnavailable(self.monitor._detach_generation)
        self.plugin.discoveryInventory = types.SimpleNamespace(snapshot=lambda: [
            {"isRemote": True, "serverName": "CM-Spare",
             "serverPeerName": "192.0.2.99:5662"}])
        with mock.patch.object(self.monitor, "_schedule_liveness_check"):
            self.monitor._check_liveness(self.monitor._liveness_generation)
        connect.assert_called_with(("192.0.2.99", 5662), timeout=2.0)
        self.assertEqual(self.device.states["address"], "192.0.2.99")
        self.assertEqual(self.device.states["reconnectCount"], 1)

    @mock.patch("network_server.socket.create_connection")
    def test_stopped_monitor_does_not_probe_inventory_endpoint(self, connect):
        generation = self.monitor._liveness_generation
        self.monitor.stop()
        self.monitor._check_liveness(generation)
        connect.assert_not_called()

    def test_sustained_outage_escalates_and_schedules_reminder(self):
        with mock.patch.object(
                __import__("network_server").time, "monotonic",
                side_effect=[100.0, 145.0]):
            self.monitor.serverAvailable(server())
            self.monitor.serverUnavailable()
            self.monitor._confirmUnavailable(self.monitor._detach_generation)
            generation = self.monitor._unavailable_generation
            self.monitor._unavailableReminder(generation)

        arguments = self.logger.error.call_args.args
        self.assertIn("remains unavailable after %.1f seconds", arguments[0])
        self.assertEqual(arguments[1:], ("CM-Spare", 45.0))
        self.assertTrue(self.monitor._unavailable_announced)
        self.assertIsNotNone(self.monitor._unavailable_timer)

    def test_recovery_after_escalation_is_reported(self):
        self.monitor.serverAvailable(server())
        self.monitor.serverUnavailable()
        self.monitor._confirmUnavailable(self.monitor._detach_generation)
        self.monitor._unavailable_announced = True

        self.monitor.serverAvailable(server())

        self.logger.info.assert_called_once()
        self.assertEqual(self.logger.info.call_args.args[2], "recovered")

    def test_state_list_includes_monitoring_fields(self):
        state_ids = [definition[0] for definition in self.monitor.getDeviceStateList()]
        self.assertEqual(state_ids, [
            "onOffState", "availability", "serverName", "serviceType",
            "serverType", "address", "host", "port",
            "authenticationRequired", "flags", "lastAttached",
            "lastDetached", "lastOutageSeconds", "reconnectCount",
            "serverVersion", "serverVersionStatus", "lastVersionCheck",
            "versionCheckError"])
        self.assertEqual(self.monitor.getDeviceDisplayStateId(), "availability")


class NetworkServerConfigurationTests(unittest.TestCase):
    def test_empty_server_selection_is_rejected(self):
        coordinator = object.__new__(discovery_ui.DiscoveryUiMixin)
        coordinator.pluginId = "com.yikes.eric.phidgets-indigo"
        with mock.patch.object(discovery_ui.indigo, "devices", []):
            valid, _, errors = coordinator._validateNetworkServerConfig(
                {"networkServerSelection": ""}, 0)

        self.assertFalse(valid)
        self.assertIn("networkServerSelection", errors)

    def test_menu_uses_channel_discovery_when_announcement_is_missing(self):
        coordinator = object.__new__(discovery_ui.DiscoveryUiMixin)
        coordinator.pluginId = "test"
        coordinator._networkServerLock = __import__("threading").RLock()
        coordinator._discoveredServers = {}
        channels = [{"isRemote": True, "serverName": "CM-Vin",
                     "serverPeerName": "192.0.2.20:5661"}]
        coordinator.discoveryInventory = types.SimpleNamespace(snapshot=lambda: channels)
        device = types.SimpleNamespace(pluginId="test", pluginProps={"networkServerName": "CM-Vin"})
        with mock.patch.object(discovery_ui.indigo, "devices", [device]):
            self.assertEqual(coordinator.getNetworkServerMenu(), [("CM-Vin", "CM-Vin")])
            channels.clear()
            self.assertEqual(coordinator.getNetworkServerMenu(), [("CM-Vin", "CM-Vin (offline)")])

    def test_inventory_resolver_handles_aliases_ipv6_and_ambiguous_names(self):
        channels = [{"isRemote": True, "serverName": "CM-Vin",
                     "serverUniqueName": "CM-Vin._phidget22server._tcp.local",
                     "serverPeerName": "[2001:db8::1]:5661"}]
        inventory = types.SimpleNamespace(snapshot=lambda: channels)
        records = channel_server_records(inventory)
        self.assertEqual(records["CM-Vin"].addr, "2001:db8::1")
        self.assertIs(records["CM-Vin"], records[channels[0]["serverUniqueName"]])
        channels.append(dict(channels[0], serverPeerName="192.0.2.20:5661"))
        self.assertNotIn("CM-Vin", channel_server_records(inventory))
        channels[:] = [{"isRemote": True, "serverName": "CM-Vin", "serverPeerName": "bad"}]
        self.assertEqual(channel_server_records(inventory), {})

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
