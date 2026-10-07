# -*- coding: utf-8 -*-
"""Text companion to a device's selected numeric display state."""
import math


def add_signed_value_state(plugin, owner, states):
    owner._signedValueSource = None
    if getattr(owner, "NUMERIC_DISPLAY", False) is not True:
        return
    source = owner.getDeviceDisplayStateId()
    if (source == getattr(owner, "customState", None) and
            getattr(owner, "customOutputType", "number") != "number"):
        return
    if source == "signedValue":
        plugin.logger.error("Device '%s' uses reserved custom state signedValue; rename that custom state to enable the signed display.",
                            owner.indigoDevice.name)
        return
    states.append(plugin.getDeviceStateDictForStringType(
        "signedValue", "Signed display value (+/-)", "signedValue"))
    owner._signedValueSource = source


def format_signed_value(value, decimal_places=-1):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    places = int(decimal_places)
    if places < 0:
        # Preserve the supplied number's precision; normalize negative zero.
        return ("+" + str(abs(value))) if value == 0 else format(value, "+")
    result = format(value, "+.%df" % places)
    if result.startswith("-") and float(result) == 0:
        result = "+" + result[1:]
    return result


def publish_signed_value(owner, value, arguments):
    try:
        places = arguments.get("decimalPlaces", getattr(owner, "decimalPlaces", -1))
        text = format_signed_value(value, places)
        owner.indigoDevice.updateStateOnServer(
            "signedValue", value=text,
            triggerEvents=arguments.get("triggerEvents", False))
    except Exception as error:
        owner.logger.error("Signed display update failed for '%s': %s",
                           owner.indigoDevice.name, str(error).replace("\n", " "))


def initialize_signed_value(owner):
    """Seed the companion after schema installation, before live callbacks start."""
    source = getattr(owner, "_signedValueSource", None)
    if not isinstance(source, str) or not source:
        return
    try:
        value = owner.indigoDevice.states.get(source)
        publish_signed_value(owner, value, {"triggerEvents": False})
    except Exception as error:
        owner.logger.error("Signed display initialization failed for '%s': %s",
                           owner.indigoDevice.name, str(error).replace("\n", " "))
