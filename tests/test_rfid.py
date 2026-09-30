import pathlib
import sys
import threading
import types
import unittest
from unittest import mock
from xml.etree import ElementTree

SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))
from rfid import RFIDPhidget
from phidget import PhidgetBase, PeripheralUnavailableError
from event_coordinator import EventCoordinator
import event_coordinator
import discovery
import device_factory


class RFIDTests(unittest.TestCase):
    def reader(self, device_id=1):
        reader = object.__new__(RFIDPhidget)
        reader._tag_lock = threading.RLock()
        reader._present_tag = None
        reader.rfidPolicyProps = {}
        reader._state = "attached"
        reader.antennaEnabled = True
        reader.phidget = mock.Mock()
        reader.indigoDevice = mock.Mock(id=device_id)
        reader.indigoDevice.name = "Reader %s" % device_id
        reader.indigo_plugin = mock.Mock(pluginPrefs={})
        reader.logger = mock.Mock()
        reader.states = {}
        reader.updateStateOnServer = lambda key, value, **kwargs: reader.states.__setitem__(key, value)
        return reader

    def test_any_tag_preserves_leading_zeroes_and_last_tag_after_loss(self):
        reader = self.reader()
        reader.onTagHandler(None, "0000123456", 1)
        reader.onTagHandler(None, "0000123456", 1)
        reader.onTagLostHandler(None, "0000123456", 1)
        reader.onTagLostHandler(None, "0000123456", 1)
        self.assertEqual(reader.states["lastTag"], "0000123456")
        self.assertEqual(reader.states["protocol"], "EM4100")
        self.assertFalse(reader.states["tagPresent"])
        self.assertEqual(reader.indigo_plugin.triggerEvent.call_args_list,
                         [mock.call(reader, "rfidTagDetected"), mock.call(reader, "rfidAllowedTagDetected"), mock.call(reader, "rfidTagLost")])

    def test_old_loss_does_not_clear_new_tag(self):
        reader = self.reader()
        reader.onTagHandler(None, "old", 1)
        reader.onTagHandler(None, "new", 2)
        reader.onTagLostHandler(None, "old", 1)
        self.assertTrue(reader.states["tagPresent"])
        self.assertEqual(reader.states["lastTag"], "new")
        self.assertEqual(reader.states["protocol"], "ISO11785 FDX-B")

    def test_attach_without_tag_does_not_read_undefined_last_tag(self):
        reader = self.reader()
        reader.phidget.getTagPresent.return_value = False
        reader.configureAttachedPhidget(reader.phidget)
        reader.phidget.getLastTag.assert_not_called()
        reader.indigo_plugin.triggerEvent.assert_not_called()

    def test_disconnect_clears_presence_without_tag_lost_and_reconnect_detects(self):
        reader = self.reader()
        reader.onTagHandler(None, "chicken", 3)
        with mock.patch.object(PhidgetBase, "onDetachHandler"):
            reader.onDetachHandler(None)
        self.assertFalse(reader.states["tagPresent"])
        self.assertFalse(reader.states["antennaEnabled"])
        self.assertEqual(reader.states["lastTag"], "chicken")
        self.assertEqual(reader.indigo_plugin.triggerEvent.call_count, 2)
        reader.phidget.getTagPresent.return_value = True
        reader.phidget.getLastTag.return_value = ("chicken", 3)
        reader.configureAttachedPhidget(reader.phidget)
        self.assertTrue(reader.states["tagPresent"])
        self.assertEqual(reader.indigo_plugin.triggerEvent.call_count, 4)

    def test_antenna_disable_clears_presence_and_survives_reattach(self):
        reader = self.reader()
        reader.onTagHandler(None, "tag", 1)
        reader.phidget.getAntennaEnabled.return_value = False
        reader.setAntennaEnabled(False)
        self.assertFalse(reader.states["tagPresent"])
        self.assertFalse(reader.antennaEnabled)
        reader.phidget.getTagPresent.return_value = False
        reader.configureAttachedPhidget(reader.phidget)
        reader.phidget.setAntennaEnabled.assert_called_with(False)

    def test_failures_are_reported_without_changing_desired_antenna(self):
        reader = self.reader()
        reader.phidget.setAntennaEnabled.side_effect = RuntimeError("unplugged")
        reader.setAntennaEnabled(False)
        self.assertTrue(reader.antennaEnabled)
        reader.logger.error.assert_called_once()
        reader.indigoDevice.setErrorStateOnServer.assert_called_once()
        with self.assertRaises(PeripheralUnavailableError):
            reader.configureAttachedPhidget(reader.phidget)

    def test_callback_and_trigger_failures_do_not_escape(self):
        reader = self.reader()
        reader.indigo_plugin.triggerEvent.side_effect = RuntimeError("trigger unavailable")
        reader.onTagHandler(None, "tag", 1)
        self.assertEqual(reader.logger.error.call_count, 2)
        reader._state = "stopped"
        reader.onTagHandler(None, "ignored", 1)
        self.assertEqual(reader.states["lastTag"], "tag")

    def test_reader_triggers_are_isolated_by_indigo_device(self):
        coordinator = EventCoordinator()
        for device_id in (1, 2):
            coordinator.start_processing(types.SimpleNamespace(
                id=device_id + 10, pluginTypeId="rfidTagDetected",
                pluginProps={"indigoDevice": str(device_id)}))
        with mock.patch.object(event_coordinator.indigo, "trigger", create=True) as trigger:
            coordinator.trigger_event(self.reader(2), "rfidTagDetected")
            trigger.execute.assert_called_once_with(12)

    def test_discovery_factory_and_xml_expose_rfid(self):
        self.assertEqual(discovery.CHANNEL_CLASSES_BY_DEVICE_TYPE["rfid"], "PhidgetRFID")
        plugin = mock.Mock(pluginPrefs={})
        device = types.SimpleNamespace(pluginProps={"serialNumber": "123456", "channel": "0"}, deviceTypeId="rfid")
        with mock.patch.object(device_factory, "RFIDPhidget") as wrapper:
            device_factory.create_phidget(plugin, device)
        info = wrapper.call_args.kwargs["channelInfo"]
        self.assertEqual(info.serialNumber, 123456)
        self.assertEqual(info.channel, 0)
        devices = ElementTree.parse(SERVER_PLUGIN / "Devices.xml")
        self.assertIsNotNone(devices.find("./Device[@id='rfid']"))
        actions = ElementTree.parse(SERVER_PLUGIN / "Actions.xml")
        required_actions = {"rfidEnableAntenna", "rfidDisableAntenna",
                            "rfidSimulateTag", "rfidSimulateTagLost"}
        for action_id in required_actions:
            action = actions.find("./Action[@id='%s']" % action_id)
            self.assertIsNotNone(action)
            self.assertEqual(action.get("deviceFilter"), "self.rfid")
            self.assertEqual(action.get("uiPath"), "DeviceActions")
            self.assertEqual(action.findtext("CallbackMethod"), action_id)
        events = ElementTree.parse(SERVER_PLUGIN / "Events.xml")
        for event_id in ("rfidTagDetected", "rfidTagLost",
                         "rfidAllowedTagDetected", "rfidDeniedTagDetected"):
            event = events.find("./Event[@id='%s']" % event_id)
            self.assertIsNotNone(event)
            self.assertEqual(event.get("deviceFilter"), "self.rfid")
            self.assertIsNotNone(event.find("./ConfigUI/Field[@id='indigoDevice']"))

    def test_handlers_registered_before_open(self):
        native = mock.Mock()
        device = types.SimpleNamespace(id=1, name="Reader", pluginProps={},
                                       updateStateOnServer=mock.Mock())
        with mock.patch("rfid.RFID", return_value=native):
            reader = RFIDPhidget(indigoDevice=device,
                                 indigo_plugin=mock.Mock(pluginPrefs={}), logger=mock.Mock())
        def check_handlers():
            for setter, handler in (
                    ("setOnTagHandler", reader.onTagHandler),
                    ("setOnTagLostHandler", reader.onTagLostHandler),
                    ("setOnAttachHandler", reader.onAttachHandler),
                    ("setOnDetachHandler", reader.onDetachHandler),
                    ("setOnErrorHandler", reader.onErrorHandler)):
                getattr(native, setter).assert_called_once_with(handler)
        native.open.side_effect = check_handlers
        with mock.patch("phidget.threading.Timer"):
            try:
                reader.start()
                native.open.assert_called_once_with()
            finally:
                reader.stop()


