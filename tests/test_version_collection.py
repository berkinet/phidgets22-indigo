import logging
import io
import json
import pathlib
import sys
import tarfile
import tempfile
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
import indigo


class FakeDevice(object):
    def __init__(self, device_id=1, name="Device", plugin_id="plugin.test",
                 device_type="digitalInput"):
        self.id = device_id
        self.name = name
        self.pluginId = plugin_id
        self.deviceTypeId = device_type
        self.states = {}
        self.ui_values = {}
        self.refreshes = 0

    def updateStateOnServer(self, key, value, uiValue=None, **kwargs):
        self.states[key] = value
        if uiValue is not None:
            self.ui_values[key] = uiValue

    def stateListOrDisplayStateIdChanged(self):
        self.refreshes += 1


class NativePhidget(object):
    def __init__(self, firmware=123, upgrade_identifier="TESTUSB",
                 vint_id=None):
        self.firmware = firmware
        self.upgrade_identifier = upgrade_identifier
        self.vint_id = vint_id

    def getDeviceVersion(self):
        return self.firmware

    def _getDeviceFirmwareUpgradeString(self):
        return self.upgrade_identifier

    def _getDeviceVINTID(self):
        if self.vint_id is None:
            raise RuntimeError("not a VINT device")
        return self.vint_id

    def _getServerVersion(self):
        return 2, 5


class UnknownUpgradeabilityPhidget(NativePhidget):
    def _getDeviceFirmwareUpgradeString(self):
        raise RuntimeError("upgrade capability unavailable")


