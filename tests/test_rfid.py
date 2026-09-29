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
        reader._state = "attached"
        reader.antennaEnabled = True
        reader.phidget = mock.Mock()
        reader.indigoDevice = mock.Mock(id=device_id)
        reader.indigoDevice.name = "Reader %s" % device_id
        reader.indigo_plugin = mock.Mock()
        reader.logger = mock.Mock()
        reader.states = {}
        reader.updateStateOnServer = lambda key, value: reader.states.__setitem__(key, value)
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
                         [mock.call(reader, "rfidTagDetected"), mock.call(reader, "rfidTagLost")])

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
        self.assertEqual(reader.indigo_plugin.triggerEvent.call_count, 1)
        reader.phidget.getTagPresent.return_value = True
        reader.phidget.getLastTag.return_value = ("chicken", 3)
        reader.configureAttachedPhidget(reader.phidget)
        self.assertTrue(reader.states["tagPresent"])
        self.assertEqual(reader.indigo_plugin.triggerEvent.call_count, 2)

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
        reader.logger.error.assert_called_once()
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
        self.assertEqual(len(actions.findall("./Action[@deviceFilter='self.rfid']")), 2)
        events = ElementTree.parse(SERVER_PLUGIN / "Events.xml")
        self.assertEqual(len(events.findall("./Event[@deviceFilter='self.rfid']")), 2)

    def test_handlers_registered_before_open(self):
        reader = self.reader()
        reader.addPhidgetHandlers()
        reader.phidget.setOnTagHandler.assert_called_once_with(reader.onTagHandler)
        reader.phidget.setOnTagLostHandler.assert_called_once_with(reader.onTagLostHandler)
