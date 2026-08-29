import pathlib
import sys
import time
import types
import unittest


SERVER_PLUGIN = (pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" /
                 "Contents" / "Server Plugin")
sys.path.insert(0, str(SERVER_PLUGIN))

import config_util
import i2c_resources


class ConfigUtilityTests(unittest.TestCase):
    def test_saved_bool_handles_indigo_string_values(self):
        for value in (True, 1, "1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                self.assertTrue(config_util.saved_bool(value))
        for value in (False, 0, "0", "false", "no", "off", ""):
            with self.subTest(value=value):
                self.assertFalse(config_util.saved_bool(value))

    def test_bounded_float_rejects_non_finite_values(self):
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    config_util.bounded_float(value)

    def test_hardware_probe_timeout_is_bounded(self):
        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, "hardware probe timed out"):
            config_util.call_with_timeout(lambda: time.sleep(0.2), 0.01)
        self.assertLess(time.monotonic() - started, 0.1)

    def test_i2c_owner_includes_disabled_devices(self):
        device = types.SimpleNamespace(
            id=7, pluginId="plugin", deviceTypeId="sgp41", enabled=False,
            pluginProps={"sgpAdapterDeviceId": "42"}, name="Air sensor")
        self.assertIs(
            i2c_resources.find_address_owner([device], "plugin", "42", 0x59),
            device)

    def test_native_owner_matches_only_the_same_channel_class(self):
        props = {
            "serverName": "server", "serialNumber": "123", "hubPort": "1",
            "channel": "0", "isVintHub": "true", "isVintDevice": "true",
        }
        existing = types.SimpleNamespace(
            id=7, pluginId="plugin", deviceTypeId="digitalInput",
            pluginProps=dict(props), name="Input")
        self.assertIs(i2c_resources.find_native_channel_owner(
            [existing], "plugin", props, "digitalInput"), existing)
        self.assertIsNone(i2c_resources.find_native_channel_owner(
            [existing], "plugin", props, "voltageInput"))


if __name__ == "__main__":
    unittest.main()
