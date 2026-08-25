import pathlib
import logging
import sys
import types
import unittest
import xml.etree.ElementTree as ElementTree
from contextlib import ExitStack
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))


class FakePluginBase(object):
    def __del__(self):
        pass


class IndigoLikeDict(dict):
    """Indigo's Dict supports mapping operations but not dict.setdefault."""

    def __getattribute__(self, name):
        if name == "setdefault":
            raise AttributeError(name)
        return super(IndigoLikeDict, self).__getattribute__(name)


fake_indigo = types.ModuleType("indigo")
fake_indigo.Dict = dict
fake_indigo.PluginBase = FakePluginBase
sys.modules.setdefault("indigo", fake_indigo)

import indigo
import actions
import device_factory
import discovery_ui
import plugin


class ConfigurationTests(unittest.TestCase):
    def test_plugin_version_matches_release(self):
        plist = (SERVER_PLUGIN.parent / "Info.plist").read_text()

        self.assertIn("<string>0.3.0</string>", plist)
        self.assertIn("<string>com.yikes.eric.phidgets-indigo</string>", plist)

    def test_plugin_responsibilities_are_supplied_by_focused_modules(self):
        self.assertIs(plugin.Plugin.lcdSetDisplay, actions.ActionsMixin.lcdSetDisplay)
        self.assertIs(plugin.Plugin.validateDeviceConfigUi,
                      discovery_ui.DiscoveryUiMixin.validateDeviceConfigUi)
        self.assertNotIn("lcdSetDisplay", plugin.Plugin.__dict__)
        self.assertNotIn("validateDeviceConfigUi", plugin.Plugin.__dict__)
        self.assertEqual(set(device_factory._BUILDERS), {
            "voltageInput", "voltageRatioInput", "digitalOutput", "digitalInput",
            "temperatureSensor", "frequencyCounter", "humiditySensor", "lcd",
        })

    def test_factory_constructs_every_supported_wrapper(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginPrefs = {
            "networkPhidgets": True,
            "enableServerDiscovery": True,
        }
        instance.logger = logging.getLogger("test.configuration.factory")
        constructors = {
            "voltageInput": "VoltageInputPhidget",
            "voltageRatioInput": "VoltageRatioInputPhidget",
            "digitalOutput": "DigitalOutputPhidget",
            "digitalInput": "DigitalInputPhidget",
            "temperatureSensor": "TemperatureSensorPhidget",
            "frequencyCounter": "FrequencyCounterPhidget",
            "humiditySensor": "HumiditySensorPhidget",
            "lcd": "LCDPhidget",
        }
        props = {
            "serialNumber": "123456", "channel": "2",
            "isVintHub": True, "isVintDevice": True, "hubPort": "1",
        }

        with ExitStack() as stack:
            mocks = {
                device_type: stack.enter_context(mock.patch.object(
                    device_factory, class_name,
                    return_value=mock.sentinel.wrapper))
                for device_type, class_name in constructors.items()
            }
            for device_type in constructors:
                with self.subTest(device_type=device_type):
                    device = types.SimpleNamespace(
                        deviceTypeId=device_type, pluginProps=dict(props))
                    self.assertIs(
                        device_factory.create_phidget(instance, device),
                        mock.sentinel.wrapper)
                    channel_info = mocks[device_type].call_args.kwargs["channelInfo"]
                    self.assertEqual(channel_info.serialNumber, 123456)
                    self.assertEqual(channel_info.channel, 2)
                    self.assertEqual(channel_info.hubPort, 1)
                    self.assertTrue(channel_info.netInfo.isRemote)
                    self.assertTrue(channel_info.netInfo.serverDiscovery)

        with self.assertRaisesRegex(ValueError, "Unexpected device type"):
            device_factory.create_phidget(
                instance,
                types.SimpleNamespace(
                    deviceTypeId="unknown", pluginProps=dict(props)))

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
        self.assertEqual(action_ids, {"lcdClear", "lcdStartAnimation",
                                      "lcdStopAnimation", "lcdSleep", "lcdWake"})
        self.assertTrue(all(action.get("deviceFilter") == "self.lcd"
                            for action in actions.findall("Action")))
        display_action = actions.find("./Action[@id='lcdStartAnimation']")
        fields = {field.get("id"): field for field in display_action.iter("Field")}
        self.assertIn("static2", fields["animationLine1"].get("visibleBindingValue"))
        self.assertIn("static2", fields["animationLine2"].get("visibleBindingValue"))
        self.assertIn(
            "virtualMarquee2", fields["virtualText"].get("visibleBindingValue"))
        for field_name in ("animationLine1", "animationLine2", "animationLine3",
                           "animationLine4", "alternateLine1", "alternateLine2",
                           "alternateLine3", "alternateLine4"):
            self.assertNotIn(
                "virtualMarquee", fields[field_name].get("visibleBindingValue"))

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
            indigo.Dict({
                "lineCount": "0", "animationMode": "static",
                "graphicX": " 3 ", "graphicY": "4",
                "backlight": "0.8", "contrast": "0.4",
            }), "lcdStartAnimation", 1)
        self.assertTrue(valid)
        self.assertEqual(values["graphicX"], "3")
        self.assertEqual(values["graphicY"], "4")

        for field, value in (("graphicX", "-1"), ("backlight", "1.1"),
                             ("contrast", "dark")):
            values = indigo.Dict({
                "lineCount": "0", "animationMode": "static",
                "graphicX": "0", "graphicY": "0",
                "backlight": "0.8", "contrast": "0.4",
            })
            values[field] = value
            valid, returned_values, errors = instance.validateActionConfigUi(
                values, "lcdStartAnimation", 1)
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
        with mock.patch.object(
                device_factory, "LCDPhidget", return_value=wrapper) as factory:
            instance.deviceStartComm(device)

        wrapper.start.assert_called_once_with()
        self.assertIs(instance.activePhidgets[device.id], wrapper)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.kwargs["screenSize"], 1)
        self.assertEqual(factory.call_args.kwargs["backlight"], 0.8)

        active_lcd = object.__new__(actions.LCDPhidget)
        active_lcd.writeText = mock.Mock()
        active_lcd.writeLines = mock.Mock()
        active_lcd.clear = mock.Mock()
        active_lcd.setBacklight = mock.Mock()
        active_lcd.setContrast = mock.Mock()
        active_lcd.setSleeping = mock.Mock()
        active_lcd.startAnimation = mock.Mock()
        active_lcd.stopAnimation = mock.Mock()
        instance.activePhidgets[device.id] = active_lcd
        substitutions = {
            "%%name%%": "Kitchen",
            "%%v:12345%%": "21.4",
            "%%d:67890:temperature%%": "19.8",
        }
        instance.substitute = lambda value: substitutions.get(value, value)

        instance.lcdSetDisplay(
            types.SimpleNamespace(props={
                "lineCount": "0", "animationMode": "static",
                "graphicText": "%%name%%", "graphicX": "2", "graphicY": "3",
                "backlight": "0.6", "contrast": "0.3"}),
            device)
        instance.lcdSetDisplay(
            types.SimpleNamespace(props={
                "lineCount": "2", "animationMode": "static",
                "animationLine1": "%%name%%", "animationLine2": "Ready",
                "backlight": "0.7", "contrast": "0.4"}),
            device)
        instance.lcdClear(types.SimpleNamespace(props={}), device)
        instance.lcdSleep(types.SimpleNamespace(props={}), device)
        instance.lcdWake(types.SimpleNamespace(props={}), device)
        instance.lcdSetDisplay(types.SimpleNamespace(props={
            "lineCount": "2", "animationMode": "marquee",
            "animationLine1": "%%v:12345%%", "animationLine2": "Open",
            "marqueeInterval": "0.5", "marqueeDirection": "right",
            "marqueeGap": "4", "backlight": "0.8", "contrast": "0.5",
        }), device)
        instance.lcdSetDisplay(types.SimpleNamespace(props={
            "lineCount": "2", "animationMode": "virtualMarquee",
            "virtualText": "%%d:67890:temperature%%",
            "marqueeInterval": "0.6", "marqueeDirection": "left",
            "marqueeGap": "5", "backlight": "0.9", "contrast": "0.6",
        }), device)
        instance.lcdStopAnimation(types.SimpleNamespace(props={}), device)

        active_lcd.writeText.assert_called_once_with("Kitchen", 2, 3)
        active_lcd.writeLines.assert_called_once_with(["Kitchen", "Ready"])
        active_lcd.clear.assert_called_once_with()
        self.assertEqual(active_lcd.setBacklight.call_args_list,
                         [mock.call(0.6), mock.call(0.7), mock.call(0.8),
                          mock.call(0.9)])
        self.assertEqual(active_lcd.setContrast.call_args_list,
                         [mock.call(0.3), mock.call(0.4), mock.call(0.5),
                          mock.call(0.6)])
        self.assertEqual(active_lcd.setSleeping.call_args_list,
                         [mock.call(False), mock.call(False),
                          mock.call(True), mock.call(False),
                          mock.call(False), mock.call(False)])
        self.assertEqual(active_lcd.startAnimation.call_args_list, [
            mock.call(
                mode="marquee", lines_a=["21.4", "Open"],
                lines_b=["", ""], interval=0.5, direction="right", gap=4),
            mock.call(
                mode="virtualMarquee", lines_a=["19.8"],
                lines_b=["", ""], interval=0.6, direction="left", gap=5),
        ])
        active_lcd.stopAnimation.assert_called_once_with()

    def test_lcd_action_resolves_target_from_action_when_device_is_none(self):
        instance = object.__new__(plugin.Plugin)
        active_lcd = object.__new__(actions.LCDPhidget)
        active_lcd.setSleeping = mock.Mock()
        instance.activePhidgets = {91: active_lcd}
        action = types.SimpleNamespace(deviceId=91, props={})

        instance.lcdSleep(action, None)

        active_lcd.setSleeping.assert_called_once_with(True)

    def test_static_substitution_overflow_can_start_marquee_or_reject(self):
        instance = object.__new__(plugin.Plugin)
        active_lcd = object.__new__(actions.LCDPhidget)
        active_lcd.screenWidth = 20
        active_lcd.setSleeping = mock.Mock()
        active_lcd.setBacklight = mock.Mock()
        active_lcd.setContrast = mock.Mock()
        active_lcd.writeLines = mock.Mock()
        active_lcd.startAnimation = mock.Mock()
        instance.activePhidgets = {42: active_lcd}
        instance.substitute = lambda value: (
            "This substituted value is longer than twenty characters"
            if value == "%%v:12345%%" else value)
        base_props = {
            "lineCount": "1", "animationMode": "static",
            "animationLine1": "%%v:12345%%",
            "backlight": "1.0", "contrast": "0.5",
        }

        marquee_props = dict(base_props, staticOverflowBehavior="marquee",
                              overflowMarqueeDirection="right",
                              overflowMarqueeGap="4",
                              overflowMarqueeInterval="0.6")
        instance.lcdSetDisplay(
            types.SimpleNamespace(deviceId=42, props=marquee_props), None)

        active_lcd.startAnimation.assert_called_once_with(
            mode="marquee",
            lines_a=["This substituted value is longer than twenty characters"],
            lines_b=[""], interval=0.6, direction="right", gap=4)
        active_lcd.writeLines.assert_not_called()

        reject_props = dict(base_props, staticOverflowBehavior="reject")
        with self.assertRaisesRegex(ValueError, "exceeds the 20-character"):
            instance.lcdSetDisplay(
                types.SimpleNamespace(deviceId=42, props=reject_props), None)

    def test_lcd_action_fields_follow_selected_device_height(self):
        instance = object.__new__(plugin.Plugin)
        device = types.SimpleNamespace(
            states={"lcdType": "text", "screenHeight": 2,
                    "backlight": 0.75, "contrast": 0.35},
            pluginProps={"lcdScreenSize": "7"})
        indigo.devices = {42: device}

        values, errors = instance.getActionConfigUiValues(
            IndigoLikeDict({}), "lcdStartAnimation", 42)

        self.assertEqual(values["lineCount"], "2")
        self.assertEqual(values["animationLayout"], "static2")
        self.assertEqual(values["backlight"], "0.75")
        self.assertEqual(values["contrast"], "0.35")
        self.assertEqual(errors, {})

        values, errors = instance.getActionConfigUiValues(
            indigo.Dict({"animationMode": "flash"}), "lcdStartAnimation", 42)
        self.assertEqual(values["animationLayout"], "flash2")
        self.assertEqual(values["lineCount"], "2")

        values["animationMode"] = "marquee"
        returned = instance.lcdAnimationConfigChanged(
            values, "lcdStartAnimation", 42)
        self.assertEqual(returned["animationLayout"], "marquee2")

        values["animationMode"] = "virtualMarquee"
        returned = instance.lcdAnimationConfigChanged(
            values, "lcdStartAnimation", 42)
        self.assertEqual(returned["animationLayout"], "virtualMarquee2")
        self.assertEqual(returned["virtualTextStatus"], "∅ empty")

        values["virtualText"] = "TEST-XYZ-123"
        returned = instance.lcdAnimationConfigChanged(
            values, "lcdStartAnimation", 42)
        self.assertEqual(returned["virtualTextStatus"],
                         "→ 12 characters stored")

        values["virtualText"] = "Visible\nHidden"
        returned = instance.lcdAnimationConfigChanged(
            values, "lcdStartAnimation", 42)
        self.assertEqual(returned["virtualTextStatus"],
                         "⚠ 14 characters stored across 2 lines")

        values["animationMode"] = "static"
        values["animationLine1"] = "Temperature: %%d:42:temperature%%"
        values["staticOverflowBehavior"] = "truncate"
        returned = instance.lcdAnimationConfigChanged(
            values, "lcdStartAnimation", 42)
        self.assertEqual(returned["staticOverflowLayout"], "show")

        values["staticOverflowBehavior"] = "marquee"
        returned = instance.lcdAnimationConfigChanged(
            values, "lcdStartAnimation", 42)
        self.assertEqual(returned["staticOverflowLayout"], "marquee")

        values["animationLine1"] = "Plain text"
        returned = instance.lcdAnimationConfigChanged(
            values, "lcdStartAnimation", 42)
        self.assertEqual(returned["staticOverflowLayout"], "hidden")

    def test_lcd_animation_validation(self):
        instance = object.__new__(plugin.Plugin)

        valid, values = instance.validateActionConfigUi(indigo.Dict({
            "lineCount": "2", "animationMode": "marquee",
            "marqueeInterval": "0.4", "marqueeGap": "3",
            "backlight": "1.0", "contrast": "0.5",
        }), "lcdStartAnimation", 42)
        self.assertTrue(valid)
        self.assertEqual(values["marqueeInterval"], "0.4")

        valid, values = instance.validateActionConfigUi(indigo.Dict({
            "lineCount": "2", "animationMode": "virtualMarquee",
            "marqueeInterval": "0.5", "marqueeGap": "4",
            "backlight": "1.0", "contrast": "0.5",
        }), "lcdStartAnimation", 42)
        self.assertTrue(valid)
        self.assertEqual(values["marqueeGap"], "4")

        valid, values, errors = instance.validateActionConfigUi(indigo.Dict({
            "lineCount": "2", "animationMode": "virtualMarquee",
            "virtualText": "First line\nHidden old text",
            "marqueeInterval": "0.5", "marqueeGap": "4",
            "backlight": "1.0", "contrast": "0.5",
        }), "lcdStartAnimation", 42)
        self.assertFalse(valid)
        self.assertIn("virtualText", errors)

        valid, values, errors = instance.validateActionConfigUi(indigo.Dict({
            "lineCount": "2", "animationMode": "marquee",
            "marqueeInterval": "0.01", "marqueeGap": "0",
            "backlight": "1.0", "contrast": "0.5",
        }), "lcdStartAnimation", 42)
        self.assertFalse(valid)
        self.assertIn("marqueeInterval", errors)
        self.assertIn("marqueeGap", errors)


if __name__ == "__main__":
    unittest.main()
