# -*- coding: utf-8 -*-

"""Consistent Indigo state publication for every runtime device."""

import traceback


def update_indigo_state(owner, key, value, **kwargs):
    """Publish one state while treating its first value as a silent baseline."""
    initialized = getattr(owner, "_initializedIndigoStates", None)
    if initialized is None:
        initialized = set()
        owner._initializedIndigoStates = initialized
    if "triggerEvents" not in kwargs:
        kwargs["triggerEvents"] = key in initialized
    owner.indigoDevice.updateStateOnServer(key, value=value, **kwargs)
    initialized.add(key)


def update_indigo_states(owner, values, logger=None, ui_values=None):
    """Publish independent states so one stale definition cannot abort a pass."""
    ui_values = ui_values or {}
    for key, value in values.items():
        arguments = {}
        if key in ui_values:
            display = ui_values[key]
            arguments["uiValue"] = display(value) if callable(display) else display
        try:
            update_indigo_state(owner, key, value, **arguments)
        except Exception:
            if logger is not None:
                device = getattr(owner, "indigoDevice", None)
                logger.debug(
                    "Unable to update state %s for device='%s' id=%s:\n%s",
                    key, getattr(device, "name", "unknown"),
                    getattr(device, "id", "unknown"), traceback.format_exc())
