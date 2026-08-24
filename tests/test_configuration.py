import pathlib
import sys
import types
import unittest
import xml.etree.ElementTree as ElementTree


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

        self.assertIn("<string>0.2.1.34</string>", plist)

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


if __name__ == "__main__":
    unittest.main()
