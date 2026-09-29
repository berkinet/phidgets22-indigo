import pathlib
import sys
import threading
import types
import unittest
from unittest import mock

SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))
import indigo
from phidget import PhidgetBase
from rfid import RFIDPhidget, SimulatedRFIDPhidget
from rfid_presence import RFIDPresence, clear_delay_seconds
import rfid_tags


class FakeTimer:
    def __init__(self, delay, callback, args):
        self.delay, self.callback, self.args = delay, callback, args
        self.cancelled = False
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        # Deliberately deliver even cancelled callbacks to exercise races.
        self.callback(*self.args)


class PresenceTests(unittest.TestCase):
    def setUp(self):
        self.time = 0.0
        self.timers = []
        self.owner = types.SimpleNamespace(
            _tag_lock=threading.RLock(), rfidPolicyProps={"rfidPresenceClearMinutes": 5},
            updateStateOnServer=mock.Mock(), _report=mock.Mock())
        self.presence = RFIDPresence(self.owner, self.timer, lambda: self.time)

    def timer(self, seconds, callback, args):
        timer = FakeTimer(seconds, callback, args)
        self.timers.append(timer)
        return timer

    def test_continuous_allowed_presence_never_starts_a_timer(self):
        self.presence.update(True)
        self.time = 10000
        self.presence.update(True)
        self.assertTrue(self.presence.active)
        self.assertEqual(self.timers, [])
        self.owner.updateStateOnServer.assert_called_with("presenceActive", True)

    def test_loss_starts_delay_and_expires_at_deadline(self):
        self.presence.update(True)
        self.time = 1000
        self.presence.update(False)
        self.assertEqual(self.timers[-1].delay, 300)
        self.assertTrue(self.presence.active)
        self.time = 1300
        self.timers[-1].fire()
        self.assertFalse(self.presence.active)
        self.owner.updateStateOnServer.assert_called_with("presenceActive", False)

    def test_return_cancels_old_callback_and_next_loss_starts_fresh_delay(self):
        self.presence.update(True)
        self.presence.update(False)
        old = self.timers[-1]
        self.time = 200
        self.presence.update(True)
        self.assertTrue(old.cancelled)
        self.time = 301
        old.fire()
        self.assertTrue(self.presence.active)
        self.presence.update(False)
        self.assertEqual(self.presence.deadline, 601)
        self.time = 600
        self.timers[-1].fire()
        self.assertTrue(self.presence.active)
        self.assertEqual(self.timers[-1].delay, 1)
        self.time = 601
        self.timers[-1].fire()
        self.assertFalse(self.presence.active)

    def test_denied_and_repeated_loss_do_not_activate_or_extend_delay(self):
        self.presence.update(False)
        self.assertFalse(self.presence.active)
        self.assertEqual(self.timers, [])
        self.presence.update(True)
        self.presence.update(False)
        self.time = 100
        self.presence.update(False)
        self.assertEqual(len(self.timers), 1)
        self.assertEqual(self.presence.deadline, 300)

    def test_zero_and_fractional_delays(self):
        self.owner.rfidPolicyProps["rfidPresenceClearMinutes"] = "0"
        self.presence.update(True)
        self.presence.update(False)
        self.assertFalse(self.presence.active)
        self.assertFalse(self.timers)
        self.owner.rfidPolicyProps["rfidPresenceClearMinutes"] = "0.5"
        self.presence.update(True)
        self.presence.update(False)
        self.assertEqual(self.timers[-1].delay, 30)

    def test_stop_and_reset_clear_state_and_ignore_old_timers(self):
        self.presence.update(True)
        self.presence.update(False)
        old = self.timers[-1]
        self.presence.stop()
        self.assertFalse(self.presence.active)
        self.assertTrue(old.cancelled)
        self.presence.update(True)
        self.assertFalse(self.presence.active)
        self.presence.reset()
        self.owner.updateStateOnServer.assert_called_with("presenceActive", False, triggerEvents=True)
        self.presence.update(True)
        self.time = 500
        old.fire()
        self.assertTrue(self.presence.active)

    def test_delay_change_applies_to_next_loss_not_pending_timer(self):
        self.presence.update(True)
        self.presence.update(False)
        self.owner.rfidPolicyProps["rfidPresenceClearMinutes"] = "10"
        self.assertEqual(self.presence.deadline, 300)
        self.presence.update(True)
        self.presence.update(False)
        self.assertEqual(self.presence.deadline, 600)

    def test_timeout_publication_failure_is_reported_and_retried(self):
        self.presence.update(True)
        self.presence.update(False)
        self.time = 300
        self.owner.updateStateOnServer.side_effect = RuntimeError("server busy")
        self.timers[-1].fire()
        self.assertTrue(self.presence.active)
        self.owner._report.assert_called_once()
        self.assertEqual(self.timers[-1].delay, 1)
        self.owner.updateStateOnServer.side_effect = None
        self.time = 301
        self.timers[-1].fire()
        self.assertFalse(self.presence.active)

    def test_timer_start_failure_clears_presence_and_reports_error(self):
        self.presence.update(True)
        self.presence.timer_factory = mock.Mock(side_effect=RuntimeError("no timer"))
        self.presence.update(False)
        self.assertFalse(self.presence.active)
        self.owner._report.assert_called_once()

    def test_delay_validation_rejects_invalid_and_nonfinite_values(self):
        with mock.patch.object(indigo, "Dict", dict, create=True):
            for value in ("-1", "nan", "inf", "tomorrow", "1441", ""):
                with self.subTest(value=value):
                    self.assertIn("rfidPresenceClearMinutes", rfid_tags.validate({"rfidPresenceClearMinutes": value}))
        self.assertEqual(clear_delay_seconds({}), 0)
        self.assertEqual(clear_delay_seconds({"rfidPresenceClearMinutes": "1440"}), 86400)

    def reader(self, device_id=10):
        device = types.SimpleNamespace(id=device_id, name="Reader %s" % device_id,
                                       pluginProps={"rfidPresenceClearMinutes": "5"}, states={},
                                       setErrorStateOnServer=mock.Mock())
        device.updateStateOnServer = mock.Mock(side_effect=lambda key, value, **kwargs: device.states.__setitem__(key, value))
        plugin = types.SimpleNamespace(pluginPrefs={}, triggerEvent=mock.Mock())
        reader = SimulatedRFIDPhidget(indigoDevice=device, indigo_plugin=plugin, logger=mock.Mock())
        reader._presence = RFIDPresence(reader, self.timer, lambda: self.time)
        reader.start()
        return reader

    def test_indigo_first_detection_fires_state_events_and_two_readers_are_independent(self):
        first, second = self.reader(10), self.reader(11)
        first.simulateTag("0001", 1)
        self.assertTrue(first.indigoDevice.states["presenceActive"])
        self.assertFalse(second.indigoDevice.states["presenceActive"])
        self.assertIn(mock.call("presenceActive", value=True, triggerEvents=True),
                      first.indigoDevice.updateStateOnServer.call_args_list)
        first.simulateTag()
        self.assertFalse(first.indigoDevice.states["tagPresent"])
        self.assertTrue(first.indigoDevice.states["presenceActive"])
        self.time = 300
        self.timers[-1].fire()
        self.assertFalse(first.indigoDevice.states["presenceActive"])
        second.indigo_plugin.triggerEvent.assert_not_called()

    def test_disconnect_uses_delay_and_reattach_cancels_it(self):
        reader = self.reader()
        reader.simulateTag("0001", 1)
        with mock.patch.object(PhidgetBase, "onDetachHandler"):
            reader.onDetachHandler(None)
        self.assertFalse(reader.indigoDevice.states["tagPresent"])
        self.assertTrue(reader.indigoDevice.states["presenceActive"])
        old = self.timers[-1]
        native = mock.Mock()
        native.getTagPresent.return_value = True
        native.getLastTag.return_value = ("0001", 1)
        reader.configureAttachedPhidget(native)
        self.time = 500
        old.fire()
        self.assertTrue(reader.indigoDevice.states["presenceActive"])

    def test_antenna_disable_starts_countdown_and_stop_cancels(self):
        reader = self.reader()
        reader.simulateTag("0001", 1)
        reader.setAntennaEnabled(False)
        self.assertTrue(reader.indigoDevice.states["presenceActive"])
        self.assertFalse(reader.indigoDevice.states["tagPresent"])
        old = self.timers[-1]
        reader.stop()
        self.assertFalse(reader.indigoDevice.states["presenceActive"])
        self.assertTrue(old.cancelled)
        self.time = 300
        old.fire()
        self.assertFalse(reader.indigoDevice.states["presenceActive"])

    def test_allowed_replacement_does_not_pulse_presence_off_at_zero_delay(self):
        reader = self.reader()
        reader.rfidPolicyProps["rfidPresenceClearMinutes"] = 0
        reader.simulateTag("first", 1)
        reader.indigoDevice.updateStateOnServer.reset_mock()
        reader.simulateTag("second", 1)
        self.assertTrue(reader.indigoDevice.states["presenceActive"])
        self.assertFalse(any(call.args[0] == "presenceActive" for call in reader.indigoDevice.updateStateOnServer.call_args_list))

    def test_denied_replacement_does_not_hold_presence_past_countdown(self):
        reader = self.reader()
        reader.simulateTag("allowed", 1)
        with mock.patch("rfid_tags.evaluate_with_reason", return_value=(False, "denied")):
            reader.simulateTag("denied", 1)
        self.assertTrue(reader.indigoDevice.states["tagPresent"])
        self.time = 300
        self.timers[-1].fire()
        self.assertFalse(reader.indigoDevice.states["presenceActive"])

    def test_native_stop_cancels_presence_even_when_close_fails(self):
        reader = self.reader()
        reader.simulateTag("0001", 1)
        reader.simulateTag()
        old = self.timers[-1]
        with mock.patch.object(PhidgetBase, "stop", side_effect=RuntimeError("close failed")):
            with self.assertRaises(RuntimeError):
                RFIDPhidget.stop(reader)
        self.assertTrue(old.cancelled)
        self.assertFalse(reader.indigoDevice.states["presenceActive"])
