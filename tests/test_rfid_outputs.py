import pathlib
import sys
import types
import unittest
from unittest import mock
from xml.etree import ElementTree

SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))
from rfid_outputs import RFIDOutputs, OUTPUTS
from rfid import RFIDPhidget, SimulatedRFIDPhidget
from actions import ActionsMixin
from runtime_registry import RuntimeDeviceRegistry


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.owner = mock.Mock()
        self.owner._state = "attached"
        self.owner.indigoDevice.name = "Reader"
        self.states = {}
        self.owner.updateStateOnServer.side_effect = lambda key, value: self.states.__setitem__(key, value)
        self.handles = [mock.Mock() for _ in range(3)]
        for handle in self.handles:
            handle.getAttached.return_value = True
            handle.getState.return_value = False
        self.factory = mock.patch("rfid_outputs.DigitalOutput", side_effect=self.handles).start()
        self.timer = mock.patch("rfid_outputs.threading.Timer").start()
        self.addCleanup(mock.patch.stopall)
        self.outputs = RFIDOutputs(self.owner)
        self.addCleanup(self.outputs.stop)
        self.reader = mock.Mock()
        self.reader.getDeviceSerialNumber.return_value = 12345
        self.reader.getIsRemote.return_value = True
        self.reader.getServerName.return_value = "remote-server"
        self.outputs.start(self.reader)

    def test_channel_identity_and_initial_read_do_not_write_hardware(self):
        for channel, handle in enumerate(self.handles):
            handle.setDeviceSerialNumber.assert_called_once_with(12345)
            handle.setServerName.assert_called_once_with("remote-server")
            handle.setIsRemote.assert_called_once_with(True)
            handle.setChannel.assert_called_once_with(channel)
            handle.open.assert_called_once_with()
            handle.setState.assert_not_called()
            handle.getState.return_value = channel == 1
            handle.setOnAttachHandler.call_args.args[0](handle)
            self.assertEqual(self.states[OUTPUTS[channel][0]], channel == 1)
            self.assertTrue(self.states[OUTPUTS[channel][0] + "Available"])

    def test_each_action_reads_back_state_and_leaves_other_channels_alone(self):
        for channel, handle in enumerate(self.handles):
            with self.subTest(channel=channel):
                for enabled in (True, False):
                    handle.getState.return_value = enabled
                    self.outputs.set(channel, enabled)
                    handle.setState.assert_called_with(enabled)
                    self.assertEqual(self.states[OUTPUTS[channel][0]], enabled)
        # A successful setter is not treated as a substitute for readback.
        self.handles[0].getState.return_value = False
        self.outputs.set(0, True)
        self.assertFalse(self.states["digitalOutput"])
        self.assertEqual([h.setState.call_count for h in self.handles], [3, 2, 2])

    def test_failure_preserves_last_value_marks_unavailable_and_recovers(self):
        handle = self.handles[0]
        handle.getState.return_value = True
        self.outputs.refresh(0, handle)
        handle.setState.side_effect = RuntimeError("write\nfailed")
        self.outputs.set(0, False)
        self.assertTrue(self.states["digitalOutput"])
        self.assertFalse(self.states["digitalOutputAvailable"])
        self.owner.logger.error.assert_called_once()
        self.assertNotIn("\n", self.owner.logger.error.call_args.args[-1])
        self.outputs.refresh(0, handle)
        self.assertTrue(self.states["digitalOutputAvailable"])

    def test_poll_observes_external_change_and_reconnect_without_replaying_commands(self):
        handle = self.handles[2]
        handle.getState.return_value = True
        self.outputs._poll(self.outputs.generation)
        self.assertTrue(self.states["onboardLED"])
        handle.getAttached.return_value = False
        handle.setOnDetachHandler.call_args.args[0](handle)
        self.assertFalse(self.states["onboardLEDAvailable"])
        self.outputs.set(2, False)
        handle.setState.assert_not_called()
        handle.getAttached.return_value = True
        handle.getState.return_value = False
        handle.setOnAttachHandler.call_args.args[0](handle)
        self.assertFalse(self.states["onboardLED"])
        self.assertTrue(self.states["onboardLEDAvailable"])
        handle.setState.assert_not_called()

    def test_stop_closes_every_handle_and_ignores_late_callbacks_and_timer(self):
        generation = self.outputs.generation
        self.handles[0].close.side_effect = RuntimeError("close failed")
        self.outputs.stop()
        before = dict(self.states)
        self.outputs._poll(generation)
        for channel, handle in enumerate(self.handles):
            handle.close.assert_called_once_with()
            handle.setOnAttachHandler.call_args.args[0](handle)
            handle.setOnErrorHandler.call_args.args[0](handle, 1, "late error")
        self.assertEqual(self.states, before)
        self.assertFalse(self.outputs.running)

    def test_partial_open_failure_does_not_disable_other_outputs(self):
        self.outputs.stop()
        handles = [mock.Mock() for _ in range(3)]
        handles[1].open.side_effect = RuntimeError("in use")
        with mock.patch("rfid_outputs.DigitalOutput", side_effect=handles):
            self.outputs.start(self.reader)
        self.assertEqual(set(self.outputs.handles), {0, 2})
        handles[1].close.assert_called_once_with()
        self.assertFalse(self.states["ledDriverAvailable"])
        handles[2].getState.return_value = True
        self.outputs.set(2, True)
        self.assertTrue(self.states["onboardLED"])

    def test_local_identity_does_not_select_server(self):
        self.outputs.stop()
        handles = [mock.Mock() for _ in range(3)]
        self.reader.getIsRemote.return_value = False
        with mock.patch("rfid_outputs.DigitalOutput", side_effect=handles):
            self.outputs.start(self.reader)
        for handle in handles:
            handle.setIsRemote.assert_called_once_with(False)
            handle.setServerName.assert_not_called()

    def test_read_and_publication_errors_do_not_escape_callbacks(self):
        handle = self.handles[0]
        handle.getState.side_effect = RuntimeError("read failed")
        self.outputs.refresh(0, handle)
        self.assertFalse(self.states["digitalOutputAvailable"])
        self.owner.updateStateOnServer.side_effect = RuntimeError("Indigo unavailable")
        self.outputs.detached(0, handle)
        self.outputs.failed(0, handle, 1, "hardware error")
        self.outputs.stop()


