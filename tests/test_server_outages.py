import importlib.util
import pathlib
import sys
import threading
import time
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))

indigo = types.ModuleType("indigo")


class FakePluginBase(object):
    def __del__(self):
        pass


indigo.PluginBase = FakePluginBase
indigo.Dict = dict
indigo.List = list
sys.modules.setdefault("indigo", indigo)

SPEC = importlib.util.spec_from_file_location("plugin_under_test", SERVER_PLUGIN / "plugin.py")
plugin_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin_module)


class FakePhidget(object):
    def __init__(self, device_id, serial, state="detached"):
        self.indigoDevice = types.SimpleNamespace(id=device_id)
        self.channelInfo = types.SimpleNamespace(
            serialNumber=serial,
            netInfo=types.SimpleNamespace(isRemote=True),
        )
        self._state = state
        self._detach_announced = state == "detached"
        self._detached_at = time.monotonic() - 3

    def serverKey(self):
        return "Test-Server-B._phidget22server._tcp.local"

    def serverDisplayName(self):
        return "Test-Server-B"

    def _identity(self):
        return "device=%s" % self.indigoDevice.id


class ServerOutageTests(unittest.TestCase):
    def setUp(self):
        self.plugin = plugin_module.Plugin.__new__(plugin_module.Plugin)
        self.plugin.activePhidgets = {
            1: FakePhidget(1, 100),
            2: FakePhidget(2, 200),
        }
        self.plugin.logger = mock.Mock()
        self.plugin._outageLock = threading.RLock()
        self.plugin._detachBatches = {}
        self.plugin._recoveryBatches = {}
        self.plugin._batchTimers = {}
        self.plugin._serverOutages = {}
        self.server_key = "Test-Server-B._phidget22server._tcp.local"

    def test_all_channels_detached_produces_one_server_warning_and_recovery(self):
        channels = set(self.plugin.activePhidgets.values())
        self.plugin._detachBatches[self.server_key] = channels

        self.plugin._flushDetachBatch(self.server_key)

        self.plugin.logger.warning.assert_called_once()
        warning = self.plugin.logger.warning.call_args.args[0]
        self.assertIn("server '%s' disconnected", warning)
        self.assertIn(self.server_key, self.plugin._serverOutages)

        for phidget in channels:
            phidget._state = "attached"
            phidget._detach_announced = False
        self.plugin._recoveryBatches[self.server_key] = {
            phidget: 73.0 for phidget in channels
        }

        self.plugin._flushRecoveryBatch(self.server_key)

        self.plugin.logger.info.assert_called_once()
        self.assertNotIn(self.server_key, self.plugin._serverOutages)

    def test_partial_detach_keeps_channel_level_warning(self):
        attached = self.plugin.activePhidgets[2]
        attached._state = "attached"
        attached._detach_announced = False
        detached = self.plugin.activePhidgets[1]
        self.plugin._detachBatches[self.server_key] = {detached}

        self.plugin._flushDetachBatch(self.server_key)

        self.plugin.logger.warning.assert_called_once()
        self.assertIn("Phidget remains detached", self.plugin.logger.warning.call_args.args[0])
        self.assertNotIn(self.server_key, self.plugin._serverOutages)


if __name__ == "__main__":
    unittest.main()
