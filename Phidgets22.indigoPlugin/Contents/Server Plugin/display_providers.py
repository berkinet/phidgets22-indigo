# -*- coding: utf-8 -*-

"""Build one transport-neutral inventory of displays and display providers."""

import indigo

from discovery import channel_token, format_phidget_model


LCD_FUNCTION = "lcd"


def _native_name(description):
    name = format_phidget_model(description)
    label = description.get("deviceLabel")
    if label:
        name = str(label)
    server = description.get("serverName") or description.get("serverUniqueName")
    return "%s — %s" % (name, server) if server else name


def _adapter_supports_lcd(plugin, device):
    wrapper = plugin.activePhidgets.get(device.id)
    supports = getattr(wrapper, "supportsFunction", None)
    if supports is not None:
        return bool(supports(LCD_FUNCTION))
    # Retained Indigo states allow discovery during a brief adapter outage.
    functions = str(device.states.get("availableFunctions", "")).lower()
    return "lcd" in functions


def available_display_providers(plugin):
    """Return native displays and configured LCD-capable adapters uniformly."""
    providers = []
    inventory = getattr(plugin, "discoveryInventory", None)
    if inventory is not None:
        for description in inventory.compatible_channels("lcd"):
            providers.append({
                "id": "native:%s" % channel_token(description),
                "kind": "native",
                "name": _native_name(description),
                "channel": description,
            })

    for device in getattr(indigo, "devices", ()):
        if (getattr(device, "pluginId", None) != plugin.pluginId or
                getattr(device, "deviceTypeId", None) != "dataAdapter" or
                not getattr(device, "enabled", True) or
                not _adapter_supports_lcd(plugin, device)):
            continue
        providers.append({
            "id": "adapter:%s" % device.id,
            "kind": "adapter",
            "name": device.name,
            "adapterDeviceId": int(device.id),
        })

    return sorted(providers, key=lambda provider: provider["name"].lower())