class SimulationTests(unittest.TestCase):
    def reader(self, device_id=1):
        from rfid import SimulatedRFIDPhidget
        device = mock.Mock(id=device_id, pluginProps={}, states={})
        device.name = "Dummy %s" % device_id
        plugin = mock.Mock(pluginPrefs={})
        reader = SimulatedRFIDPhidget(indigoDevice=device, indigo_plugin=plugin, logger=mock.Mock())
        reader.states = {}
        reader.updateStateOnServer = lambda key, value, **kwargs: reader.states.__setitem__(key, value)
        reader.start()
        return reader

    def test_lifecycle_does_not_construct_hardware_or_start_timers(self):
        with mock.patch("rfid.RFID", side_effect=AssertionError("native handle")):
            reader = self.reader()
            self.assertEqual(reader._state, "attached")
            self.assertIsNone(reader.timer)
            self.assertEqual(reader.states["connectionType"], "Simulated RFID reader")
            reader.stop()
            self.assertEqual(reader._state, "stopped")
            self.assertFalse(reader.states["tagPresent"])

    def test_two_readers_are_independent_and_preserve_ids(self):
        first, second = self.reader(1), self.reader(2)
        first.simulateTag("000001", 1)
        self.assertEqual(first.states["lastTag"], "000001")
        self.assertTrue(first.states["tagPresent"])
        self.assertFalse(second.states["tagPresent"])
        second.indigo_plugin.triggerEvent.assert_not_called()
        first.simulateTag("000001", 1)
        self.assertEqual(first.indigo_plugin.triggerEvent.call_args_list,
                         [mock.call(first, "rfidTagDetected"), mock.call(first, "rfidAllowedTagDetected")])
        first.simulateTag()
        self.assertFalse(first.states["tagPresent"])
        self.assertEqual(first.states["lastTag"], "000001")
        first.indigo_plugin.triggerEvent.assert_called_with(first, "rfidTagLost")

    def test_replacement_reports_loss_then_detection(self):
        reader = self.reader()
        reader.simulateTag("first", 3)
        reader.indigo_plugin.triggerEvent.reset_mock()
        reader.simulateTag("second", 3)
        self.assertEqual(reader.indigo_plugin.triggerEvent.call_args_list,
                         [mock.call(reader, "rfidTagLost"), mock.call(reader, "rfidTagDetected"), mock.call(reader, "rfidAllowedTagDetected")])

    def test_antenna_disabled_and_invalid_scan_report_errors(self):
        reader = self.reader()
        reader.setAntennaEnabled(False)
        reader.simulateTag("123", 1)
        reader.simulateTag("", 1)
        reader.simulateTag("123", 99)
        self.assertFalse(reader.states["tagPresent"])
        self.assertEqual(reader.logger.error.call_count, 3)
        reader.setAntennaEnabled(True)
        reader.simulateTag("123", 1)
        self.assertTrue(reader.states["tagPresent"])
        reader.indigoDevice.setErrorStateOnServer.assert_called_with(None)

    def test_config_can_save_without_discovery(self):
        from discovery_ui import DiscoveryUiMixin
        ui = object.__new__(DiscoveryUiMixin)
        ui.discoveryInventory = None
        with mock.patch.object(sys.modules["indigo"], "Dict", dict, create=True):
            values, errors = ui.getDeviceConfigUiValues({"rfidSimulation": True}, "rfid", 0)
            result = ui.validateDeviceConfigUi(values, "rfid", 0)
        self.assertTrue(result[0])
        self.assertEqual(result[1]["serialNumber"], "")
        self.assertTrue(values["compatibleModelFound"])

    def test_simulation_actions_reject_physical_readers(self):
        from actions import ActionsMixin
        from runtime_registry import RuntimeDeviceRegistry
        ui = object.__new__(ActionsMixin)
        ui.logger = mock.Mock()
        ui.runtimeRegistry = RuntimeDeviceRegistry()
        physical = mock.Mock(spec=RFIDPhidget)
        ui.runtimeRegistry.register(1, physical)
        ui.rfidSimulateTag(types.SimpleNamespace(deviceId=1, props={"tag": "123"}))
        ui.logger.error.assert_called_once()

    def test_factory_simulation_uses_no_native_handle(self):
        from rfid import SimulatedRFIDPhidget
        plugin = mock.Mock(pluginPrefs={})
        device = mock.Mock(pluginProps={"rfidSimulation": True}, deviceTypeId="rfid")
        with mock.patch("rfid.RFID", side_effect=AssertionError("native handle")):
            reader = device_factory.create_phidget(plugin, device)
        self.assertIsInstance(reader, SimulatedRFIDPhidget)
        self.assertFalse(reader.channelInfo.netInfo.isRemote)
