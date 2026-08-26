import pathlib
import sys
import types
import unittest


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))

import indigo
import display_providers
import lcd


class AdapterWrapper(object):
    @staticmethod
    def supportsFunction(function_id):
        return function_id == "lcd"


class FakeInventory(object):
    def compatible_channels(self, device_type):
        if device_type != "lcd":
            return []
        return [{
            "serverName": "Workshop", "serverUniqueName": None,
            "serialNumber": 123, "hubPort": None,
            "isHubPortDevice": False, "channel": 0,
            "channelClass": 11, "deviceClass": 13,
            "deviceSKU": "LCD1100", "deviceName": "Graphic LCD Phidget",
            "deviceLabel": "Native screen",
        }]


class DisplayProviderTests(unittest.TestCase):
    def setUp(self):
        self.adapter_device = types.SimpleNamespace(
            id=42, name="Kitchen display bus", enabled=True,
            pluginId="test.plugin", deviceTypeId="dataAdapter", states={})
        self.unrelated = types.SimpleNamespace(
            id=43, name="Input", enabled=True, pluginId="test.plugin",
            deviceTypeId="digitalInput", states={})
        indigo.devices = [self.adapter_device, self.unrelated]
        self.plugin = types.SimpleNamespace(
            pluginId="test.plugin", discoveryInventory=FakeInventory(),
            activePhidgets={42: AdapterWrapper()})

    def test_native_and_adapter_providers_share_one_inventory(self):
        providers = display_providers.available_display_providers(self.plugin)

        self.assertEqual([provider["kind"] for provider in providers],
                         ["adapter", "native"])
        self.assertEqual(providers[0]["name"], "Kitchen display bus")
        self.assertEqual(providers[0]["adapterDeviceId"], 42)
        self.assertEqual(providers[1]["name"], "Native screen — Workshop")

    def test_lcd_contract_resolves_shared_provider_without_opening_it(self):
        resolved = lcd.LCDPhidget.resolveAdapterProvider(self.plugin, "42")

        self.assertIs(resolved, self.plugin.activePhidgets[42])
        with self.assertRaisesRegex(RuntimeError, "not active"):
            lcd.LCDPhidget.resolveAdapterProvider(self.plugin, 99)


if __name__ == "__main__":
    unittest.main()
