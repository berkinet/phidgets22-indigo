import json
import unittest
from unittest import mock
from test_phidget_lifecycle import TestPhidget, phidget_module


class OutagePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.phidget = TestPhidget()
        self.device = self.phidget.indigoDevice
        self.device.replacePluginPropsOnServer = lambda props: setattr(self.device, 'pluginProps', props)
        self.device.pluginProps['normalSetting'] = 'retained'

    def record(self, started=100000, due=200900, daily=True):
        return json.dumps(dict(address=self.phidget._outage_address(),
                              started=started, due=due, daily=daily))

    def test_restart_preserves_elapsed_deadline_and_daily_state(self):
        self.device.pluginProps['detachedOutageRecord'] = self.record()
        with mock.patch.object(phidget_module.time, 'time', return_value=200000), \
                mock.patch.object(phidget_module.time, 'monotonic', return_value=500), \
                mock.patch.object(phidget_module.threading, 'Timer') as timer:
            self.phidget.start()
            self.assertEqual(self.phidget._detached_at, -99500)
            self.assertTrue(self.phidget._daily_reminder_reported)
            self.assertEqual(timer.call_args.args[0], 900)
            self.assertEqual(json.loads(self.device.pluginProps['detachedOutageRecord'])['started'], 100000)
            self.phidget.onAttachHandler(self.phidget.native)
            self.assertNotIn('detachedOutageRecord', self.device.pluginProps)
            self.assertEqual(self.device.pluginProps['normalSetting'], 'retained')

    def test_overdue_reminder_keeps_startup_grace(self):
        self.device.pluginProps['detachedOutageRecord'] = self.record(due=150000)
        with mock.patch.object(phidget_module.time, 'time', return_value=200000), \
                mock.patch.object(phidget_module.threading, 'Timer') as timer:
            self.phidget.start()
            self.assertEqual(timer.call_args.args[0], self.phidget.initial_connection_timeout)

    def test_changed_address_and_invalid_records_start_fresh(self):
        changed = json.loads(self.record())
        changed['address'][0] = 999999
        for raw in (json.dumps(changed), 'invalid json', self.record(started=float('nan'))):
            with self.subTest(raw=raw), \
                    mock.patch.object(phidget_module.time, 'time', return_value=200000), \
                    mock.patch.object(phidget_module.time, 'monotonic', return_value=500), \
                    mock.patch.object(phidget_module.threading, 'Timer'):
                self.device.pluginProps['detachedOutageRecord'] = raw
                self.phidget.start()
                self.assertEqual(self.phidget._detached_at, 500)
                self.assertIsNone(self.phidget._restored_reminder_due)

    def test_detach_persists_and_daily_schedule_updates_due_time(self):
        self.phidget._state = 'attached'
        self.phidget._detached_at = None
        with mock.patch.object(phidget_module.time, 'time', return_value=200000), \
                mock.patch.object(phidget_module.time, 'monotonic', return_value=500), \
                mock.patch.object(phidget_module.threading, 'Timer'):
            self.phidget.onDetachHandler(self.phidget.native)
            record = json.loads(self.device.pluginProps['detachedOutageRecord'])
            self.assertEqual(record['started'], 200000)
            self.phidget._detached_at = 500 - 90000
            self.phidget._schedule_detached_reminder(self.phidget._timer_generation)
            record = json.loads(self.device.pluginProps['detachedOutageRecord'])
            self.assertEqual(record['due'], 286400)
