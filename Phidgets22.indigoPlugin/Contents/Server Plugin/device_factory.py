# -*- coding: utf-8 -*-

"""Construct Phidget wrapper instances from saved Indigo device properties."""

import indigo

from phidget import ChannelInfo, NetInfo
from voltageinput import VoltageInputPhidget
from voltageratioinput import VoltageRatioInputPhidget
from digitaloutput import DigitalOutputPhidget
from temperaturesensor import TemperatureSensorPhidget
from digitalinput import DigitalInputPhidget
from frequencycounter import FrequencyCounterPhidget
from humiditysensor import HumiditySensorPhidget
from lcd import NativeLCDPhidget
from i2c_lcd import I2CLCDPhidget
from dataadapter import DataAdapterPhidget
from adapter_gpio import AdapterGPIOInputPhidget, AdapterGPIOOutputPhidget
from bme280 import BME280Phidget
from sgp41 import SGP41Phidget


def _saved_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _channel_info(plugin, device):
    props = device.pluginProps
    serial_number = props.get("serialNumber", None)
    serial_number = int(serial_number) if serial_number else -1
    channel = props.get("channel", None)
    channel = int(channel) if channel else -1

    is_vint_hub = props.get("isVintHub", None)
    is_vint_hub = bool(is_vint_hub) if is_vint_hub else 0
    is_vint_device = props.get("isVintDevice", None)
    is_vint_device = bool(is_vint_device) if is_vint_device else 0
    is_hub_port_device = int(is_vint_hub and not is_vint_device)
    hub_port = props.get("hubPort", -1)
    hub_port = int(hub_port) if hub_port else -1

    return ChannelInfo(
        serialNumber=serial_number,
        channel=channel,
        isHubPortDevice=is_hub_port_device,
        hubPort=hub_port,
        netInfo=NetInfo(
            isRemote=plugin.pluginPrefs.get("networkPhidgets", False),
            serverDiscovery=plugin.pluginPrefs.get("enableServerDiscovery", False),
            serverName=props.get("serverName", None),
        ),
    )


def _common(plugin, device):
    props = device.pluginProps
    data_interval = props.get("dataInterval", None)
    data_interval = int(data_interval) if data_interval else None
    return {
        "base": {
            "indigo_plugin": plugin,
            "channelInfo": _channel_info(plugin, device),
            "indigoDevice": device,
            "logger": plugin.logger,
        },
        "dataInterval": data_interval,
        "decimalPlaces": int(props.get("decimalPlaces", 3)),
    }


def _custom_formula(props):
    if props.get("useCustomFormula", False):
        return props.get("customState", None), props.get("customFormula", None)
    return None, None


def _voltage_input(plugin, device, common):
    props = device.pluginProps
    custom_state, custom_formula = _custom_formula(props)
    return VoltageInputPhidget(
        **common["base"], decimalPlaces=common["decimalPlaces"],
        sensorType=int(props.get("voltageSensorType", 0)),
        dataInterval=common["dataInterval"],
        voltageChangeTrigger=float(props.get("voltageChangeTrigger", 0)),
        sensorValueChangeTrigger=float(props.get("sensorValueChangeTrigger", 0)),
        customState=custom_state, customFormula=custom_formula)


def _voltage_ratio_input(plugin, device, common):
    props = device.pluginProps
    custom_state, custom_formula = _custom_formula(props)
    return VoltageRatioInputPhidget(
        **common["base"], decimalPlaces=common["decimalPlaces"],
        sensorType=int(props.get("voltageRatioSensorType", 0)),
        dataInterval=common["dataInterval"],
        voltageRatioChangeTrigger=float(props.get("voltageRatioChangeTrigger", 0)),
        sensorValueChangeTrigger=float(props.get("sensorValueChangeTrigger", 0)),
        customState=custom_state, customFormula=custom_formula)


def _digital_output(plugin, device, common):
    return DigitalOutputPhidget(**common["base"])


def _digital_input(plugin, device, common):
    props = device.pluginProps
    return DigitalInputPhidget(
        **common["base"],
        isAlarm=bool(props.get("isAlarm", False)),
        onStateIcon=str(props.get("onStateIcon", "SensorOn")),
        offStateIcon=str(props.get("offStateIcon", "SensorOff")))


def _temperature_sensor(plugin, device, common):
    props = device.pluginProps
    thermocouple_type = (int(props.get("thermocoupleType", None))
                         if props.get("useThermoCouple", False) else None)
    return TemperatureSensorPhidget(
        **common["base"], decimalPlaces=common["decimalPlaces"],
        displayTempUnit=props.get("displayTempUnit", "C"),
        thermocoupleType=thermocouple_type,
        dataInterval=common["dataInterval"],
        temperatureChangeTrigger=float(props.get("temperatureChangeTrigger", 0)))


def _frequency_counter(plugin, device, common):
    props = device.pluginProps
    return FrequencyCounterPhidget(
        **common["base"], decimalPlaces=common["decimalPlaces"],
        filterType=int(props.get("filterType", 0)),
        dataInterval=common["dataInterval"],
        displayStateName=props.get("displayStateName", None),
        frequencyCutoff=float(props.get("frequencyCutoff", 1)),
        isDAQ1400=bool(props.get("isDAQ1400", False)),
        inputType=int(props.get("inputType", 0)),
        powerSupply=int(props.get("powerSupply", 0)))


