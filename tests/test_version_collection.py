import logging
import pathlib
import sys
import threading
import types
import unittest
from unittest import mock


SERVER_PLUGIN = (pathlib.Path(__file__).parents[1] /
                 "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin")
sys.path.insert(0, str(SERVER_PLUGIN))

if "indigo" not in sys.modules:
    sys.modules["indigo"] = types.ModuleType("indigo")
if not hasattr(sys.modules["indigo"], "PluginBase"):
    sys.modules["indigo"].PluginBase = type(
        "PluginBase", (), {"__del__": lambda self: None})

import version_collection


class FakeDevice(object):
    def __init__(self, device_id=1, name="Device", plugin_id="plugin.test"):
        self.id = device_id
        self.name = name
        self.pluginId = plugin_id
        self.states = {}
        self.refreshes = 0

    def updateStateOnServer(self, key, value):
        self.states[key] = value

    def stateListOrDisplayStateIdChanged(self):
        self.refreshes += 1


class NativePhidget(object):
    def __init__(self, firmware=123, upgrade_identifier="HUM1000"):
        self.firmware = firmware
        self.upgrade_identifier = upgrade_identifier

    def getDeviceVersion(self):
        return self.firmware

    def _getDeviceFirmwareUpgradeString(self):
        return self.upgrade_identifier

    def _getServerVersion(self):
        return 2, 5


class UnknownUpgradeabilityPhidget(NativePhidget):
    def _getDeviceFirmwareUpgradeString(self):
        raise RuntimeError("upgrade capability unavailable")


def wrapper(device=None, phidget=None, state="attached", remote=True,
            server="Server A"):
    return types.SimpleNamespace(
        indigoDevice=device or FakeDevice(),
        phidget=phidget if phidget is not None else NativePhidget(),
        _state=state,
        runtimeServerName=server,
        runtimeServerUniqueName="",
        runtimeServerHostname="",
        channelInfo=types.SimpleNamespace(netInfo=types.SimpleNamespace(
            isRemote=remote, serverName=server)))


class FakePlugin(object):
    def __init__(self):
        self.pluginId = "plugin.test"
        self.pluginPrefs = {"versionCollectionInterval": "86400"}
        self.activePhidgets = {}
        self._activePhidgetsLock = threading.RLock()
        self._networkServerDevices = set()
        self._networkServerLock = threading.RLock()


class VersionCollectionTests(unittest.TestCase):
    def setUp(self):
        self.plugin = FakePlugin()
        self.logger = mock.Mock(spec=logging.Logger)
        self.collector = version_collection.VersionCollector(
            self.plugin, self.logger)

    def test_collects_firmware_and_upgradeability_independently(self):
        device = FakeDevice()
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device, phidget=NativePhidget(123, "HUM1000"))

        self.collector.collect()

        self.assertTrue(device.states["hasFirmware"])
        self.assertEqual(device.states["firmwareVersion"], "123")
        self.assertTrue(device.states["firmwareUpgradeable"])
        self.assertEqual(device.states["firmwareUpgradeabilityStatus"],
                         "Supported")
        self.assertEqual(device.states["firmwareVersionStatus"], "Collected")
        self.assertEqual(device.states["versionCheckError"], "")

    def test_firmware_can_exist_without_upgrade_support(self):
        device = FakeDevice()
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device, phidget=NativePhidget(87, ""))

        self.collector.collect()

        self.assertTrue(device.states["hasFirmware"])
        self.assertFalse(device.states["firmwareUpgradeable"])
        self.assertEqual(device.states["firmwareUpgradeabilityStatus"],
                         "Not supported")

    def test_logical_peripheral_reports_no_firmware(self):
        device = FakeDevice()
        logical = types.SimpleNamespace(
            indigoDevice=device, _state="attached", channelInfo=None)
        self.plugin.activePhidgets[device.id] = logical

        self.collector.collect()

        self.assertFalse(device.states["hasFirmware"])
        self.assertFalse(device.states["firmwareUpgradeable"])
        self.assertEqual(device.states["firmwareUpgradeabilityStatus"],
                         "Not supported")
        self.assertEqual(device.states["firmwareVersionStatus"], "No firmware")

    def test_upgradeability_failure_does_not_discard_firmware_version(self):
        device = FakeDevice()
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device, phidget=UnknownUpgradeabilityPhidget(91))

        self.collector.collect()

        self.assertTrue(device.states["hasFirmware"])
        self.assertEqual(device.states["firmwareVersion"], "91")
        self.assertFalse(device.states["firmwareUpgradeable"])
        self.assertEqual(device.states["firmwareUpgradeabilityStatus"],
                         "Unknown")
        self.assertEqual(device.states["firmwareVersionStatus"], "Collected")
        self.assertIn("capability unavailable",
                      device.states["versionCheckError"])

    def test_detached_device_reports_unavailable_without_erasing_version(self):
        device = FakeDevice()
        device.states["firmwareVersion"] = "100"
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device, state="detached")

        self.collector.collect()

        self.assertEqual(device.states["firmwareVersion"], "100")
        self.assertEqual(device.states["firmwareVersionStatus"], "Unavailable")
        self.assertEqual(device.states["versionCheckError"],
                         "Device is not attached")

    def test_collects_server_protocol_version_from_matching_channel(self):
        channel_device = FakeDevice()
        self.plugin.activePhidgets[channel_device.id] = wrapper(
            device=channel_device, server="Server A")
        server_device = FakeDevice(2, "Server A monitor")
        monitor = types.SimpleNamespace(
            serverName="Server A", indigoDevice=server_device)
        self.plugin._networkServerDevices = [monitor]

        self.collector.collect()

        self.assertEqual(server_device.states["serverVersion"], "2.5")
        self.assertEqual(server_device.states["serverVersionStatus"], "Collected")

    def test_server_without_attached_channel_is_unavailable(self):
        server_device = FakeDevice(2, "Server B monitor")
        monitor = types.SimpleNamespace(
            serverName="Server B", indigoDevice=server_device)
        self.plugin._networkServerDevices = [monitor]

        self.collector.collect()

        self.assertEqual(server_device.states["serverVersionStatus"],
                         "Unavailable")
        self.assertIn("No attached", server_device.states["versionCheckError"])

    def test_migration_refreshes_only_plugin_owned_devices(self):
        owned = FakeDevice()
        foreign = FakeDevice(2, plugin_id="another.plugin")
        with mock.patch.object(sys.modules["indigo"], "devices",
                               [owned, foreign], create=True):
            self.collector.migrate_state_lists()

        self.assertEqual(owned.refreshes, 1)
        self.assertEqual(foreign.refreshes, 0)


if __name__ == "__main__":
    unittest.main()
