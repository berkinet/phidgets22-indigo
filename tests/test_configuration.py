import pathlib
import logging
import sys
import types
import unittest
import xml.etree.ElementTree as ElementTree
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))


class FakePluginBase(object):
    def __del__(self):
        pass


fake_indigo = types.ModuleType("indigo")
fake_indigo.Dict = dict
fake_indigo.PluginBase = FakePluginBase
sys.modules.setdefault("indigo", fake_indigo)

import indigo
import plugin


class ConfigurationTests(unittest.TestCase):
    def test_plugin_version_matches_release(self):
        plist = (SERVER_PLUGIN.parent / "Info.plist").read_text()

        self.assertIn("<string>0.2.1.35</string>", plist)

    def test_device_menu_defaults_and_icon_labels(self):
        root = ElementTree.parse(SERVER_PLUGIN / "Devices.xml").getroot()
        fields = {field.get("id"): field for field in root.iter("Field")}

        self.assertEqual(fields["displayTempUnit"].get("defaultValue"), "C")
        self.assertEqual(fields["displayStateName"].get("defaultValue"), "frequency")
        sprinkler_labels = [option.text for option in root.iter("Option")
                            if option.get("value") == "SprinklerOn"]
        self.assertEqual(sprinkler_labels, ["sprinkler on", "sprinkler on"])

    def test_event_device_labels_are_spelled_correctly(self):
        root = ElementTree.parse(SERVER_PLUGIN / "Events.xml").getroot()
        labels = [label.text for label in root.iter("Label")]

        self.assertEqual(labels.count("Phidget Device"), 2)
        self.assertNotIn("Phdget Device", labels)

    def test_lcd_device_and_actions_are_declared(self):
        devices = ElementTree.parse(SERVER_PLUGIN / "Devices.xml").getroot()
        lcd_device = devices.find("./Device[@id='lcd']")
        self.assertIsNotNone(lcd_device)
        lcd_fields = {field.get("id") for field in lcd_device.iter("Field")}
        self.assertTrue({"lcdScreenSize", "lcdBacklight",
                         "lcdContrast", "lcdRestoreInitialText"}.issubset(lcd_fields))

        actions = ElementTree.parse(SERVER_PLUGIN / "Actions.xml").getroot()
        action_ids = {action.get("id") for action in actions.findall("Action")}
        self.assertEqual(action_ids, {"lcdWriteText", "lcdWriteLines", "lcdClear", "lcdSetBacklight",
                                      "lcdSetContrast", "lcdSleep", "lcdWake"})
        self.assertTrue(all(action.get("deviceFilter") == "self.lcd"
                            for action in actions.findall("Action")))

    def test_attach_timeout_accepts_positive_integer(self):
        instance = object.__new__(plugin.Plugin)
        values = indigo.Dict({"attachTimeout": " 12 "})

        self.assertTrue(instance.validatePrefsConfigUi(values))
        self.assertEqual(values["attachTimeout"], "12")

    def test_attach_timeout_rejects_invalid_values(self):
        instance = object.__new__(plugin.Plugin)
        for value in ("", "1.5", "zero", "0", "-1"):
            values = indigo.Dict({"attachTimeout": value})

            valid, returned_values, errors = instance.validatePrefsConfigUi(values)

            self.assertFalse(valid)
            self.assertIs(returned_values, values)
            self.assertIn("attachTimeout", errors)

    def test_lcd_action_validation(self):
        instance = object.__new__(plugin.Plugin)

        valid, values = instance.validateActionConfigUi(
            indigo.Dict({"x": " 3 ", "y": "4"}), "lcdWriteText", 1)
        self.assertTrue(valid)
        self.assertEqual(values, {"x": "3", "y": "4"})

        valid, values = instance.validateActionConfigUi(
            indigo.Dict({"lineCount": " 2 "}), "lcdWriteLines", 1)
        self.assertTrue(valid)
        self.assertEqual(values, {"lineCount": "2"})

        for action_type, field, value in (
                ("lcdWriteText", "x", "-1"),
                ("lcdWriteLines", "lineCount", "5"),
                ("lcdSetBacklight", "backlight", "1.1"),
                ("lcdSetContrast", "contrast", "dark")):
            values = indigo.Dict({field: value})
            valid, returned_values, errors = instance.validateActionConfigUi(
                values, action_type, 1)
            self.assertFalse(valid)
            self.assertIs(returned_values, values)
            self.assertIn(field, errors)

    def test_lcd_factory_and_action_dispatch(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginPrefs = {
            "networkPhidgets": True,
            "enableServerDiscovery": True,
        }
        instance.logger = logging.getLogger("test.configuration.lcd")
        instance.activePhidgets = {}

        device = mock.Mock()
        device.id = 91
        device.name = "Hall LCD"
        device.deviceTypeId = "lcd"
        device.pluginProps = {
            "serialNumber": "123456",
            "channel": "0",
            "isVintHub": True,
            "isVintDevice": True,
            "hubPort": "2",
            "lcdScreenSize": "1",
            "lcdBacklight": "0.8",
            "lcdContrast": "0.4",
            "lcdRestoreInitialText": False,
            "lcdInitialText": "Ready",
            "lcdInitialLine1": "",
            "lcdInitialLine2": "",
            "lcdInitialX": "0",
            "lcdInitialY": "0",
        }
        wrapper = mock.Mock()
        with mock.patch.object(plugin, "LCDPhidget", return_value=wrapper) as factory:
            instance.deviceStartComm(device)

        wrapper.start.assert_called_once_with()
        self.assertIs(instance.activePhidgets[device.id], wrapper)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.kwargs["screenSize"], 1)
        self.assertEqual(factory.call_args.kwargs["backlight"], 0.8)

        active_lcd = object.__new__(plugin.LCDPhidget)
        active_lcd.writeText = mock.Mock()
        active_lcd.writeLines = mock.Mock()
        active_lcd.clear = mock.Mock()
        active_lcd.setBacklight = mock.Mock()
        active_lcd.setContrast = mock.Mock()
        active_lcd.setSleeping = mock.Mock()
        instance.activePhidgets[device.id] = active_lcd
        instance.substitute = lambda value: value.replace("%%name%%", "Kitchen")

        instance.lcdWriteText(
            types.SimpleNamespace(props={"text": "%%name%%", "x": "2", "y": "3"}),
            device)
        instance.lcdWriteLines(
            types.SimpleNamespace(props={
                "lineCount": "2", "line1": "%%name%%", "line2": "Ready"}),
            device)
        instance.lcdClear(types.SimpleNamespace(props={}), device)
        instance.lcdSetBacklight(
            types.SimpleNamespace(props={"backlight": "0.6"}), device)
        instance.lcdSetContrast(
            types.SimpleNamespace(props={"contrast": "0.3"}), device)
        instance.lcdSleep(types.SimpleNamespace(props={}), device)
        instance.lcdWake(types.SimpleNamespace(props={}), device)

        active_lcd.writeText.assert_called_once_with("Kitchen", 2, 3)
        active_lcd.writeLines.assert_called_once_with(["Kitchen", "Ready"])
        active_lcd.clear.assert_called_once_with()
        active_lcd.setBacklight.assert_called_once_with(0.6)
        active_lcd.setContrast.assert_called_once_with(0.3)
        self.assertEqual(active_lcd.setSleeping.call_args_list,
                         [mock.call(True), mock.call(False)])


if __name__ == "__main__":
    unittest.main()
