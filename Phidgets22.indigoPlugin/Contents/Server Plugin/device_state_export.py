# -*- coding: utf-8 -*-

"""JSON snapshots of configured Indigo devices owned by this plugin."""

import datetime
import json
import os


EXPORT_FILENAME = "Phidgets 22 Device States.json"
SCHEMA_VERSION = 1


def _json_value(value):
    """Convert Indigo container/value types into JSON-safe values."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "items"):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return str(value)


def build_device_state_snapshot(plugin, devices):
    records = []
    for device in devices:
        if getattr(device, "pluginId", None) != plugin.pluginId:
            continue
        records.append({
            "id": int(device.id),
            "name": str(device.name),
            "deviceTypeId": str(device.deviceTypeId),
            "typeName": str(getattr(device, "typeName", "") or ""),
            "enabled": bool(getattr(device, "enabled", True)),
            "address": str(getattr(device, "address", "") or ""),
            "states": _json_value(getattr(device, "states", {})),
        })
    records.sort(key=lambda record: (record["name"].lower(), record["id"]))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"),
        "plugin": {
            "id": str(plugin.pluginId),
            "displayName": str(getattr(plugin, "pluginDisplayName", "") or ""),
            "version": str(getattr(plugin, "pluginVersion", "") or ""),
        },
        "deviceCount": len(records),
        "devices": records,
    }


def default_export_path(plugin):
    log_path = getattr(getattr(plugin, "plugin_file_handler", None),
                       "baseFilename", "")
    if not log_path:
        raise RuntimeError("Plugin log directory is unavailable")
    return os.path.join(os.path.dirname(log_path), EXPORT_FILENAME)


def write_device_state_snapshot(plugin, devices, path=None):
    path = path or default_export_path(plugin)
    snapshot = build_device_state_snapshot(plugin, devices)
    temporary_path = path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as output:
        json.dump(snapshot, output, indent=2, sort_keys=True,
                  ensure_ascii=False)
        output.write("\n")
    os.replace(temporary_path, path)
    return path, snapshot