def _humidity_sensor(plugin, device, common):
    props = device.pluginProps
    return HumiditySensorPhidget(
        **common["base"], decimalPlaces=common["decimalPlaces"],
        humidityChangeTrigger=float(props.get("humidityChangeTrigger", 0)),
        dataInterval=common["dataInterval"])


def _lcd(plugin, device, common):
    props = device.pluginProps
    lcd_class = (I2CLCDPhidget
                 if props.get("lcdProviderKind") == "adapter"
                 else NativeLCDPhidget)
    extra = ({
        "adapterDeviceId": int(props["lcdAdapterDeviceId"]),
        "i2cAddress": int(str(props.get("lcdI2CAddress", "0x27")), 0),
        "pinMapping": {
            key: int(props.get("lcdI2C%sPin" % label, default))
            for key, label, default in (
                ("rs", "RS", 0), ("rw", "RW", 1),
                ("enable", "Enable", 2), ("backlight", "Backlight", 3),
                ("d4", "D4", 4), ("d5", "D5", 5),
                ("d6", "D6", 6), ("d7", "D7", 7))
        },
        "backlightActiveHigh": _saved_bool(
            props.get("lcdI2CBacklightActiveHigh", True)),
    }
             if lcd_class is I2CLCDPhidget else {})
    return lcd_class(
        **common["base"],
        **extra,
        screenSize=int(props.get("lcdScreenSize", 1)),
        backlight=float(props.get("lcdBacklight", 1.0)),
        contrast=float(props.get("lcdContrast", 0.5)),
        restoreInitialText=_saved_bool(props.get("lcdRestoreInitialText", False)),
        initialText=props.get("lcdInitialText", ""),
        initialLines=[props.get("lcdInitialLine%d" % line_number, "")
                      for line_number in range(1, 5)],
        initialX=int(props.get("lcdInitialX", 0)),
        initialY=int(props.get("lcdInitialY", 0)))


def _data_adapter(plugin, device, common):
    props = device.pluginProps
    return DataAdapterPhidget(
        **common["base"],
        voltage=int(props.get("dataAdapterVoltage", 5)),
        frequency=int(props.get("dataAdapterFrequency", 2)))


def _adapter_gpio_channel_info(plugin, device):
    adapter = plugin.activePhidgets.get(int(device.pluginProps["gpioAdapterDeviceId"]))
    if adapter is None:
        adapter_device = indigo.devices[int(device.pluginProps["gpioAdapterDeviceId"])]
        info = _channel_info(plugin, adapter_device)
    else:
        source = adapter.channelInfo
        info = ChannelInfo(
            serialNumber=source.serialNumber, hubPort=source.hubPort,
            isHubPortDevice=source.isHubPortDevice,
            netInfo=source.netInfo)
    info.channel = int(device.pluginProps.get("gpioPin", 0))
    return info


def _adapter_gpio_input(plugin, device, common):
    props = device.pluginProps
    common["base"]["channelInfo"] = _adapter_gpio_channel_info(plugin, device)
    return AdapterGPIOInputPhidget(
        **common["base"], adapterDeviceId=int(props["gpioAdapterDeviceId"]),
        inputMode=props.get("gpioInputMode", "pullup"),
        inverted=_saved_bool(props.get("gpioInverted", True)),
        debounceMilliseconds=int(props.get("gpioDebounceMilliseconds", 50)),
        isAlarm=False, onStateIcon="SensorOn", offStateIcon="SensorOff")


def _adapter_gpio_output(plugin, device, common):
    common["base"]["channelInfo"] = _adapter_gpio_channel_info(plugin, device)
    return AdapterGPIOOutputPhidget(
        **common["base"],
        adapterDeviceId=int(device.pluginProps["gpioAdapterDeviceId"]))


def _bme280(plugin, device, common):
    props = device.pluginProps
    return BME280Phidget(
        **common["base"], decimalPlaces=common["decimalPlaces"],
        adapterDeviceId=int(props["bmeAdapterDeviceId"]),
        i2cAddress=int(str(props.get("bmeI2CAddress", "0x76")), 0),
        pollInterval=float(props.get("bmePollInterval", 2.0)))


def _sgp41(plugin, device, common):
    props = device.pluginProps
    return SGP41Phidget(
        **common["base"],
        adapterDeviceId=int(props["sgpAdapterDeviceId"]),
        relativeHumidity=float(props.get("sgpRelativeHumidity", 50.0)),
        temperature=float(props.get("sgpTemperature", 25.0)))


_BUILDERS = {
    "voltageInput": _voltage_input,
    "voltageRatioInput": _voltage_ratio_input,
    "digitalOutput": _digital_output,
    "digitalInput": _digital_input,
    "temperatureSensor": _temperature_sensor,
    "frequencyCounter": _frequency_counter,
    "humiditySensor": _humidity_sensor,
    "lcd": _lcd,
    "dataAdapter": _data_adapter,
    "adapterGPIOInput": _adapter_gpio_input,
    "adapterGPIOOutput": _adapter_gpio_output,
    "bme280": _bme280,
    "sgp41": _sgp41,
}


def create_phidget(plugin, device):
    """Return the configured wrapper for an Indigo Phidget device."""
    try:
        builder = _BUILDERS[device.deviceTypeId]
    except KeyError:
        raise ValueError("Unexpected device type: %s" % device.deviceTypeId)
    return builder(plugin, device, _common(plugin, device))
