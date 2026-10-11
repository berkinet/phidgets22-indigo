import json
import tempfile
import os
import unittest
from unittest import mock
from test_phidget_lifecycle import TestPhidget, phidget_module
from outage_store import OutageStore


class OutagePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.phidget = TestPhidget()
        self.device = self.phidget.indigoDevice
        self.device.replacePluginPropsOnServer = mock.Mock(side_effect=AssertionError('Device configuration must not be written'))
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = OutageStore(folder.name)
        self.phidget.indigo_plugin.outageStore = self.store
        self.device.pluginProps['normalSetting'] = 'retained'

    def record(self, started=100000, due=200900, daily=True):
        return json.dumps(dict(address=self.phidget._outage_address(),
                              started=started, due=due, daily=daily))

    def test_restart_preserves_elapsed_deadline_and_daily_state(self):
        self.store.save(self.device.id, json.loads(self.record()))
        with mock.patch.object(phidget_module.time, 'time', return_value=200000), \
                mock.patch.object(phidget_module.time, 'monotonic', return_value=500), \
                mock.patch.object(phidget_module.threading, 'Timer') as timer:
            self.phidget.start()
            self.assertEqual(self.phidget._detached_at, -99500)
            self.assertTrue(self.phidget._daily_reminder_reported)
            self.assertEqual(timer.call_args.args[0], 900)
            self.assertEqual(self.store.load(self.device.id)['started'], 100000)
            self.phidget.onAttachHandler(self.phidget.native)
            self.assertIsNone(self.store.load(self.device.id))
            self.device.replacePluginPropsOnServer.assert_not_called()
            self.assertEqual(self.device.pluginProps['normalSetting'], 'retained')

    def test_overdue_reminder_keeps_startup_grace(self):
        self.store.save(self.device.id, json.loads(self.record(due=150000)))
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
                with open(self.store._path(self.device.id), 'w') as saved:
                    saved.write(raw)
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
            record = self.store.load(self.device.id)
            self.assertEqual(record['started'], 200000)
            self.phidget._detached_at = 500 - 90000
            self.phidget._schedule_detached_reminder(self.phidget._timer_generation)
            record = self.store.load(self.device.id)
            self.assertEqual(record['due'], 286400)

    def test_file_store_survives_new_store_and_does_not_change_configuration(self):
        record = json.loads(self.record())
        self.store.save(self.device.id, record)
        reloaded = OutageStore(self.store.directory)
        self.assertEqual(reloaded.load(self.device.id), record)
        self.store.save(self.device.id, dict(record, due=300000))
        self.assertEqual(reloaded.load(self.device.id)['due'], 300000)
        self.assertFalse(os.path.exists(self.store._path(self.device.id) + '.tmp'))
        self.store.save(self.device.id, None)
        self.assertIsNone(reloaded.load(self.device.id))
        self.device.replacePluginPropsOnServer.assert_not_called()

    def test_failed_save_does_not_interrupt_reminder(self):
        self.phidget._state = 'detached'
        self.phidget._detached_at = 100
        with mock.patch.object(self.store, 'save', side_effect=OSError('disk full')), \
                mock.patch.object(phidget_module.threading, 'Timer') as timer:
            self.phidget._schedule_detached_reminder(self.phidget._timer_generation)
            timer.return_value.start.assert_called_once()
        self.phidget.test_logger.error.assert_called_once()
