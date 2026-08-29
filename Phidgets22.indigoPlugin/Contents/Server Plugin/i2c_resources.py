# -*- coding: utf-8 -*-

"""Shared ownership rules for logical devices on an Indigo I2C adapter."""

from config_util import saved_bool


def assignment(device):
    props = getattr(device, "pluginProps", {})
    device_type = getattr(device, "deviceTypeId", None)
    if device_type == "sgp41":
        return props.get("sgpAdapterDeviceId"), 0x59
    if device_type == "bme280":
        return props.get("bmeAdapterDeviceId"), props.get("bmeI2CAddress", "0x76")
    if device_type == "lcd" and props.get("lcdProviderKind") == "adapter":
        return props.get("lcdAdapterDeviceId"), props.get("lcdI2CAddress", "0x27")
    return None


def find_address_owner(devices, plugin_id, adapter_id, address,
                       excluding_device_id=0):
    """Return any configured owner, including one currently disabled."""
    for device in devices:
        if (getattr(device, "id", None) == excluding_device_id or
                getattr(device, "pluginId", None) != plugin_id):
            continue
        resource = assignment(device)
        if resource is None:
            continue
        other_adapter, other_address = resource
        try:
            same_resource = (
                str(other_adapter) == str(adapter_id) and
                int(str(other_address), 0) == int(address))
        except (TypeError, ValueError):
            same_resource = False
        if same_resource:
            return device
    return None


def native_channel_key(props, device_type):
    try:
        return (
            str(device_type or ""),
            str(props.get("serverName") or ""),
            int(props.get("serialNumber")),
            int(props.get("hubPort", -1) or -1),
            int(props.get("channel", -1) or -1),
            saved_bool(props.get("isVintHub", False)),
            saved_bool(props.get("isVintDevice", False)),
        )
    except (TypeError, ValueError):
        return None


def find_native_channel_owner(devices, plugin_id, props, device_type,
                              excluding_device_id=0):
    key = native_channel_key(props, device_type)
    if key is None:
        return None
    for device in devices:
        if (getattr(device, "id", None) == excluding_device_id or
                getattr(device, "pluginId", None) != plugin_id or
                getattr(device, "deviceTypeId", None) in
                ("adapterGPIOInput", "adapterGPIOOutput",
                 "bme280", "sgp41")):
            continue
        if assignment(device) is not None:
            continue
        if native_channel_key(
                getattr(device, "pluginProps", {}),
                getattr(device, "deviceTypeId", None)) == key:
            return device
    return None
