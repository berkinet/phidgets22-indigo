# -*- coding: utf-8 -*-

"""Thread-safe ownership of active runtime devices and server monitors."""

import threading


class RuntimeDeviceRegistry(object):
    def __init__(self):
        self._lock = threading.RLock()
        self._devices = {}
        self._network_servers = {}

    def get(self, device_id):
        with self._lock:
            return self._devices.get(device_id)

    def register(self, device_id, runtime_device):
        with self._lock:
            self._devices[device_id] = runtime_device

    def remove(self, device_id):
        with self._lock:
            return self._devices.pop(device_id, None)

    def snapshot(self):
        with self._lock:
            return list(self._devices.values())

    def items_snapshot(self):
        with self._lock:
            return list(self._devices.items())

    def dependents_of(self, provider_id):
        return [device for device in self.snapshot()
                if getattr(device, "adapterDeviceId", None) == provider_id]

    def clear(self):
        with self._lock:
            self._devices.clear()
            self._network_servers.clear()

    def register_network_server(self, monitor):
        with self._lock:
            self._network_servers[id(monitor)] = monitor

    def remove_network_server(self, monitor):
        with self._lock:
            self._network_servers.pop(id(monitor), None)

    def network_servers_snapshot(self):
        with self._lock:
            return list(self._network_servers.values())


def registry_for(plugin):
    """Return the registry, lazily adapting lightweight test/plugin hosts."""
    registry = getattr(plugin, "runtimeRegistry", None)
    if registry is not None:
        return registry
    registry = RuntimeDeviceRegistry()
    for device_id, runtime_device in getattr(
            plugin, "activePhidgets", {}).items():
        registry.register(device_id, runtime_device)
    for monitor in getattr(plugin, "_networkServerDevices", set()):
        registry.register_network_server(monitor)
    plugin.runtimeRegistry = registry
    return registry
