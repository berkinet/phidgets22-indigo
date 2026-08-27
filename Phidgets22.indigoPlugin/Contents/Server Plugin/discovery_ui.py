# -*- coding: utf-8 -*-

"""Indigo configuration callbacks backed by the live discovery inventory."""

import indigo

from discovery import (CHANNEL_CLASSES_BY_DEVICE_TYPE, device_token,
                       channel_token, format_channel, format_network_diagram,
                       port_token, server_token, target_token)
from display_providers import available_display_providers


class DiscoveryUiMixin(object):
    def getAvailableDisplayMenu(self, filter="", valuesDict=None,
                                typeId="", targetId=0):
        """Supply one future LCD selector without exposing its transport."""
        providers = available_display_providers(self)
        return [("selectDisplay", "Select a display")] + [
            (provider["id"], provider["name"]) for provider in providers]

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
        valuesDict["lcdProfile"] = "freenove-lcd2004-pcf8574t"
        valuesDict["lcdScreenSize"] = "8"
        valuesDict["discoveredChannel"] = "manual"
        valuesDict["serialNumber"] = str(adapter_props.get("serialNumber", ""))
        valuesDict["channel"] = str(adapter_props.get("channel", "0"))
        valuesDict["serverName"] = str(adapter_props.get("serverName", ""))
        valuesDict["observedConnection"] = "%s→Freenove LCD2004" % adapter_device.name
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
            valuesDict["address"] = "lcd-i2c-%s-27" % valuesDict["lcdAdapterDeviceId"]
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