class IntegrationTests(unittest.TestCase):
    def test_physical_reader_owns_outputs_and_exposes_state_definitions(self):
        from phidget import PhidgetBase
        native = mock.Mock()
        native.getTagPresent.return_value = False
        with mock.patch("rfid.RFID", return_value=native), mock.patch("rfid.RFIDOutputs") as factory:
            reader = RFIDPhidget(indigoDevice=mock.Mock(pluginProps={}),
                                 indigo_plugin=mock.Mock(pluginPrefs={}), logger=mock.Mock())
        manager = factory.return_value
        manager.start.assert_not_called()
        reader.updateStateOnServer = mock.Mock()
        reader.configureAttachedPhidget(native)
        manager.start.assert_called_once_with(native)
        reader.stateList = lambda *states: states
        definitions = {key: kind for kind, key, label in reader.getDeviceStateList()}
        for key, label in OUTPUTS:
            self.assertEqual(definitions[key], "bool")
            self.assertEqual(definitions[key + "Available"], "bool")
        self.assertEqual(reader.getDeviceDisplayStateId(), "tagPresent")
        with mock.patch.object(PhidgetBase, "stop"):
            reader.stop()
        manager.stop.assert_called_once_with()

    def test_action_definitions_dispatch_to_correct_output_and_validate(self):
        ui = object.__new__(ActionsMixin)
        ui.logger = mock.Mock()
        ui.runtimeRegistry = RuntimeDeviceRegistry()
        reader = mock.Mock(spec=RFIDPhidget)
        ui.runtimeRegistry.register(1, reader)
        actions = ElementTree.parse(SERVER_PLUGIN / "Actions.xml")
        for channel, action_id in enumerate(("rfidDigitalOutput", "rfidLEDDriver", "rfidOnboardLED")):
            definition = actions.find(".//Action[@id='%s']" % action_id)
            self.assertEqual(definition.attrib["deviceFilter"], "self.rfid")
            for state in ("on", "off"):
                action = types.SimpleNamespace(deviceId=1, pluginTypeId=action_id, props={"outputState": state})
                getattr(ui, definition.findtext("CallbackMethod"))(action)
                reader.setOutput.assert_called_with(channel, state == "on")
        reader.setOutput.reset_mock()
        ui.rfidSetOutput(types.SimpleNamespace(deviceId=1, pluginTypeId="rfidOnboardLED", props={}))
        ui.rfidSetOutput(types.SimpleNamespace(deviceId=99, pluginTypeId="rfidOnboardLED", props={"outputState": "on"}))
        reader.setOutput.assert_not_called()
        self.assertEqual(ui.logger.error.call_count, 2)

    def test_simulation_has_all_output_states_without_hardware_and_stops_cleanly(self):
        device = mock.Mock(pluginProps={})
        plugin = mock.Mock(pluginPrefs={})
        with mock.patch("rfid_outputs.DigitalOutput", side_effect=AssertionError("hardware")), mock.patch("rfid.RFID", side_effect=AssertionError("hardware")):
            reader = SimulatedRFIDPhidget(indigoDevice=device, indigo_plugin=plugin, logger=mock.Mock())
            states = {}
            reader.updateStateOnServer = lambda key, value, **kw: states.__setitem__(key, value)
            reader.start()
            for channel, (key, label) in enumerate(OUTPUTS):
                self.assertFalse(states[key])
                reader.setOutput(channel, True)
                self.assertTrue(states[key])
                self.assertTrue(states[key + "Available"])
            reader.stop()
            for key, label in OUTPUTS:
                self.assertFalse(states[key + "Available"])
            reader.setOutput(0, False)
            self.assertTrue(states["digitalOutput"])
            reader.start()
            self.assertFalse(states["digitalOutput"])
            reader.stop()
