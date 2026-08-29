import pathlib
import inspect
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


class DeviceCollection(dict):
    def __iter__(self):
        return iter(self.values())


class IdentityDevice(object):
    """Device proxy whose equality, like Indigo's, is identity-based."""

    def __init__(self, **attributes):
        self.__dict__.update(attributes)


class RehydratingDeviceCollection(DeviceCollection):
    """Return a fresh proxy for indexed access while iterating stored proxies."""

    def __getitem__(self, key):
        stored = super(RehydratingDeviceCollection, self).__getitem__(key)
        return IdentityDevice(**stored.__dict__)


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
    def test_device_validation_uses_focused_dispatch_handlers(self):
        coordinator = inspect.getsource(
            discovery_ui.DiscoveryUiMixin.validateDeviceConfigUi)
        self.assertLessEqual(len(coordinator.splitlines()), 16)
        for name in (
                "_validateSGP41Config", "_validateBME280Config",
                "_validateAdapterGPIOConfig", "_validateLCDConfig",
                "_validateLCDSettings", "_validateDataAdapterConfig",
                "_validateDataAdapterSettings", "_validateChannelConfig"):
            self.assertTrue(hasattr(discovery_ui.DiscoveryUiMixin, name), name)

    def test_custom_sensor_formula_is_validated_before_save(self):
        instance = object.__new__(plugin.Plugin)
        values = indigo.Dict({
            "dataInterval": "1000", "decimalPlaces": "2",
            "voltageSensorType": "0", "voltageChangeTrigger": "0",
            "sensorValueChangeTrigger": "0", "useCustomFormula": True,
            "customState": "converted",
            "customFormula": "__import__('os').system('id')",
        })

        errors = instance._validateNativeSettings(values, "voltageInput")

        self.assertIn("customFormula", errors)
        self.assertIn("unsupported operation", errors["customFormula"])

        values["customFormula"] = "'Low' if x < 2.5 else 'High'"
        values["customOutputType"] = "text"
        errors = instance._validateNativeSettings(values, "voltageInput")
        self.assertNotIn("customFormula", errors)

    def test_custom_formula_language_is_documented_in_device_dialogs(self):
        devices = ElementTree.parse(SERVER_PLUGIN / "Devices.xml").getroot()
        help_labels = [field.find("Label").text for field in devices.iter("Field")
                       if field.get("id") == "customFormulaHelp"]

        self.assertEqual(len(help_labels), 2)
        output_fields = [field for field in devices.iter("Field")
                         if field.get("id") == "customOutputType"]
        self.assertEqual(len(output_fields), 2)
        for field in output_fields:
            self.assertEqual(field.get("visibleBindingId"), "useCustomFormula")
            self.assertEqual(
                [(option.get("value"), option.text)
                 for option in field.iter("Option")],
                [("number", "Number"), ("text", "Text"),
                 ("boolean", "On/Off")])
        for label in help_labels:
            self.assertIn("Allowed: x, numbers", label)
            self.assertIn("and/or/not", label)
            self.assertIn("round, clamp", label)

    def test_plugin_version_matches_release(self):
        plist = (SERVER_PLUGIN.parent / "Info.plist").read_text()

        self.assertIn("<string>0.3.32</string>", plist)
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
            "dataAdapter", "adapterGPIOInput", "adapterGPIOOutput", "bme280",
            "sgp41",
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
            "lcd": "NativeLCDPhidget",
            "dataAdapter": "DataAdapterPhidget",
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

    def test_missing_model_discovery_reveals_model_specific_notice(self):
        instance = object.__new__(plugin.Plugin)
        inventory = mock.Mock()
        inventory.resolve_channel.return_value = None
        inventory.selection_for_saved_address.return_value = None
        inventory.server_choices.return_value = []
        inventory.compatible_channels.return_value = []
        instance.discoveryInventory = inventory
        instance.pluginId = "com.yikes.eric.phidgets-indigo"
        instance.activePhidgets = {}

        values, errors = instance.getDeviceConfigUiValues({}, "lcd", 0)

        self.assertFalse(values["compatibleModelFound"])
        self.assertEqual(errors, {})
        inventory.server_choices.assert_called_once_with("lcd")

    def test_adapter_gpio_factory_uses_selected_adapter_address(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginPrefs = {
            "networkPhidgets": True, "enableServerDiscovery": True}
        instance.logger = logging.getLogger("test.configuration.gpio")
        channel_info = device_factory.ChannelInfo(
            serialNumber=729035, hubPort=-1, isHubPortDevice=0, channel=0,
            netInfo=device_factory.NetInfo(
                isRemote=True, serverName="CM-Library Mac"))
        instance.activePhidgets = {
            42: types.SimpleNamespace(channelInfo=channel_info)}
        props = {
            "gpioAdapterDeviceId": "42", "gpioPin": "1",
            "gpioInputMode": "pullup", "gpioInverted": True,
            "gpioDebounceMilliseconds": "75",
        }
        device = types.SimpleNamespace(
            deviceTypeId="adapterGPIOInput", pluginProps=props)

        with mock.patch.object(
                device_factory, "AdapterGPIOInputPhidget",
                return_value=mock.sentinel.wrapper) as constructor:
            result = device_factory.create_phidget(instance, device)

        self.assertIs(result, mock.sentinel.wrapper)
        arguments = constructor.call_args.kwargs
        self.assertEqual(arguments["channelInfo"].serialNumber, 729035)
        self.assertEqual(arguments["channelInfo"].channel, 1)
        self.assertEqual(arguments["adapterDeviceId"], 42)
        self.assertEqual(arguments["inputMode"], "pullup")
        self.assertTrue(arguments["inverted"])
        self.assertEqual(arguments["debounceMilliseconds"], 75)

    def test_bme280_factory_uses_selected_adapter_and_address(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginPrefs = {
            "networkPhidgets": True, "enableServerDiscovery": True}
        instance.logger = logging.getLogger("test.configuration.bme280")
        device = types.SimpleNamespace(
            deviceTypeId="bme280",
            pluginProps={
                "bmeAdapterDeviceId": "42", "bmeI2CAddress": "0x76",
                "bmePollInterval": "2.5", "bmeDisplayState": "temperature",
                "decimalPlaces": "2",
            })

        with mock.patch.object(
                device_factory, "BME280Phidget",
                return_value=mock.sentinel.wrapper) as constructor:
            result = device_factory.create_phidget(instance, device)

        self.assertIs(result, mock.sentinel.wrapper)
        self.assertEqual(constructor.call_args.kwargs["adapterDeviceId"], 42)
        self.assertEqual(constructor.call_args.kwargs["i2cAddress"], 0x76)
        self.assertEqual(constructor.call_args.kwargs["pollInterval"], 2.5)
        self.assertEqual(constructor.call_args.kwargs["displayState"], "temperature")

    def test_sgp41_factory_uses_adapter_and_compensation_values(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginPrefs = {"networkPhidgets": True,
                                "enableServerDiscovery": True}
        instance.logger = logging.getLogger("test.configuration.sgp41")
        device = types.SimpleNamespace(
            deviceTypeId="sgp41", pluginProps={
                "sgpAdapterDeviceId": "42", "sgpRelativeHumidity": "55.5",
                "sgpTemperature": "22.25", "sgpDisplayState": "rawNox"})
        with mock.patch.object(
                device_factory, "SGP41Phidget",
                return_value=mock.sentinel.wrapper) as constructor:
            result = device_factory.create_phidget(instance, device)
        self.assertIs(result, mock.sentinel.wrapper)
        self.assertEqual(constructor.call_args.kwargs["adapterDeviceId"], 42)
        self.assertEqual(constructor.call_args.kwargs["relativeHumidity"], 55.5)
        self.assertEqual(constructor.call_args.kwargs["temperature"], 22.25)
        self.assertEqual(constructor.call_args.kwargs["displayState"], "rawNox")

    def test_custom_formula_output_type_reaches_sensor_wrapper(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginPrefs = {
            "networkPhidgets": True, "enableServerDiscovery": True}
        instance.logger = logging.getLogger("test.configuration.formula-output")
        device = types.SimpleNamespace(
            deviceTypeId="voltageInput", pluginProps={
                "serialNumber": "123", "channel": "0", "isVintHub": False,
                "isVintDevice": False, "useCustomFormula": True,
                "customState": "status", "customFormula": "'On'",
                "customOutputType": "text", "voltageSensorType": "0",
                "voltageChangeTrigger": "0", "sensorValueChangeTrigger": "0",
                "decimalPlaces": "2"})

        with mock.patch.object(
                device_factory, "VoltageInputPhidget",
                return_value=mock.sentinel.wrapper) as constructor:
            result = device_factory.create_phidget(instance, device)

        self.assertIs(result, mock.sentinel.wrapper)
        self.assertEqual(constructor.call_args.kwargs["customOutputType"], "text")

    def test_data_adapter_device_is_declared(self):
        devices = ElementTree.parse(SERVER_PLUGIN / "Devices.xml").getroot()
        adapter = devices.find("./Device[@id='dataAdapter']")

        self.assertIsNotNone(adapter)
        fields = {field.get("id") for field in adapter.iter("Field")}
        self.assertTrue({"dataAdapterVoltage", "dataAdapterFrequency",
                         "compatibleModelFound", "missingModelNotice"} <= fields)
        notice = adapter.find(".//Field[@id='missingModelNotice']/Label")
        self.assertIn("No I2C Data Adapter device", notice.text)
        self.assertNotIn("manually", notice.text)

    def test_adapter_gpio_devices_are_declared(self):
        devices = ElementTree.parse(SERVER_PLUGIN / "Devices.xml").getroot()
        environmental = devices.find("./Device[@id='bme280']")
        gpio_input = devices.find("./Device[@id='adapterGPIOInput']")
        gpio_output = devices.find("./Device[@id='adapterGPIOOutput']")

        self.assertIsNotNone(environmental)
        environmental_fields = {
            field.get("id") for field in environmental.iter("Field")}
        self.assertTrue({"bmeAdapterSelection", "bmeI2CAddress",
                         "bmePollInterval", "bmeDisplayState"} <=
                        environmental_fields)
        gas_sensor = devices.find("./Device[@id='sgp41']")
        self.assertIsNotNone(gas_sensor)
        gas_fields = {field.get("id") for field in gas_sensor.iter("Field")}
        self.assertTrue({"sgpAdapterSelection", "sgpRelativeHumidity",
                         "sgpTemperature", "sgpDisplayState"} <= gas_fields)
        self.assertIsNotNone(gpio_input)
        self.assertIsNotNone(gpio_output)
        self.assertEqual(gpio_output.get("type"), "relay")
        input_fields = {field.get("id") for field in gpio_input.iter("Field")}
        self.assertTrue({"gpioAdapterSelection", "gpioPin", "gpioInputMode",
                         "gpioInverted", "gpioDebounceMilliseconds"} <=
                        input_fields)

    def test_adapter_gpio_validation_rejects_duplicate_pin(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginId = "com.yikes.eric.phidgets-indigo"
        adapter = types.SimpleNamespace(
            id=42, name="I2C Adapter 1", pluginId=instance.pluginId,
            deviceTypeId="dataAdapter", enabled=True, pluginProps={})
        existing = types.SimpleNamespace(
            id=43, name="Existing GPIO", pluginId=instance.pluginId,
            deviceTypeId="adapterGPIOOutput", enabled=True,
            pluginProps={"gpioAdapterDeviceId": "42", "gpioPin": "1"})
        devices = DeviceCollection({42: adapter, 43: existing})
        values = indigo.Dict({
            "gpioAdapterSelection": "42", "gpioPin": "1",
            "gpioInputMode": "pullup", "gpioInverted": False,
            "gpioDebounceMilliseconds": "50",
        })

        with mock.patch.object(indigo, "devices", devices, create=True):
            valid, returned, errors = instance.validateDeviceConfigUi(
                values, "adapterGPIOInput", 0)

        self.assertFalse(valid)
        self.assertIs(returned, values)
        self.assertIn("already assigned", errors["gpioPin"])

    def test_adapter_gpio_validation_accepts_rehydrated_device_proxy(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginId = "com.yikes.eric.phidgets-indigo"
        adapter = IdentityDevice(
            id=42, name="I2C Adapter 1", pluginId=instance.pluginId,
            deviceTypeId="dataAdapter", enabled=True, pluginProps={})
        devices = RehydratingDeviceCollection({42: adapter})
        values = indigo.Dict({
            "gpioAdapterSelection": "42", "gpioPin": "0",
            "gpioInputMode": "pullup", "gpioInverted": True,
            "gpioDebounceMilliseconds": "50",
        })

        with mock.patch.object(indigo, "devices", devices, create=True):
            valid, returned = instance.validateDeviceConfigUi(
                values, "adapterGPIOInput", 0)

        self.assertTrue(valid)
        self.assertIs(returned, values)
        self.assertEqual(values["gpioAdapterDeviceId"], "42")
        self.assertEqual(values["observedConnection"], "I2C Adapter 1→GPIO 0")
        self.assertEqual(values["address"], "gpio-42-0")

    def test_bme280_validation_probes_chip_identity(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginId = "com.yikes.eric.phidgets-indigo"
        adapter_device = IdentityDevice(
            id=42, name="I2C Adapter 1", pluginId=instance.pluginId,
            deviceTypeId="dataAdapter", enabled=True, pluginProps={})
        devices = DeviceCollection({42: adapter_device})
        adapter = mock.Mock()
        adapter.i2cSendReceive.return_value = b"\x60"
        instance.activePhidgets = {42: adapter}
        values = indigo.Dict({
            "bmeAdapterSelection": "42", "bmeI2CAddress": "0x76",
            "bmePollInterval": "2.0", "bmeDisplayState": "humidity",
            "decimalPlaces": "2",
        })

        with mock.patch.object(indigo, "devices", devices, create=True):
            valid, returned = instance.validateDeviceConfigUi(
                values, "bme280", 0)

        self.assertTrue(valid)
        self.assertIs(returned, values)
        adapter.i2cSendReceive.assert_called_once_with(0x76, b"\xD0", 1)
        self.assertEqual(values["address"], "bme280-42-76")

    def test_bmp280_rejects_humidity_display_state(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginId = "com.yikes.eric.phidgets-indigo"
        adapter_device = IdentityDevice(
            id=42, name="I2C Adapter 1", pluginId=instance.pluginId,
            deviceTypeId="dataAdapter", enabled=True, pluginProps={})
        devices = DeviceCollection({42: adapter_device})
        adapter = mock.Mock()
        adapter.i2cSendReceive.return_value = b"\x58"
        instance.activePhidgets = {42: adapter}
        values = indigo.Dict({
            "bmeAdapterSelection": "42", "bmeI2CAddress": "0x76",
            "bmePollInterval": "2", "bmeDisplayState": "humidity",
            "decimalPlaces": "2"})
        with mock.patch.object(indigo, "devices", devices, create=True):
            valid, _, errors = instance.validateDeviceConfigUi(
                values, "bme280", 0)
        self.assertFalse(valid)
        self.assertIn("does not provide", errors["bmeDisplayState"])

    def test_sgp41_validation_probes_serial_number(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginId = "com.yikes.eric.phidgets-indigo"
        adapter_device = IdentityDevice(
            id=42, name="I2C Adapter 1", pluginId=instance.pluginId,
            deviceTypeId="dataAdapter", enabled=True, pluginProps={})
        devices = DeviceCollection({42: adapter_device})
        adapter = mock.Mock()
        adapter.i2cCommandResponse.return_value = (
            b"\x12\x34\x37\x56\x78\x7D\x9A\xBC\xE0")
        instance.activePhidgets = {42: adapter}
        values = indigo.Dict({
            "sgpAdapterSelection": "42", "sgpRelativeHumidity": "50",
            "sgpTemperature": "25", "sgpDisplayState": "rawNox"})
        with mock.patch.object(indigo, "devices", devices, create=True):
            valid, returned = instance.validateDeviceConfigUi(values, "sgp41", 0)
        self.assertTrue(valid)
        self.assertIs(returned, values)
        adapter.i2cCommandResponse.assert_called_once_with(
            0x59, b"\x36\x82", 0.001, 9)
        self.assertEqual(values["address"], "sgp41-42-59")

    def test_new_device_cannot_save_without_a_compatible_channel(self):
        instance = object.__new__(plugin.Plugin)
        inventory = mock.Mock()
        inventory.server_choices.return_value = []
        instance.discoveryInventory = inventory
        instance._observedConnectionForDevice = lambda device_id: "Not yet observed"
        values = indigo.Dict({"serialNumber": "", "channel": ""})

        valid, returned_values, errors = instance.validateDeviceConfigUi(
            values, "dataAdapter", 0)

        self.assertFalse(valid)
        self.assertIs(returned_values, values)
        self.assertIn("discoveredServer", errors)
        self.assertIn("before saving", errors["showAlertText"])

    def test_new_device_must_select_one_of_several_available_channels(self):
        instance = object.__new__(plugin.Plugin)
        inventory = mock.Mock()
        inventory.server_choices.return_value = [("server-token", "Server")]
        instance.discoveryInventory = inventory
        instance._observedConnectionForDevice = lambda device_id: "Not yet observed"
        values = indigo.Dict({"serialNumber": "", "channel": ""})

        valid, returned_values, errors = instance.validateDeviceConfigUi(
            values, "dataAdapter", 0)

        self.assertFalse(valid)
        self.assertIs(returned_values, values)
        self.assertIn("Select an available device", errors["showAlertText"])

    def test_configured_offline_device_retains_saved_address(self):
        instance = object.__new__(plugin.Plugin)
        indigo.variables = {}
        inventory = mock.Mock()
        inventory.server_choices.return_value = []
        instance.discoveryInventory = inventory
        instance._observedConnectionForDevice = lambda device_id: "Previously observed"
        values = indigo.Dict({
            "serialNumber": "123456", "channel": "0", "serverName": "",
            "isVintHub": False, "isVintDevice": False,
            "dataAdapterVoltage": "5", "dataAdapterFrequency": "2",
        })

        valid, returned_values = instance.validateDeviceConfigUi(
            values, "dataAdapter", 42)

        self.assertTrue(valid)
        self.assertEqual(returned_values["address"], "123456|p-0")

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
        self.assertEqual(fields["graphicFont"].get("defaultValue"), "4")
        self.assertEqual(fields["graphicContentType"].get("defaultValue"), "text")
        self.assertEqual(fields["formulaExpression"].get("defaultValue"), "sin(x)")
        self.assertEqual(fields["donutInterval"].get("defaultValue"), "0.15")
        self.assertEqual(fields["graphicFont"].get("visibleBindingId"),
                         "graphicContentLayout")
        self.assertEqual(fields["formulaExpression"].get("visibleBindingId"),
                         "graphicContentLayout")
        self.assertIn("graphic8", fields["graphicLine8"].get(
            "visibleBindingValue"))
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
                device_factory, "NativeLCDPhidget", return_value=wrapper) as factory:
            instance.deviceStartComm(device)

        wrapper.start.assert_called_once_with()
        self.assertIs(instance.activePhidgets[device.id], wrapper)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.kwargs["screenSize"], 1)
        self.assertEqual(factory.call_args.kwargs["backlight"], 0.8)

        active_lcd = object.__new__(actions.LCDPhidget)
        active_lcd.writeText = mock.Mock()
        active_lcd.writeLines = mock.Mock()
        active_lcd.writeGraphicLines = mock.Mock()
        active_lcd.plotFormula = mock.Mock()
        active_lcd.startDonut = mock.Mock()
        active_lcd.clear = mock.Mock()
        active_lcd.setBacklight = mock.Mock()
        active_lcd.setContrast = mock.Mock()
        active_lcd.setSleeping = mock.Mock()
        active_lcd.startAnimation = mock.Mock()
        active_lcd.turnOff = mock.Mock()
        active_lcd.runDisplayWhenAttached = mock.Mock(
            side_effect=lambda callback: callback())
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
                "lineCount": "0", "animationMode": "static",
                "graphicContentType": "formula",
                "formulaExpression": "sin(x)", "formulaXMin": "-3.14",
                "formulaXMax": "3.14", "formulaYMin": "-1.2",
                "formulaYMax": "1.2", "formulaShowAxes": True,
                "formulaStyle": "line", "backlight": "0.6",
                "contrast": "0.3"}),
            device)
        instance.lcdSetDisplay(
            types.SimpleNamespace(props={
                "lineCount": "0", "animationMode": "static",
                "graphicContentType": "donut", "donutInterval": "0.2",
                "backlight": "0.6", "contrast": "0.3"}),
            device)
        instance.lcdSetDisplay(
            types.SimpleNamespace(props={
                "lineCount": "0", "animationMode": "static",
                "graphicFont": "5", "graphicLine1": "Large",
                "graphicLine2": "Text", "backlight": "0.6",
                "contrast": "0.3"}),
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
        active_lcd.writeGraphicLines.assert_called_once_with(
            ["Large", "Text", "", "", "", "", "", ""], 5)
        active_lcd.plotFormula.assert_called_once_with(
            "sin(x)", "-3.14", "3.14", "-1.2", "1.2", True, "line")
        active_lcd.startDonut.assert_called_once_with(0.2)
        active_lcd.writeLines.assert_called_once_with(["Kitchen", "Ready"])
        active_lcd.turnOff.assert_called_once_with()
        active_lcd.clear.assert_called_once_with()
        self.assertEqual(active_lcd.setBacklight.call_args_list,
                         [mock.call(0.6), mock.call(0.6), mock.call(0.6),
                          mock.call(0.6),
                          mock.call(0.7), mock.call(0.8),
                          mock.call(0.9)])
        self.assertEqual(active_lcd.setContrast.call_args_list,
                         [mock.call(0.3), mock.call(0.3), mock.call(0.3),
                          mock.call(0.3),
                          mock.call(0.4), mock.call(0.5),
                          mock.call(0.6)])
        self.assertEqual(active_lcd.setSleeping.call_args_list,
                         [mock.call(False), mock.call(False), mock.call(False),
                          mock.call(False),
                          mock.call(False),
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
        active_lcd.turnOff.assert_called_once_with()

    def test_i2c_display_selection_populates_profile_and_factory(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginId = "com.yikes.eric.phidgets-indigo"
        instance.pluginPrefs = {"networkPhidgets": True,
                                "enableServerDiscovery": True}
        instance.logger = logging.getLogger("test.configuration.i2c-lcd")
        instance.discoveryInventory = mock.Mock()
        instance.discoveryInventory.compatible_channels.return_value = []
        adapter_wrapper = mock.Mock()
        adapter_wrapper.supportsFunction.side_effect = lambda value: value == "lcd"
        adapter_wrapper._state = "attached"
        adapter_wrapper.i2cAddressResponds.return_value = True
        instance.activePhidgets = {42: adapter_wrapper}
        adapter_device = types.SimpleNamespace(
            id=42, name="Library display bus", enabled=True,
            pluginId=instance.pluginId, deviceTypeId="dataAdapter", states={},
            pluginProps={"serialNumber": "729035", "channel": "0",
                         "serverName": "CM-Library Mac"})
        indigo.devices = DeviceCollection({42: adapter_device})
        values = indigo.Dict({"lcdDisplayProvider": "adapter:42"})

        returned = instance.displayProviderChanged(values, "lcd", 0)

        self.assertEqual(returned["lcdProviderKind"], "adapter")
        self.assertEqual(returned["lcdAdapterDeviceId"], "42")
        self.assertEqual(returned["lcdProfile"], "freenove-hd44780-pcf8574")
        self.assertEqual(returned["lcdScreenSize"], "8")
        self.assertEqual(returned["lcdI2CAddress"], "0x27")
        self.assertIn("I2C character LCD", returned["observedConnection"])

        returned.update({
            "lcdScreenSize": "5",
            "lcdBacklight": "1.0", "lcdContrast": "0.5",
            "lcdInitialX": "0", "lcdInitialY": "0",
            "isVintHub": False, "isVintDevice": False,
        })
        indigo.variables = {}
        valid, saved = instance.validateDeviceConfigUi(returned, "lcd", 0)
        self.assertTrue(valid)
        self.assertEqual(saved["address"], "lcd-i2c-42-27")

        device = types.SimpleNamespace(
            deviceTypeId="lcd", pluginProps=dict(returned,
                lcdBacklight="1.0", lcdContrast="0.5",
                lcdRestoreInitialText=False, lcdInitialText="",
                lcdInitialLine1="", lcdInitialLine2="",
                lcdInitialLine3="", lcdInitialLine4="",
                lcdInitialX="0", lcdInitialY="0"))
        with mock.patch.object(device_factory, "I2CLCDPhidget",
                               return_value=mock.sentinel.i2c_lcd) as constructor:
            result = device_factory.create_phidget(instance, device)

        self.assertIs(result, mock.sentinel.i2c_lcd)
        self.assertEqual(constructor.call_args.kwargs["adapterDeviceId"], 42)
        self.assertEqual(constructor.call_args.kwargs["screenSize"], 5)
        self.assertEqual(constructor.call_args.kwargs["i2cAddress"], 0x27)
        self.assertEqual(constructor.call_args.kwargs["pinMapping"], {
            "rs": 0, "rw": 1, "enable": 2, "backlight": 3,
            "d4": 4, "d5": 5, "d6": 6, "d7": 7,
        })

    def test_i2c_lcd_validation_rejects_unresponsive_address(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginId = "com.yikes.eric.phidgets-indigo"
        instance.logger = mock.Mock()
        instance.discoveryInventory = mock.Mock()
        instance.discoveryInventory.compatible_channels.return_value = []
        adapter = mock.Mock(_state="attached")
        adapter.i2cAddressResponds.return_value = False
        instance.activePhidgets = {42: adapter}
        adapter_device = types.SimpleNamespace(
            id=42, name="Library display bus", enabled=True,
            pluginId=instance.pluginId, deviceTypeId="dataAdapter", states={},
            pluginProps={"serialNumber": "729035", "channel": "0",
                         "serverName": "CM-Library Mac"})
        indigo.devices = DeviceCollection({42: adapter_device})
        indigo.variables = {}
        values = indigo.Dict({
            "lcdDisplayProvider": "adapter:42",
            "lcdProviderKind": "adapter", "lcdAdapterDeviceId": "42",
            "lcdProfile": "freenove-hd44780-pcf8574",
            "lcdI2CAddress": "0x26", "lcdScreenSize": "5",
            "lcdBacklight": "1.0", "lcdContrast": "0.5",
            "lcdInitialX": "0", "lcdInitialY": "0",
            "serialNumber": "729035", "channel": "0", "serverName": "",
            "isVintHub": False, "isVintDevice": False,
        })

        valid, returned, errors = instance.validateDeviceConfigUi(
            values, "lcd", 0)

        self.assertFalse(valid)
        self.assertIn("No I2C device responded at 0x26", errors["lcdI2CAddress"])
        adapter.i2cAddressResponds.assert_called_once_with(0x26)

    def test_adapter_attachment_starts_a_dependent_i2c_display(self):
        instance = object.__new__(plugin.Plugin)
        instance.pluginId = "com.yikes.eric.phidgets-indigo"
        instance.logger = mock.Mock()
        instance.activePhidgets = {42: mock.sentinel.adapter}
        instance.deviceStartComm = mock.Mock()
        lcd_device = types.SimpleNamespace(
            id=99, enabled=True, pluginId=instance.pluginId,
            deviceTypeId="lcd", pluginProps={"lcdAdapterDeviceId": "42"})
        indigo.devices = DeviceCollection({99: lcd_device})
        adapter = types.SimpleNamespace(
            indigoDevice=types.SimpleNamespace(id=42),
            supportsFunction=lambda value: value == "lcd",
            _identity=lambda: "adapter")

        instance.phidgetAttachCompleted(
            adapter, detached_for=0.1, attach_count=1,
            detach_announced=False)

        instance.deviceStartComm.assert_called_once_with(lcd_device)

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
        active_lcd.runDisplayWhenAttached = mock.Mock(
            side_effect=lambda callback: callback())
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
        self.assertEqual(values["graphicContentLayout"], "hidden")
        self.assertEqual(values["graphicLineLayout"], "hidden")
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
        self.assertEqual(returned["graphicContentLayout"], "hidden")
        self.assertEqual(returned["graphicLineLayout"], "hidden")

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

        valid, values, errors = instance.validateActionConfigUi(indigo.Dict({
            "lineCount": "0", "animationMode": "static",
            "graphicContentType": "formula", "formulaExpression": "'text'",
            "formulaXMin": "-1", "formulaXMax": "1",
            "formulaYMin": "-1", "formulaYMax": "1",
            "formulaStyle": "line", "backlight": "1.0", "contrast": "0.5",
        }), "lcdStartAnimation", 42)
        self.assertFalse(valid)
        self.assertIn("formulaExpression", errors)

        valid, values = instance.validateActionConfigUi(indigo.Dict({
            "lineCount": "0", "animationMode": "static",
            "graphicContentType": "donut", "donutInterval": "0.2",
            "backlight": "1.0", "contrast": "0.5",
        }), "lcdStartAnimation", 42)
        self.assertTrue(valid)
        self.assertEqual(values["donutInterval"], "0.2")

        valid, values, errors = instance.validateActionConfigUi(indigo.Dict({
            "lineCount": "0", "animationMode": "static",
            "graphicContentType": "donut", "donutInterval": "0.01",
            "backlight": "1.0", "contrast": "0.5",
        }), "lcdStartAnimation", 42)
        self.assertFalse(valid)
        self.assertIn("donutInterval", errors)

    def test_lcd_action_validation_persists_cleared_text_fields(self):
        instance = object.__new__(plugin.Plugin)
        values = indigo.Dict({
            "lineCount": "4", "animationMode": "marquee",
            "animationLine1": "Current", "marqueeDirection": "left",
            "marqueeGap": "3", "marqueeInterval": "0.4",
            "backlight": "1.0", "contrast": "0.5",
        })

        valid, returned = instance.validateActionConfigUi(
            values, "lcdStartAnimation", 42)

        self.assertTrue(valid)
        self.assertEqual(returned["animationLine1"], "Current")
        for field in ("animationLine2", "animationLine3", "animationLine4",
                      "alternateLine1", "alternateLine2", "alternateLine3",
                      "alternateLine4", "virtualText", "graphicText"):
            self.assertIn(field, returned)
            self.assertEqual(returned[field], "")

    def test_stopping_adapter_quiesces_dependent_lcd_first(self):
        instance = object.__new__(plugin.Plugin)
        instance.logger = mock.Mock()
        provider = mock.Mock()
        provider.supportsFunction.return_value = True
        dependent = mock.Mock()
        dependent.adapterDeviceId = 42
        instance.activePhidgets = {42: provider, 91: dependent}
        device = mock.Mock(id=42, name="I2C Adapter 1")

        instance.deviceStopComm(device)

        dependent.providerStopping.assert_called_once_with()
        provider.stop.assert_called_once_with()
        self.assertNotIn(42, instance.activePhidgets)


if __name__ == "__main__":
    unittest.main()
