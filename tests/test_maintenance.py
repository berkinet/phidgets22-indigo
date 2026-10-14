import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock
SERVER = pathlib.Path(__file__).parents[1] / 'Phidgets22.indigoPlugin/Contents/Server Plugin'
sys.path.insert(0, str(SERVER))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))
from outage_store import OutageStore
import version_collection
import test_sgp41 as sgp_fixtures


class MaintenanceTests(unittest.TestCase):
    def test_outage_pruning_only_removes_obsolete_plugin_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = OutageStore(directory)
            store.save(1, {'started':1})
            store.save(2, {'started':2})
            untouched = pathlib.Path(directory) / 'another-plugin.json'
            untouched.write_text('{}')
            store.prune([1])
            self.assertEqual(store.load(1), {'started':1})
            self.assertIsNone(store.load(2))
            self.assertTrue(untouched.exists())

    def test_catalog_refresh_has_ttl_and_backs_off_fetch_failure(self):
        catalog = version_collection.FirmwareCatalog(())
        plugin = types.SimpleNamespace(pluginPrefs={})
        collector = version_collection.VersionCollector(plugin, mock.Mock(), firmware_catalog=catalog)
        collector._remote_catalog_enabled = True
        now = [100]
        with mock.patch.object(version_collection.time, 'monotonic', side_effect=lambda:now[0]), \
                mock.patch.object(version_collection, 'fetch_firmware_catalog', side_effect=RuntimeError('offline')) as fetch:
            collector._refresh_catalog()
            collector._refresh_catalog()
            fetch.assert_called_once()
            now[0] += 21600
            collector._refresh_catalog()
            self.assertEqual(fetch.call_count, 2)

    def test_dependent_start_before_provider_remains_registered_for_recovery(self):
        wrapper, adapter, device = sgp_fixtures.SGP41Tests().wrapper()
        wrapper.indigo_plugin.activePhidgets.clear()
        wrapper.start()
        self.assertEqual(wrapper._state, 'starting')
        device.setErrorStateOnServer.assert_called_with('Provider unavailable')
        from runtime_registry import registry_for
        registry_for(wrapper.indigo_plugin).register(42, adapter)
        with mock.patch.object(sgp_fixtures.i2c_peripheral.threading, 'Timer'):
            wrapper.providerReattached()
        device.setErrorStateOnServer.assert_called_with(None)

    def test_polled_generic_fault_recovers_and_rearms_reporting(self):
        wrapper, adapter, device = sgp_fixtures.SGP41Tests().wrapper()
        normal = adapter.i2cCommandResponse
        adapter.i2cCommandResponse = mock.Mock(side_effect=RuntimeError('offline'))
        with mock.patch.object(sgp_fixtures.i2c_peripheral.threading, 'Timer'):
            wrapper.start()
            wrapper._poll(wrapper._generation)
            wrapper.logger.error.assert_called_once()
            adapter.i2cCommandResponse = normal
            wrapper._poll(wrapper._generation)
            device.setErrorStateOnServer.assert_called_with(None)
            adapter.i2cCommandResponse = mock.Mock(side_effect=RuntimeError('offline'))
            wrapper._poll(wrapper._generation)
            self.assertEqual(wrapper.logger.error.call_count, 2)

    def test_deleted_device_record_is_removed_even_if_stop_fails(self):
        import test_server_outages as fixtures
        from runtime_registry import RuntimeDeviceRegistry
        plugin = fixtures.plugin_module.Plugin.__new__(fixtures.plugin_module.Plugin)
        plugin.logger = mock.Mock()
        plugin.runtimeRegistry = RuntimeDeviceRegistry()
        device = types.SimpleNamespace(id=1, name='Deleted sensor')
        runtime = mock.Mock()
        runtime.stop.side_effect = RuntimeError('close failed')
        plugin.runtimeRegistry.register(1, runtime)
        with tempfile.TemporaryDirectory() as directory:
            plugin.outageStore = OutageStore(directory)
            plugin.outageStore.save(1, {'started':1})
            plugin.deviceDeleted(device)
            self.assertIsNone(plugin.outageStore.load(1))
            self.assertIsNone(plugin.runtimeRegistry.get(1))
        plugin.logger.error.assert_called_once()

    def test_duplicate_start_disposes_previous_runtime_before_starting_new_one(self):
        import test_server_outages as fixtures
        from runtime_registry import RuntimeDeviceRegistry
        plugin = fixtures.plugin_module.Plugin.__new__(fixtures.plugin_module.Plugin)
        plugin.logger = mock.Mock()
        plugin.runtimeRegistry = RuntimeDeviceRegistry()
        device = types.SimpleNamespace(id=1, name='Sensor', deviceTypeId='temperatureSensor',
                                       stateListOrDisplayStateIdChanged=mock.Mock())
        calls = []
        old, new = mock.Mock(), mock.Mock()
        old.stop.side_effect = lambda: calls.append('stop old')
        new.start.side_effect = lambda: calls.append('start new')
        plugin.runtimeRegistry.register(1, old)
        with mock.patch.object(fixtures.plugin_module, 'create_phidget', return_value=new), \
                mock.patch.object(fixtures.plugin_module, 'initialize_signed_value'):
            plugin.deviceStartComm(device)
        self.assertEqual(calls, ['stop old', 'start new'])
        self.assertIs(plugin.runtimeRegistry.get(1), new)
