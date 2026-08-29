# -*- coding: utf-8 -*-

"""Indigo configuration callbacks backed by the live discovery inventory."""

import indigo

from discovery import (CHANNEL_CLASSES_BY_DEVICE_TYPE, device_token,
                       channel_token, format_channel, format_network_diagram,
                       port_token, server_token, target_token)
from display_providers import available_display_providers


FREENOVE_I2C_PROFILE = "freenove-hd44780-pcf8574"
FREENOVE_I2C_DEFAULTS = {
    "lcdI2CAddress": "0x27",
    "lcdI2CRSPin": "0", "lcdI2CRWPin": "1",
    "lcdI2CEnablePin": "2", "lcdI2CBacklightPin": "3",
    "lcdI2CD4Pin": "4", "lcdI2CD5Pin": "5",
    "lcdI2CD6Pin": "6", "lcdI2CD7Pin": "7",
    "lcdI2CBacklightActiveHigh": True,
}


def _sensirion_crc(data):
    value = 0xFF
    for byte in bytearray(data):
        value ^= byte
        for _ in range(8):
            value = (((value << 1) ^ 0x31) & 0xFF
                     if value & 0x80 else (value << 1) & 0xFF)
    return value


class DiscoveryUiMixin(object):
    LCD_SCREEN_SIZES = [
        ("1", "Automatic / graphic LCD"),
        ("2", "1 row × 8 characters"), ("3", "2 rows × 8 characters"),
        ("4", "1 row × 16 characters"), ("5", "2 rows × 16 characters"),
        ("6", "4 rows × 16 characters"), ("7", "2 rows × 20 characters"),
        ("8", "4 rows × 20 characters"), ("9", "2 rows × 24 characters"),
        ("10", "1 row × 40 characters"), ("11", "2 rows × 40 characters"),
        ("12", "4 rows × 40 characters"),
    ]

    def getLCDScreenSizeMenu(self, filter="", valuesDict=None,
                             typeId="", targetId=0):
        if valuesDict is not None and valuesDict.get("lcdProviderKind") == "adapter":
            return [choice for choice in self.LCD_SCREEN_SIZES
                    if choice[0] in ("5", "8")]
        return list(self.LCD_SCREEN_SIZES)

    def getAvailableDisplayMenu(self, filter="", valuesDict=None,
                                typeId="", targetId=0):
        """Supply one future LCD selector without exposing its transport."""
        providers = available_display_providers(self)
        return [("selectDisplay", "Select a display")] + [
            (provider["id"], provider["name"]) for provider in providers]

    def _availableGPIOAdapters(self):
        return [device for device in getattr(indigo, "devices", ())
                if (getattr(device, "pluginId", None) == self.pluginId and
                    getattr(device, "deviceTypeId", None) == "dataAdapter" and
                    getattr(device, "enabled", True))]

    def getAvailableGPIOAdapterMenu(self, filter="", valuesDict=None,
                                    typeId="", targetId=0):
        return [("selectAdapter", "Select an I2C adapter")] + [
            (str(device.id), device.name)
            for device in sorted(
                self._availableGPIOAdapters(),
                key=lambda candidate: candidate.name.lower())]

    def _applyGPIOAdapter(self, valuesDict, selection):
        try:
            adapter = indigo.devices[int(selection)]
        except (IndexError, KeyError, TypeError, ValueError):
            return valuesDict
        available_ids = {
            getattr(device, "id", None)
            for device in self._availableGPIOAdapters()}
        if getattr(adapter, "id", None) not in available_ids:
            return valuesDict
        valuesDict["gpioAdapterSelection"] = str(adapter.id)
        valuesDict["gpioAdapterDeviceId"] = str(adapter.id)
        valuesDict["observedConnection"] = "%s→GPIO %s" % (
            adapter.name, valuesDict.get("gpioPin", "0"))
        return valuesDict

    def gpioAdapterChanged(self, valuesDict, typeId, devId):
        return self._applyGPIOAdapter(
            valuesDict, valuesDict.get("gpioAdapterSelection", ""))

    def _applyBMEAdapter(self, valuesDict, selection):
        try:
            adapter = indigo.devices[int(selection)]
        except (IndexError, KeyError, TypeError, ValueError):
            return valuesDict
        available_ids = {
            getattr(device, "id", None)
            for device in self._availableGPIOAdapters()}
        if getattr(adapter, "id", None) not in available_ids:
            return valuesDict
        valuesDict["bmeAdapterSelection"] = str(adapter.id)
        valuesDict["bmeAdapterDeviceId"] = str(adapter.id)
        valuesDict["observedConnection"] = "%s→BME/BMP280" % adapter.name
        return valuesDict

    def bmeAdapterChanged(self, valuesDict, typeId, devId):
        return self._applyBMEAdapter(
            valuesDict, valuesDict.get("bmeAdapterSelection", ""))

    def _applySGPAdapter(self, valuesDict, selection):
        try:
            adapter = indigo.devices[int(selection)]
        except (IndexError, KeyError, TypeError, ValueError):
            return valuesDict
        available_ids = {getattr(device, "id", None)
                         for device in self._availableGPIOAdapters()}
        if getattr(adapter, "id", None) not in available_ids:
            return valuesDict
        valuesDict["sgpAdapterSelection"] = str(adapter.id)
        valuesDict["sgpAdapterDeviceId"] = str(adapter.id)
        valuesDict["observedConnection"] = "%s→SGP41 0x59" % adapter.name
        return valuesDict

    def sgpAdapterChanged(self, valuesDict, typeId, devId):
        return self._applySGPAdapter(
            valuesDict, valuesDict.get("sgpAdapterSelection", ""))

    def _applyDisplayProvider(self, valuesDict, selection, devId=0):
        providers = {provider["id"]: provider
                     for provider in available_display_providers(self)}
        provider = providers.get(selection)
        valuesDict["compatibleModelFound"] = bool(providers)
        if provider is None:
            return valuesDict
        valuesDict["lcdDisplayProvider"] = provider["id"]
        valuesDict["lcdProviderKind"] = provider["kind"]
        if provider["kind"] == "native":
            description = provider["channel"]
            valuesDict["lcdAdapterDeviceId"] = ""
            valuesDict["lcdProfile"] = "native"
            valuesDict["discoveredServer"] = server_token(description)
            valuesDict["discoveredDevice"] = device_token(description)
            valuesDict["discoveredChannel"] = channel_token(description)
            if description.get("deviceClass") == 21:
                valuesDict["discoveredPort"] = port_token(description)
                valuesDict["discoveredTarget"] = target_token(description)
            return self.menuChanged(valuesDict, "lcd", devId)

        adapter_id = int(provider["adapterDeviceId"])
        adapter_device = indigo.devices[adapter_id]
        adapter_props = adapter_device.pluginProps
        valuesDict["lcdAdapterDeviceId"] = str(adapter_id)
        old_profile = valuesDict.get("lcdProfile", "")
        if old_profile in ("", "freenove-lcd2004-pcf8574t"):
            valuesDict["lcdProfile"] = FREENOVE_I2C_PROFILE
        if not valuesDict.get("lcdScreenSize", ""):
            valuesDict["lcdScreenSize"] = "8"
        for key, default in FREENOVE_I2C_DEFAULTS.items():
            if valuesDict.get(key, None) in (None, ""):
                valuesDict[key] = default
        valuesDict["discoveredChannel"] = "manual"
        valuesDict["serialNumber"] = str(adapter_props.get("serialNumber", ""))
        valuesDict["channel"] = str(adapter_props.get("channel", "0"))
        valuesDict["serverName"] = str(adapter_props.get("serverName", ""))
        valuesDict["observedConnection"] = "%s→I2C character LCD" % adapter_device.name
        return valuesDict

    def lcdProfileChanged(self, valuesDict, typeId, devId):
        if valuesDict.get("lcdProfile") == FREENOVE_I2C_PROFILE:
            for key, default in FREENOVE_I2C_DEFAULTS.items():
                valuesDict[key] = default
        return valuesDict

    def displayProviderChanged(self, valuesDict, typeId, devId):
        return self._applyDisplayProvider(
            valuesDict, valuesDict.get("lcdDisplayProvider", ""), devId)

    def validatePrefsConfigUi(self, valuesDict):
        try:
            attach_timeout = int(valuesDict.get("attachTimeout", "5"))
            if attach_timeout <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors = indigo.Dict()
            errors["attachTimeout"] = "Enter a whole number greater than zero."
            return False, valuesDict, errors

        valuesDict["attachTimeout"] = str(attach_timeout)
        return True

    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        """Initialize, safely migrate, and collapse discovery selections."""
        values = indigo.Dict(pluginProps)
        values["configurationMigrated"] = False
        values["observedConnection"] = self._observedConnectionForDevice(devId)
        defaults = {
            "discoveredServer": "manual",
            "discoveredDevice": "selectServer",
            "discoveredPort": "selectDevice",
            "discoveredTarget": "selectPort",
            "discoveredChannel": "selectTarget",
        }
        for key, value in defaults.items():
            if values.get(key, None) is None:
                values[key] = value

        if typeId in ("adapterGPIOInput", "adapterGPIOOutput"):
            selection = (values.get("gpioAdapterSelection") or
                         values.get("gpioAdapterDeviceId") or "")
            adapters = self._availableGPIOAdapters()
            if not selection and len(adapters) == 1:
                selection = str(adapters[0].id)
            if selection:
                values = self._applyGPIOAdapter(values, selection)
            return (values, indigo.Dict())

        if typeId == "bme280":
            selection = (values.get("bmeAdapterSelection") or
                         values.get("bmeAdapterDeviceId") or "")
            adapters = self._availableGPIOAdapters()
            if not selection and len(adapters) == 1:
                selection = str(adapters[0].id)
            if selection:
                values = self._applyBMEAdapter(values, selection)
            return (values, indigo.Dict())

        if typeId == "sgp41":
            selection = (values.get("sgpAdapterSelection") or
                         values.get("sgpAdapterDeviceId") or "")
            adapters = self._availableGPIOAdapters()
            if not selection and len(adapters) == 1:
                selection = str(adapters[0].id)
            if selection:
                values = self._applySGPAdapter(values, selection)
            return (values, indigo.Dict())

        selected_channel = values.get("discoveredChannel", "")
        resolved_channel = (self.discoveryInventory.resolve_channel(selected_channel)
                            if self.discoveryInventory is not None else None)
        if self.discoveryInventory is not None and resolved_channel is None:
            recovered = self.discoveryInventory.selection_for_saved_address(
                typeId, values)
            if recovered is not None:
                for key, value in recovered.items():
                    values[key] = value
                values["configurationMigrated"] = True
        values = self.menuChanged(values, typeId, devId)
        if typeId == "lcd":
            providers = available_display_providers(self)
            values["compatibleModelFound"] = bool(providers)
            selection = values.get("lcdDisplayProvider", "")
            if not selection:
                description = (self.discoveryInventory.resolve_channel(
                    values.get("discoveredChannel", ""))
                    if self.discoveryInventory is not None else None)
                if description is not None:
                    selection = "native:%s" % channel_token(description)
                elif len(providers) == 1:
                    selection = providers[0]["id"]
            if selection:
                values = self._applyDisplayProvider(values, selection, devId)
        return (values, indigo.Dict())

    def _observedConnectionForDevice(self, devId):
        if devId:
            try:
                device_states = indigo.devices[devId].states
                return (device_states.get("connectionPath") or
                        device_states.get("connection") or
                        "Not yet observed")
            except Exception:
                pass
        return "Not yet observed"

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        valuesDict["observedConnection"] = self._observedConnectionForDevice(devId)
        if typeId == "sgp41":
            errors = indigo.Dict()
            selection = valuesDict.get("sgpAdapterSelection", "")
            valuesDict = self._applySGPAdapter(valuesDict, selection)
            adapter_id = str(valuesDict.get("sgpAdapterDeviceId", ""))
            if not adapter_id or adapter_id != str(selection):
                errors["sgpAdapterSelection"] = "Select an available I2C adapter."
            display_state = valuesDict.get("sgpDisplayState", "rawVoc")
            if display_state not in ("rawVoc", "rawNox"):
                errors["sgpDisplayState"] = "Select Raw VOC or Raw NOx."
            for key, label, minimum, maximum in (
                    ("sgpRelativeHumidity", "relative humidity", 0.0, 100.0),
                    ("sgpTemperature", "temperature", -45.0, 130.0)):
                try:
                    value = float(valuesDict.get(key, ""))
                    if value < minimum or value > maximum:
                        raise ValueError
                    valuesDict[key] = str(value)
                except (TypeError, ValueError):
                    errors[key] = "Enter %s from %g through %g." % (
                        label, minimum, maximum)
            if adapter_id:
                for other in getattr(indigo, "devices", ()):
                    if (getattr(other, "id", None) == devId or
                            getattr(other, "pluginId", None) != self.pluginId or
                            not getattr(other, "enabled", True)):
                        continue
                    props = getattr(other, "pluginProps", {})
                    other_type = getattr(other, "deviceTypeId", None)
                    other_adapter = (props.get("sgpAdapterDeviceId")
                                     if other_type == "sgp41" else
                                     props.get("bmeAdapterDeviceId")
                                     if other_type == "bme280" else
                                     props.get("lcdAdapterDeviceId")
                                     if other_type == "lcd" else None)
                    other_address = (0x59 if other_type == "sgp41" else
                                     props.get("bmeI2CAddress")
                                     if other_type == "bme280" else
                                     props.get("lcdI2CAddress")
                                     if other_type == "lcd" else None)
                    try:
                        collision = (str(other_adapter) == adapter_id and
                                     int(str(other_address), 0) == 0x59)
                    except (TypeError, ValueError):
                        collision = False
                    if collision:
                        errors["sgpAdapterSelection"] = (
                            "Address 0x59 is already assigned to '%s'." %
                            getattr(other, "name", "another device"))
                        break
                adapter = self.activePhidgets.get(int(adapter_id))
                if adapter is not None and "sgpAdapterSelection" not in errors:
                    try:
                        response = bytes(adapter.i2cCommandResponse(
                            0x59, b"\x36\x82", 0.001, 9))
                        if len(response) != 9:
                            raise ValueError("incomplete serial-number response")
                        for offset in range(0, 9, 3):
                            if response[offset + 2] != _sensirion_crc(
                                    response[offset:offset + 2]):
                                raise ValueError("invalid serial-number CRC")
                    except Exception as error:
                        errors["sgpAdapterSelection"] = (
                            "Unable to verify SGP41 at 0x59: %s" % error)
            if errors:
                errors["showAlertText"] = "Correct the SGP41 settings before saving."
                return (False, valuesDict, errors)
            valuesDict["address"] = "sgp41-%s-59" % adapter_id
            valuesDict["observedConnection"] = "%s→SGP41 0x59" % (
                indigo.devices[int(adapter_id)].name)
            return (True, valuesDict)
        if typeId == "bme280":
            errors = indigo.Dict()
            selection = valuesDict.get("bmeAdapterSelection", "")
            valuesDict = self._applyBMEAdapter(valuesDict, selection)
            adapter_id = str(valuesDict.get("bmeAdapterDeviceId", ""))
            if not adapter_id or adapter_id != str(selection):
                errors["bmeAdapterSelection"] = "Select an available I2C adapter."
            display_state = valuesDict.get("bmeDisplayState", "pressure")
            if display_state not in ("temperature", "pressure", "humidity"):
                errors["bmeDisplayState"] = (
                    "Select temperature, pressure, or humidity.")
            try:
                address = int(str(valuesDict.get("bmeI2CAddress", "")), 0)
                if address not in (0x76, 0x77):
                    raise ValueError
                valuesDict["bmeI2CAddress"] = "0x%02X" % address
            except (TypeError, ValueError):
                address = None
                errors["bmeI2CAddress"] = "Select address 0x76 or 0x77."
            try:
                interval = float(valuesDict.get("bmePollInterval", "2"))
                if interval < 1.0 or interval > 3600.0:
                    raise ValueError
                valuesDict["bmePollInterval"] = str(interval)
            except (TypeError, ValueError):
                errors["bmePollInterval"] = (
                    "Enter a polling interval from 1 to 3600 seconds.")
            try:
                decimal_places = int(valuesDict.get("decimalPlaces", "2"))
                if decimal_places < 0 or decimal_places > 6:
                    raise ValueError
                valuesDict["decimalPlaces"] = str(decimal_places)
            except (TypeError, ValueError):
                errors["decimalPlaces"] = (
                    "Enter a whole number from 0 through 6.")
            if adapter_id and address is not None:
                for other in getattr(indigo, "devices", ()):
                    if (getattr(other, "id", None) == devId or
                            getattr(other, "pluginId", None) != self.pluginId or
                            not getattr(other, "enabled", True)):
                        continue
                    props = getattr(other, "pluginProps", {})
                    other_adapter = (props.get("bmeAdapterDeviceId")
                                     if getattr(other, "deviceTypeId", None) == "bme280"
                                     else props.get("lcdAdapterDeviceId")
                                     if getattr(other, "deviceTypeId", None) == "lcd"
                                     else None)
                    other_address = (props.get("bmeI2CAddress")
                                     if getattr(other, "deviceTypeId", None) == "bme280"
                                     else props.get("lcdI2CAddress")
                                     if getattr(other, "deviceTypeId", None) == "lcd"
                                     else None)
                    try:
                        collision = (str(other_adapter) == adapter_id and
                                     int(str(other_address), 0) == address)
                    except (TypeError, ValueError):
                        collision = False
                    if collision:
                        errors["bmeI2CAddress"] = (
                            "Address 0x%02X is already assigned to '%s'." %
                            (address, getattr(other, "name", "another device")))
                        break
                adapter = self.activePhidgets.get(int(adapter_id))
                if adapter is not None and "bmeI2CAddress" not in errors:
                    try:
                        response = bytes(adapter.i2cSendReceive(
                            address, bytes((0xD0,)), 1))
                        if len(response) != 1 or response[0] not in (0x58, 0x60):
                            found = "no chip ID" if not response else "chip ID 0x%02X" % response[0]
                            errors["bmeI2CAddress"] = (
                                "No BME280/BMP280 found at 0x%02X (%s)." %
                                (address, found))
                        elif (response[0] == 0x58 and
                              display_state == "humidity"):
                            errors["bmeDisplayState"] = (
                                "BMP280 does not provide a humidity state.")
                    except Exception as error:
                        errors["bmeI2CAddress"] = (
                            "Unable to verify address 0x%02X: %s" %
                            (address, error))
            if errors:
                errors["showAlertText"] = (
                    "Correct the BME280/BMP280 settings before saving.")
                return (False, valuesDict, errors)
            valuesDict["address"] = "bme280-%s-%02x" % (adapter_id, address)
            valuesDict["observedConnection"] = "%s→BME/BMP280 0x%02X" % (
                indigo.devices[int(adapter_id)].name, address)
            return (True, valuesDict)
        if typeId in ("adapterGPIOInput", "adapterGPIOOutput"):
            errors = indigo.Dict()
            selection = valuesDict.get("gpioAdapterSelection", "")
            valuesDict = self._applyGPIOAdapter(valuesDict, selection)
            adapter_id = str(valuesDict.get("gpioAdapterDeviceId", ""))
            if not adapter_id or adapter_id != str(selection):
                errors["gpioAdapterSelection"] = "Select an available I2C adapter."
            try:
                pin = int(valuesDict.get("gpioPin", ""))
                if pin not in (0, 1):
                    raise ValueError
                valuesDict["gpioPin"] = str(pin)
            except (TypeError, ValueError):
                pin = None
                errors["gpioPin"] = "Select GPIO 0 or GPIO 1."

            if typeId == "adapterGPIOInput":
                if valuesDict.get("gpioInputMode", "pullup") not in (
                        "pullup", "floating"):
                    errors["gpioInputMode"] = "Select Pull-up or Floating."
                try:
                    debounce = int(valuesDict.get(
                        "gpioDebounceMilliseconds", "50"))
                    if debounce < 0 or debounce > 5000:
                        raise ValueError
                    valuesDict["gpioDebounceMilliseconds"] = str(debounce)
                except (TypeError, ValueError):
                    errors["gpioDebounceMilliseconds"] = (
                        "Enter a whole number from 0 through 5000.")

            if adapter_id and pin is not None:
                for other in getattr(indigo, "devices", ()):
                    props = getattr(other, "pluginProps", {})
                    if (getattr(other, "id", None) == devId or
                            getattr(other, "pluginId", None) != self.pluginId or
                            getattr(other, "deviceTypeId", None) not in
                            ("adapterGPIOInput", "adapterGPIOOutput") or
                            not getattr(other, "enabled", True)):
                        continue
                    if (str(props.get("gpioAdapterDeviceId", "")) == adapter_id and
                            str(props.get("gpioPin", "")) == str(pin)):
                        errors["gpioPin"] = (
                            "GPIO %d is already assigned to '%s'." %
                            (pin, getattr(other, "name", "another device")))
                        break
            if errors:
                errors["showAlertText"] = "Correct the GPIO settings before saving."
                return (False, valuesDict, errors)
            valuesDict["address"] = "gpio-%s-%s" % (adapter_id, pin)
            valuesDict["observedConnection"] = "%s→GPIO %s" % (
                indigo.devices[int(adapter_id)].name, pin)
            return (True, valuesDict)
        if typeId == "lcd":
            selection = valuesDict.get("lcdDisplayProvider", "")
            providers = {provider["id"]: provider
                         for provider in available_display_providers(self)}
            saved_native_offline = bool(
                devId and valuesDict.get("lcdProviderKind", "native") == "native" and
                str(valuesDict.get("serialNumber", "")).strip() and
                str(valuesDict.get("channel", "")).strip())
            if selection not in providers and not saved_native_offline:
                errors = indigo.Dict()
                errors["lcdDisplayProvider"] = "Select an available display."
                errors["showAlertText"] = "Select an available display before saving."
                return (False, valuesDict, errors)
            valuesDict = self._applyDisplayProvider(valuesDict, selection, devId)
        inventory = getattr(self, "discoveryInventory", None)
        compatible_available = bool(
            inventory is not None and inventory.server_choices(typeId))
        has_saved_address = bool(
            str(valuesDict.get("serialNumber", "")).strip() and
            str(valuesDict.get("channel", "")).strip())
        if not has_saved_address:
            errors = indigo.Dict()
            if compatible_available:
                errors["discoveredServer"] = "Select a compatible device."
                errors["showAlertText"] = (
                    "Select an available device and channel before saving.")
            else:
                errors["discoveredServer"] = "No compatible device is available."
                errors["showAlertText"] = (
                    "Connect and install an appropriate device before saving.")
            return (False, valuesDict, errors)

        selected_channel = valuesDict.get("discoveredChannel", "")
        description = None
        if selected_channel and selected_channel not in (
                "manual", "selectDevice", "selectChannel"):
            description = (self.discoveryInventory.resolve_channel(selected_channel)
                           if self.discoveryInventory is not None else None)
            expected_class = CHANNEL_CLASSES_BY_DEVICE_TYPE.get(typeId)
            if (description is None or
                    description.get("channelClassName") != expected_class or
                    device_token(description) != valuesDict.get("discoveredDevice", "") or
                    (description is not None and description.get("deviceClass") == 21 and
                     target_token(description) != valuesDict.get("discoveredTarget", "")) or
                    (valuesDict.get("discoveredServer", "") and
                     server_token(description) != valuesDict.get("discoveredServer", ""))):
                errors = indigo.Dict()
                errors["discoveredChannel"] = (
                    "Select an available channel for the chosen Phidget.")
                errors["showAlertText"] = (
                    "The discovered channel is no longer available or is not compatible.")
                return (False, valuesDict, errors)

            valuesDict["serialNumber"] = str(description.get("serialNumber"))
            valuesDict["channel"] = str(description.get("channel"))
            valuesDict["serverName"] = (description.get("serverName") or
                                        description.get("serverUniqueName") or "")
            is_vint = description.get("deviceClass") == 21
            valuesDict["isVintHub"] = is_vint
            valuesDict["isVintDevice"] = bool(
                is_vint and not description.get("isHubPortDevice"))
            valuesDict["hubPort"] = (
                str(description.get("hubPort")) if is_vint else "")

        if typeId == "lcd":
            errors = indigo.Dict()
            try:
                screen_size = int(valuesDict.get("lcdScreenSize", "1"))
                if screen_size < 1 or screen_size > 12:
                    raise ValueError
            except (TypeError, ValueError):
                errors["lcdScreenSize"] = "Select a valid LCD screen size."
                screen_size = 1

            if valuesDict.get("lcdProviderKind") == "adapter":
                if valuesDict.get("lcdProfile") == FREENOVE_I2C_PROFILE:
                    for key, default in FREENOVE_I2C_DEFAULTS.items():
                        if key != "lcdI2CAddress":
                            valuesDict[key] = default
                if screen_size not in (5, 8):
                    errors["lcdScreenSize"] = (
                        "Select 2 rows × 16 characters or 4 rows × 20 characters.")
                i2c_address = None
                try:
                    i2c_address = int(str(valuesDict.get(
                        "lcdI2CAddress", "0x27")).strip(), 0)
                    if i2c_address < 0x08 or i2c_address > 0x77:
                        raise ValueError
                    valuesDict["lcdI2CAddress"] = "0x%02X" % i2c_address
                except (TypeError, ValueError):
                    errors["lcdI2CAddress"] = (
                        "Enter a 7-bit I2C address from 0x08 through 0x77.")

                if i2c_address is not None:
                    adapter_id = str(valuesDict.get("lcdAdapterDeviceId", ""))
                    for other in getattr(indigo, "devices", ()):
                        other_props = getattr(other, "pluginProps", {})
                        if (getattr(other, "id", None) == devId or
                                getattr(other, "pluginId", None) != self.pluginId or
                                getattr(other, "deviceTypeId", None) != "lcd" or
                                not getattr(other, "enabled", True) or
                                other_props.get("lcdProviderKind") != "adapter" or
                                str(other_props.get("lcdAdapterDeviceId", "")) != adapter_id):
                            continue
                        try:
                            other_address = int(str(other_props.get(
                                "lcdI2CAddress", "0x27")), 0)
                        except (TypeError, ValueError):
                            continue
                        if other_address == i2c_address:
                            errors["lcdI2CAddress"] = (
                                "That address is already used by '%s' on this adapter." %
                                getattr(other, "name", "another LCD"))
                            break

                    adapter = self.activePhidgets.get(int(adapter_id or 0))
                    probe = getattr(adapter, "i2cAddressResponds", None)
                    if ("lcdI2CAddress" not in errors and probe is not None and
                            getattr(adapter, "_state", None) == "attached"):
                        try:
                            if not probe(i2c_address):
                                errors["lcdI2CAddress"] = (
                                    "No I2C device responded at 0x%02X. Verify the "
                                    "address jumpers and wiring." % i2c_address)
                        except Exception:
                            self.logger.warning(
                                "Unable to verify I2C address 0x%02X during LCD "
                                "configuration", i2c_address, exc_info=True)

                pins = []
                for field in ("lcdI2CRSPin", "lcdI2CRWPin",
                              "lcdI2CEnablePin", "lcdI2CBacklightPin",
                              "lcdI2CD4Pin", "lcdI2CD5Pin",
                              "lcdI2CD6Pin", "lcdI2CD7Pin"):
                    try:
                        pin = int(valuesDict.get(field, ""))
                        if pin < 0 or pin > 7:
                            raise ValueError
                        valuesDict[field] = str(pin)
                        pins.append(pin)
                    except (TypeError, ValueError):
                        errors[field] = "Enter an expander pin number from 0 through 7."
                if len(pins) == 8 and len(set(pins)) != 8:
                    errors["lcdI2CRSPin"] = (
                        "Each LCD signal must use a different expander pin.")

            for field, label in (("lcdBacklight", "backlight"),
                                 ("lcdContrast", "contrast")):
                try:
                    value = float(valuesDict.get(field, ""))
                    if value < 0.0 or value > 1.0:
                        raise ValueError
                except (TypeError, ValueError):
                    errors[field] = (
                        "Enter a %s value from 0.0 to 1.0." % label)

            for field, label in (("lcdInitialX", "X"), ("lcdInitialY", "Y")):
                try:
                    value = int(valuesDict.get(field, "0"))
                    if value < 0:
                        raise ValueError
                    valuesDict[field] = str(value)
                except (TypeError, ValueError):
                    errors[field] = (
                        "Enter a whole-number %s position of zero or greater." % label)

            if (description is not None and
                    str(description.get("deviceSKU") or "").startswith("1204") and
                    screen_size == 1):
                errors["lcdScreenSize"] = (
                    "Select the dimensions of the panel connected to this text LCD adapter.")

            if (description is not None and
                    description.get("channelSubclass") == 80 and screen_size != 1):
                errors["lcdScreenSize"] = (
                    "Use Automatic / graphic LCD for a graphic display.")

            if errors:
                errors["showAlertText"] = "Correct the LCD settings before saving."
                return (False, valuesDict, errors)

        if typeId == "dataAdapter":
            errors = indigo.Dict()
            try:
                voltage = int(valuesDict.get("dataAdapterVoltage", ""))
                if voltage not in (1, 3, 4, 5):
                    raise ValueError
            except (TypeError, ValueError):
                errors["dataAdapterVoltage"] = "Select a supported bus voltage."
            try:
                frequency = int(valuesDict.get("dataAdapterFrequency", ""))
                if frequency not in (1, 2, 3):
                    raise ValueError
            except (TypeError, ValueError):
                errors["dataAdapterFrequency"] = "Select a supported I2C frequency."
            if errors:
                errors["showAlertText"] = (
                    "Correct the I2C adapter settings before saving.")
                return (False, valuesDict, errors)

        address_index = str(valuesDict["serialNumber"])
        variable_name = "p22_" + address_index
        if variable_name in indigo.variables:
            label = str(indigo.variables[variable_name].value)
            if label != "":
                address_index = label

        if bool(valuesDict["isVintHub"]) and not bool(valuesDict["isVintDevice"]):
            valuesDict["address"] = address_index + "|p" + valuesDict["hubPort"]
        elif (not bool(valuesDict["isVintHub"]) and
              not bool(valuesDict["isVintDevice"])):
            prefixes = {
                "digitalInput": "di-",
                "digitalOutput": "do-",
                "voltageRatioInput": "vr-",
                "voltageInput": "av-",
            }
            prefix = prefixes.get(typeId, "p-")
            valuesDict["address"] = (
                address_index + "|" + prefix + valuesDict["channel"])
        elif ("hubPort" in valuesDict and len(valuesDict["hubPort"]) > 0 and
              "channel" in valuesDict and len(valuesDict["channel"]) > 0):
            valuesDict["address"] = (
                address_index + "|p" + valuesDict["hubPort"] +
                "-c" + valuesDict["channel"])
        elif "hubPort" in valuesDict and len(valuesDict["hubPort"]):
            valuesDict["address"] = address_index + "|p" + valuesDict["hubPort"]
        elif "channel" in valuesDict and len(valuesDict["channel"]) > 0:
            valuesDict["address"] = address_index + "|c" + valuesDict["channel"]
        else:
            valuesDict["address"] = address_index

        valuesDict["configurationMigrated"] = False
        if typeId == "lcd" and valuesDict.get("lcdProviderKind") == "adapter":
            valuesDict["address"] = "lcd-i2c-%s-%02x" % (
                valuesDict["lcdAdapterDeviceId"],
                int(valuesDict.get("lcdI2CAddress", "0x27"), 0))
        return (True, valuesDict)

    def getPhidgetTypeMenu(self, filter="", valuesDict=None, typeId="", targetId=0):
        return self.phidgetInfo.getPhidgetTypeMenu(filter.split(","))

    def getDiscoveredDeviceMenu(self, filter="", valuesDict=None,
                                typeId="", targetId=0):
        if self.discoveryInventory is None:
            return [("manual", "Discovery unavailable — use manual settings below")]
        selected_server = (valuesDict.get("discoveredServer", "")
                           if valuesDict is not None else "")
        if not selected_server or selected_server == "manual":
            return [("selectServer", "")]
        choices = self.discoveryInventory.device_choices_for_server(
            typeId, selected_server)
        return [("selectDevice", "Select a Phidget")] + choices

    def getDiscoveredServerMenu(self, filter="", valuesDict=None,
                                typeId="", targetId=0):
        if self.discoveryInventory is None:
            return [("manual", "Discovery unavailable — use manual settings below")]
        return [("manual", "Select a server")] + \
            self.discoveryInventory.server_choices(typeId)

    def getDiscoveredChannelMenu(self, filter="", valuesDict=None,
                                 typeId="", targetId=0):
        selected_device = (valuesDict.get("discoveredDevice", "")
                           if valuesDict is not None else "")
        if (self.discoveryInventory is None or not selected_device or
                selected_device in ("manual", "selectServer", "selectDevice")):
            return [("selectDevice", "")]
        selected_target = (valuesDict.get("discoveredTarget", "")
                           if valuesDict is not None else "")
        if (self.discoveryInventory.is_vint_device(selected_device) and
                selected_target in ("", "selectPort", "selectTarget")):
            return [("selectTarget", "")]
        choices = self.discoveryInventory.channel_choices(
            typeId, selected_device, selected_target)
        return [("selectChannel", "Select a channel")] + choices

    def getDiscoveredPortMenu(self, filter="", valuesDict=None,
                              typeId="", targetId=0):
        selected_device = (valuesDict.get("discoveredDevice", "")
                           if valuesDict is not None else "")
        if (self.discoveryInventory is None or
                not self.discoveryInventory.is_vint_device(selected_device)):
            return [("selectDevice", "")]
        return [("selectPort", "Select a port")] + \
            self.discoveryInventory.port_choices(typeId, selected_device)

    def getDiscoveredTargetMenu(self, filter="", valuesDict=None,
                                typeId="", targetId=0):
        selected_port = (valuesDict.get("discoveredPort", "")
                         if valuesDict is not None else "")
        if (self.discoveryInventory is None or
                selected_port in ("", "selectDevice", "selectPort")):
            return [("selectPort", "")]
        return [("selectTarget", "Select a device or function")] + \
            self.discoveryInventory.target_choices(typeId, selected_port)

    def menuChanged(self, valuesDict, typeId, devId):
        """Refresh dependent menus and auto-select every unambiguous level."""
        inventory = self.discoveryInventory
        if inventory is None:
            valuesDict["compatibleModelFound"] = False
            return valuesDict

        valid_servers = inventory.server_choices(typeId)
        valuesDict["compatibleModelFound"] = bool(valid_servers)
        selected_server = valuesDict.get("discoveredServer", "")
        if (selected_server not in [choice[0] for choice in valid_servers] and
                len(valid_servers) == 1):
            selected_server = valid_servers[0][0]
            valuesDict["discoveredServer"] = selected_server
        server_selected = selected_server in [choice[0] for choice in valid_servers]
        valuesDict["serverSelected"] = server_selected

        selected_device = valuesDict.get("discoveredDevice", "")
        valid_devices = (inventory.device_choices_for_server(typeId, selected_server)
                         if server_selected else [])
        if (selected_device not in [choice[0] for choice in valid_devices] and
                len(valid_devices) == 1):
            selected_device = valid_devices[0][0]
            valuesDict["discoveredDevice"] = selected_device
        device_selected = selected_device in [choice[0] for choice in valid_devices]
        valuesDict["deviceSelected"] = device_selected

        vint_selected = bool(device_selected and
                             inventory.is_vint_device(selected_device))
        valuesDict["vintSelected"] = vint_selected
        selected_description = (inventory.resolve_device(selected_device)
                                if device_selected else None)
        if selected_description is not None and not vint_selected:
            valuesDict["serialNumber"] = str(
                selected_description.get("serialNumber"))
            valuesDict["serverName"] = (
                selected_description.get("serverName") or
                selected_description.get("serverUniqueName") or "")
            valuesDict["isVintHub"] = False
            valuesDict["isVintDevice"] = False
            valuesDict["hubPort"] = ""

        selected_port = valuesDict.get("discoveredPort", "")
        valid_ports = (inventory.port_choices(typeId, selected_device)
                       if vint_selected else [])
        if (selected_port not in [choice[0] for choice in valid_ports] and
                len(valid_ports) == 1):
            selected_port = valid_ports[0][0]
            valuesDict["discoveredPort"] = selected_port
        port_selected = selected_port in [choice[0] for choice in valid_ports]
        valuesDict["portSelected"] = port_selected

        selected_target = valuesDict.get("discoveredTarget", "")
        valid_targets = (inventory.target_choices(typeId, selected_port)
                         if port_selected else [])
        if (selected_target not in [choice[0] for choice in valid_targets] and
                len(valid_targets) == 1):
            selected_target = valid_targets[0][0]
            valuesDict["discoveredTarget"] = selected_target
        target_selected = selected_target in [choice[0] for choice in valid_targets]
        valuesDict["targetSelected"] = target_selected
        channel_parent_selected = bool(
            device_selected and (not vint_selected or target_selected))
        valuesDict["channelParentSelected"] = channel_parent_selected

        compatible_channels = (inventory.channel_choices(
            typeId, selected_device, selected_target if vint_selected else None)
            if channel_parent_selected else [])
        valuesDict["channelChoiceRequired"] = len(compatible_channels) > 1
        if len(compatible_channels) == 1:
            valuesDict["discoveredChannel"] = compatible_channels[0][0]
        elif valuesDict.get("discoveredChannel", "") not in [
                choice[0] for choice in compatible_channels]:
            valuesDict["discoveredChannel"] = "selectChannel"

        selected_channel = valuesDict.get("discoveredChannel", "")
        description = (inventory.resolve_channel(selected_channel)
                       if device_selected else None)
        resolved_selection = bool(
            description is not None and
            device_token(description) == selected_device and
            (not vint_selected or target_token(description) == selected_target))
        valuesDict["derivedFieldsEnabled"] = not resolved_selection
        if resolved_selection:
            valuesDict["serialNumber"] = str(description.get("serialNumber"))
            valuesDict["channel"] = str(description.get("channel"))
            valuesDict["serverName"] = (description.get("serverName") or
                                        description.get("serverUniqueName") or "")
            is_vint = description.get("deviceClass") == 21
            valuesDict["isVintHub"] = is_vint
            valuesDict["isVintDevice"] = bool(
                is_vint and not description.get("isHubPortDevice"))
            valuesDict["hubPort"] = (
                str(description.get("hubPort")) if is_vint else "")
        return valuesDict

    def logDiscoveryInventory(self):
        if self.discoveryInventory is None:
            self.logger.warning("Phidget discovery inventory is unavailable")
            return
        channels = self.discoveryInventory.snapshot()
        self.logger.info("Discovered Phidget inventory: %d channel(s)", len(channels))
        for channel in channels:
            self.logger.info("  %s", format_channel(channel))

    def printPhidgetsNetworkDiagram(self):
        if self.discoveryInventory is None:
            self.logger.warning("Phidget discovery inventory is unavailable")
            return
        for line in format_network_diagram(self.discoveryInventory.snapshot()):
            self.logger.info("%s", line)

    def getAttachCapableList(self, filter="", valuesDict=None,
                             typeId="", targetId=0):
        result = []
        for device in indigo.devices:
            if device.pluginId == "com.yikes.eric.phidgets-indigo":
                result.append((device.id, device.name))
        return result
