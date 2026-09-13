# -*- coding: utf-8 -*-

import pathlib
import sys
import types
import unittest


SERVER_PLUGIN = (pathlib.Path(__file__).parents[1] /
                 "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin")
sys.path.insert(0, str(SERVER_PLUGIN))

from runtime_registry import RuntimeDeviceRegistry, registry_for


class RuntimeDeviceRegistryTests(unittest.TestCase):
    def test_register_snapshot_remove_and_clear(self):
        registry = RuntimeDeviceRegistry()
        first = object()
        second = object()

        registry.register(1, first)
        registry.register(2, second)
        registry.register_network_server(first)

        self.assertIs(registry.get(1), first)
        self.assertEqual(set(registry.snapshot()), {first, second})
        self.assertIs(registry.remove(1), first)
        registry.clear()
        self.assertEqual(registry.snapshot(), [])
        self.assertEqual(registry.network_servers_snapshot(), [])

    def test_dependents_are_selected_by_provider_id(self):
        registry = RuntimeDeviceRegistry()
        dependent = types.SimpleNamespace(adapterDeviceId=10)
        unrelated = types.SimpleNamespace(adapterDeviceId=11)
        registry.register(1, dependent)
        registry.register(2, unrelated)

        self.assertEqual(registry.dependents_of(10), [dependent])

    def test_network_servers_have_separate_typed_snapshot(self):
        registry = RuntimeDeviceRegistry()
        monitor = object()
        registry.register_network_server(monitor)
        self.assertEqual(registry.network_servers_snapshot(), [monitor])
        registry.remove_network_server(monitor)
        self.assertEqual(registry.network_servers_snapshot(), [])

    def test_legacy_test_host_is_adapted_once(self):
        runtime_device = object()
        monitor = object()
        plugin = types.SimpleNamespace(
            activePhidgets={42: runtime_device},
            _networkServerDevices={monitor})

        registry = registry_for(plugin)

        self.assertIs(registry.get(42), runtime_device)
        self.assertEqual(registry.network_servers_snapshot(), [monitor])
        self.assertIs(registry_for(plugin), registry)


if __name__ == "__main__":
    unittest.main()