def wrapper(device=None, phidget=None, state="attached", remote=True,
            server="Server A", hub_port_device=False, hub_port=-1):
    return types.SimpleNamespace(
        indigoDevice=device or FakeDevice(),
        phidget=phidget if phidget is not None else NativePhidget(),
        _state=state,
        runtimeServerName=server,
        runtimeServerUniqueName="",
        runtimeServerHostname="",
        channelInfo=types.SimpleNamespace(
            isHubPortDevice=hub_port_device,
            hubPort=hub_port,
            netInfo=types.SimpleNamespace(
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
            self.plugin, self.logger,
            firmware_catalog=version_collection.FirmwareCatalog((
                "TESTUSBv123.bin.rc4",
                "TESTUSBv124.bin.rc4",
                "HUM1000_0x014_v104.bin.obf",
                "HUM1000_0x014_v105.bin.obf",
            )))

    def test_failed_collection_logs_and_reschedules(self):
        with mock.patch.object(self.collector, "collect", side_effect=RuntimeError("boom")), \
                mock.patch.object(self.collector, "_schedule") as schedule:
            self.collector._collect_and_reschedule()
        self.logger.error.assert_called_once()
        schedule.assert_called_once_with(86400)
        self.assertTrue(self.collector._collection_lock.acquire(False))
        self.collector._collection_lock.release()

    def test_official_catalog_refresh_reads_only_firmware_filenames(self):
        archive_data = io.BytesIO()
        with tarfile.open(fileobj=archive_data, mode="w:gz") as archive:
            filename = b"TESTUSBv125.bin.rc4"
            member = tarfile.TarInfo("phidget22admin-1.27.20260914/firmware/" +
                                     filename.decode("ascii"))
            member.size = len(filename)
            archive.addfile(member, io.BytesIO(filename))
        responses = [io.BytesIO(b'<a href="phidget22admin-1.27.20260914.tar.gz">'),
                     io.BytesIO(archive_data.getvalue())]
        opener = mock.Mock(side_effect=responses)
        version, catalog = version_collection.fetch_firmware_catalog(
            opener=opener)
        self.assertEqual(version, "1.27.20260914")
        self.assertEqual(catalog.versions("TESTUSB"), {125})
        self.assertEqual(opener.call_count, 2)

    def test_catalog_refresh_skips_archive_if_no_newer_version(self):
        opener = mock.Mock(return_value=io.BytesIO(
            b'<a href="phidget22admin-1.26.20260828.tar.gz">'))
        self.assertIsNone(version_collection.fetch_firmware_catalog(
            opener=opener))
        opener.assert_called_once()

    def test_last_successful_catalog_survives_restart_and_network_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            self.plugin.plugin_file_handler = types.SimpleNamespace(
                baseFilename=str(pathlib.Path(directory) / "plugin.log"))
            first = version_collection.VersionCollector(
                self.plugin, self.logger)
            catalog = version_collection.FirmwareCatalog((
                "TESTUSBv125.bin.rc4",))
            with mock.patch.object(version_collection, "fetch_firmware_catalog",
                                   return_value=("1.27.20260914", catalog)):
                first._refresh_catalog()
            cache_path = pathlib.Path(directory) / version_collection.CACHE_FILENAME
            self.assertEqual(json.loads(cache_path.read_text())["version"],
                             "1.27.20260914")
            restored = version_collection.VersionCollector(
                self.plugin, self.logger)
            with mock.patch.object(version_collection, "fetch_firmware_catalog",
                                   side_effect=TimeoutError("offline")):
                restored._refresh_catalog()
            self.assertEqual(restored.catalog_version, "1.27.20260914")
            self.assertEqual(restored.firmware_catalog.versions("TESTUSB"), {125})

    def test_collects_firmware_and_upgradeability_independently(self):
        device = FakeDevice()
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device, phidget=NativePhidget(123, "TESTUSB"))

        self.collector.collect()

        self.assertTrue(device.states["hasFirmware"])
        self.assertEqual(device.states["firmwareVersion"], "123")
        self.assertTrue(device.states["firmwareUpgradeable"])
        self.assertEqual(device.states["firmwareUpgradeabilityStatus"],
                         "Supported")
        self.assertEqual(device.states["firmwareVersionStatus"], "Collected")
        self.assertEqual(device.states["versionCheckError"], "")
        self.assertEqual(device.states["latestFirmwareVersion"], "124")
        self.assertTrue(device.states["firmwareUpdateAvailable"])
        self.assertEqual(device.ui_values["firmwareUpdateAvailable"], "Yes")
        self.assertFalse(device.states["firmwareMajorUpdateAvailable"])
        self.assertEqual(device.ui_values["firmwareMajorUpdateAvailable"], "No")
        self.assertEqual(device.states["firmwareUpdateStatus"],
                         "Update available")
        self.assertEqual(device.states["firmwareCatalogVersion"],
                         "1.26.20260828")

    def test_update_variable_event_and_warnings_follow_list_changes(self):
        first = FakeDevice(1, "First")
        second = FakeDevice(2, "Second")
        first_phidget = NativePhidget(123, "TESTUSB")
        second_phidget = NativePhidget(124, "TESTUSB")
        self.plugin.activePhidgets = {
            1: wrapper(first, first_phidget),
            2: wrapper(second, second_phidget),
        }
        self.plugin.eventCoordinator = mock.Mock()
        variables = {}

        def create(name, value):
            variables[name] = types.SimpleNamespace(id=7, value=value)

        def update(variable_id, value):
            self.assertEqual(variable_id, 7)
            variables[version_collection.UPDATE_VARIABLE_NAME].value = value

        with mock.patch.object(indigo, "devices", [first, second], create=True), \
                mock.patch.object(indigo, "variables", variables, create=True), \
                mock.patch.object(indigo, "variable", types.SimpleNamespace(
                    create=create, updateValue=update), create=True):
            self.collector.collect()
            self.assertIn("First (Indigo ID 1): firmware 123; latest 124",
                          variables[version_collection.UPDATE_VARIABLE_NAME].value)
            self.plugin.eventCoordinator.trigger_global_event.assert_called_once_with(
                "firmwareUpdateAvailable")
            self.assertEqual(self.logger.warning.call_count, 1)

            self.collector.collect()
            self.assertEqual(self.logger.warning.call_count, 1)
            self.assertEqual(
                self.plugin.eventCoordinator.trigger_global_event.call_count, 1)

            second_phidget.firmware = 123
            self.collector.collect()
            self.assertEqual(self.logger.warning.call_count, 2)
            self.assertEqual(
                self.plugin.eventCoordinator.trigger_global_event.call_count, 2)

            first_phidget.firmware = 124
            second_phidget.firmware = 124
            self.collector.collect()
            self.assertEqual(variables[version_collection.UPDATE_VARIABLE_NAME].value,
                             "")
            self.assertEqual(
                self.plugin.eventCoordinator.trigger_global_event.call_count, 2)

            first_phidget.firmware = 123
            self.collector.collect()
            self.assertEqual(self.logger.warning.call_count, 3)
            self.assertEqual(
                self.plugin.eventCoordinator.trigger_global_event.call_count, 3)

    def test_saved_update_state_and_variable_do_not_notify_after_restart(self):
        device = FakeDevice(1, "Existing")
        device.states["firmwareUpdateAvailable"] = True
        self.plugin.activePhidgets[1] = wrapper(
            device, NativePhidget(123, "TESTUSB"))
        self.plugin.eventCoordinator = mock.Mock()
        value = "Existing (Indigo ID 1): firmware 123; latest 124"
        variables = {version_collection.UPDATE_VARIABLE_NAME:
                     types.SimpleNamespace(id=7, value=value)}

        with mock.patch.object(indigo, "devices", [device], create=True), \
                mock.patch.object(indigo, "variables", variables, create=True), \
                mock.patch.object(indigo, "variable", mock.Mock(), create=True):
            self.collector.collect()

        self.logger.warning.assert_not_called()
        self.plugin.eventCoordinator.trigger_global_event.assert_not_called()

    def test_temporary_older_version_exercises_real_notification_path(self):
        device = FakeDevice(1, "Test device")
        phidget = NativePhidget(124, "TESTUSB")
        self.plugin.activePhidgets[1] = wrapper(device, phidget)
        self.plugin.eventCoordinator = mock.Mock()
        variables = {}
        self.collector.request_collection = mock.Mock()

        def create(name, value):
            variables[name] = types.SimpleNamespace(id=7, value=value)

        def update(variable_id, value):
            variables[version_collection.UPDATE_VARIABLE_NAME].value = value

        with mock.patch.object(indigo, "devices", [device], create=True), \
                mock.patch.object(indigo, "variables", variables, create=True), \
                mock.patch.object(indigo, "variable", types.SimpleNamespace(
                    create=create, updateValue=update), create=True):
            self.collector.collect()
            self.assertFalse(device.states["firmwareUpdateAvailable"])
            self.collector.set_test_override(1, 123)
            self.collector.collect()
            self.assertEqual(device.states["firmwareVersion"], "123")
            self.assertTrue(device.states["firmwareUpdateAvailable"])
            self.assertIn("[TEST OVERRIDE]", variables[
                version_collection.UPDATE_VARIABLE_NAME].value)
            self.assertEqual(
                self.plugin.eventCoordinator.trigger_global_event.call_count, 1)
            self.collector.collect()
            self.assertEqual(
                self.plugin.eventCoordinator.trigger_global_event.call_count, 1)
            self.collector.clear_test_override(1)
            self.collector.collect()
            self.assertEqual(device.states["firmwareVersion"], "124")
            self.assertFalse(device.states["firmwareUpdateAvailable"])
            self.assertEqual(variables[
                version_collection.UPDATE_VARIABLE_NAME].value, "")
            self.assertEqual(
                self.plugin.eventCoordinator.trigger_global_event.call_count, 1)

    def test_temporary_override_rejects_invalid_versions_and_clears_on_stop(self):
        device = FakeDevice(1, "Test device")
        self.plugin.activePhidgets[1] = wrapper(
            device, NativePhidget(124, "TESTUSB"))
        self.collector.request_collection = mock.Mock()
        with self.assertRaises(ValueError):
            self.collector.set_test_override(1, 124)
        with self.assertRaises(ValueError):
            self.collector.set_test_override(1, 0)
        self.collector.set_test_override(1, 123)
        self.assertEqual(self.collector._test_version_for(1), 123)
        self.collector.stop()
        self.assertIsNone(self.collector._test_version_for(1))

    def test_supplied_catalog_separates_interfacekit_revisions(self):
        catalog = version_collection.FirmwareCatalog.loaded(
            version_collection.CATALOG_PATH)

        # Serial 312564 is an early 1017 running firmware 100.  The supplied
        # Admin catalog starts at hardware revision 1017_2, so it must not be
        # offered that revision's firmware.
        self.assertEqual(catalog.versions("1017_1"), set())
        self.assertEqual(catalog.versions("1017_2"), {210, 211, 212})
        self.assertEqual(catalog.versions("1018_2"), set())
        self.assertEqual(catalog.versions("1018_3"), {1000, 1001})
        self.assertIn(105, catalog.versions("HUM1000", 0x014))

    def test_firmware_can_exist_without_upgrade_support(self):
        device = FakeDevice()
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device, phidget=NativePhidget(87, ""))

        self.collector.collect()

        self.assertTrue(device.states["hasFirmware"])
        self.assertFalse(device.states["firmwareUpgradeable"])
        self.assertEqual(device.states["firmwareUpgradeabilityStatus"],
                         "Not supported")

    def test_vint_catalog_match_uses_upgrade_identifier_and_vint_id(self):
        device = FakeDevice()
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device,
            phidget=NativePhidget(104, "HUM1000", vint_id=0x014),
            hub_port=2)

        self.collector.collect()

        self.assertTrue(device.states["firmwareUpgradeable"])
        self.assertEqual(device.states["latestFirmwareVersion"], "105")
        self.assertTrue(device.states["firmwareUpdateAvailable"])

    def test_major_update_is_identified_separately(self):
        device = FakeDevice()
        collector = version_collection.VersionCollector(
            self.plugin, self.logger,
            firmware_catalog=version_collection.FirmwareCatalog((
                "TESTUSBv123.bin.rc4", "TESTUSBv201.bin.rc4")))
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device, phidget=NativePhidget(123, "TESTUSB"))

        collector.collect()

        self.assertTrue(device.states["firmwareUpdateAvailable"])
        self.assertTrue(device.states["firmwareMajorUpdateAvailable"])
        self.assertEqual(device.states["firmwareUpdateStatus"],
                         "Major update available")

    def test_old_interfacekit_without_catalog_match_has_no_update(self):
        device = FakeDevice(device_type="digitalInput")
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device, phidget=NativePhidget(904, "1018_2"))

        self.collector.collect()

        self.assertFalse(device.states["firmwareUpgradeable"])
        self.assertEqual(device.states["latestFirmwareVersion"], "")
        self.assertFalse(device.states["firmwareUpdateAvailable"])
        self.assertEqual(device.ui_values["firmwareUpdateAvailable"], "No")
        self.assertEqual(device.states["firmwareUpdateStatus"],
                         "No compatible firmware")

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

    def test_hub_port_mode_does_not_claim_parent_hub_firmware(self):
        device = FakeDevice(device_type="voltageInput")
        phidget = mock.Mock()
        phidget.getDeviceVersion.return_value = 110
        self.plugin.activePhidgets[device.id] = wrapper(
            device=device, phidget=phidget, hub_port_device=True)

        self.collector.collect()

        phidget.getDeviceVersion.assert_not_called()
        self.assertFalse(device.states["hasFirmware"])
        self.assertEqual(device.states["firmwareVersion"], "")
        self.assertFalse(device.states["firmwareUpgradeable"])
        self.assertEqual(device.states["firmwareUpgradeabilityStatus"],
                         "Not applicable")
        self.assertEqual(device.states["firmwareVersionStatus"], "No firmware")
        self.assertEqual(device.states["versionCheckError"], "")

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
        server_device = FakeDevice(
            2, "Server A monitor", device_type="networkServer")
        monitor = types.SimpleNamespace(
            serverName="Server A", indigoDevice=server_device)
        self.plugin._networkServerDevices = [monitor]
        self.plugin.activePhidgets[server_device.id] = monitor

        self.collector.collect()

        self.assertEqual(server_device.states["serverVersion"], "2.5")
        self.assertEqual(server_device.states["serverVersionStatus"], "Collected")
        self.assertNotIn("hasFirmware", server_device.states)

    def test_server_without_attached_channel_is_unavailable(self):
        server_device = FakeDevice(
            2, "Server B monitor", device_type="networkServer")
        monitor = types.SimpleNamespace(
            serverName="Server B", indigoDevice=server_device)
        self.plugin._networkServerDevices = [monitor]
        self.plugin.activePhidgets[server_device.id] = monitor

        self.collector.collect()

        self.assertEqual(server_device.states["serverVersionStatus"],
                         "Unavailable")
        self.assertIn("No attached", server_device.states["versionCheckError"])

    def test_collector_start_does_not_rebuild_device_state_lists_early(self):
        owned = FakeDevice()
        foreign = FakeDevice(2, plugin_id="another.plugin")
        with mock.patch.object(sys.modules["indigo"], "devices",
                               [owned, foreign], create=True):
            self.collector.start()

        self.assertEqual(owned.refreshes, 0)
        self.assertEqual(foreign.refreshes, 0)


if __name__ == "__main__":
    unittest.main()
