# -*- coding: utf-8 -*-

"""Read-only inventory of channels observed by a Phidget Manager."""

import base64
import json
import threading

from Phidget22.Devices.Manager import Manager


CHANNEL_CLASSES_BY_DEVICE_TYPE = {
    "voltageInput": "PhidgetVoltageInput",
    "voltageRatioInput": "PhidgetVoltageRatioInput",
    "digitalInput": "PhidgetDigitalInput",
    "digitalOutput": "PhidgetDigitalOutput",
    "temperatureSensor": "PhidgetTemperatureSensor",
    "humiditySensor": "PhidgetHumiditySensor",
    "frequencyCounter": "PhidgetFrequencyCounter",
    "lcd": "PhidgetLCD",
}


def _read(channel, method_name, default=None):
    """Read optional channel metadata without disrupting discovery."""
    try:
        return getattr(channel, method_name)()
    except Exception:
        return default


def describe_channel(channel):
    """Return the stable, serializable metadata used by the inventory."""
    is_remote = bool(_read(channel, "getIsRemote", False))
    description = {
        "serverName": None,
        "serverUniqueName": None,
        "serverHostname": None,
        "serverPeerName": None,
        "isRemote": is_remote,
        "serialNumber": _read(channel, "getDeviceSerialNumber"),
        "deviceLabel": _read(channel, "getDeviceLabel"),
        "deviceName": _read(channel, "getDeviceName"),
        "deviceSKU": _read(channel, "getDeviceSKU"),
        "deviceClass": _read(channel, "getDeviceClass"),
        "deviceClassName": _read(channel, "getDeviceClassName"),
        "channel": _read(channel, "getChannel"),
        "channelClass": _read(channel, "getChannelClass"),
        "channelClassName": _read(channel, "getChannelClassName"),
        "channelName": _read(channel, "getChannelName"),
        "channelSubclass": _read(channel, "getChannelSubclass"),
        "hubPort": _read(channel, "getHubPort"),
        "isHubPortDevice": bool(_read(channel, "getIsHubPortDevice", False)),
    }

    if is_remote:
        description.update({
            "serverName": _read(channel, "getServerName"),
            "serverUniqueName": _read(channel, "getServerUniqueName"),
            "serverHostname": _read(channel, "getServerHostname"),
            "serverPeerName": _read(channel, "getServerPeerName"),
        })

    return description


def channel_key(description):
    """Build an identity key from addressing fields, including the server."""
    return (
        description.get("serverUniqueName") or description.get("serverName"),
        description.get("serialNumber"),
        description.get("hubPort"),
        description.get("isHubPortDevice"),
        description.get("channel"),
        description.get("channelClass"),
    )


def channel_sort_key(description):
    """Provide deterministic ordering without comparing None to strings."""
    return tuple(str(value) if value is not None else "" for value in channel_key(description))


def device_key(description):
    """Identify a top-level physical Phidget or the parent of VINT ports."""
    if description.get("deviceClass") == 21:
        return (
            description.get("serverUniqueName") or description.get("serverName"),
            description.get("serialNumber"),
            "VINT_HUB",
        )
    return (
        description.get("serverUniqueName") or description.get("serverName"),
        description.get("serialNumber"),
        description.get("deviceClass"),
        description.get("deviceSKU"),
    )


def port_key(description):
    return device_key(description) + (description.get("hubPort"),)


def target_key(description):
    if description.get("isHubPortDevice"):
        return port_key(description) + ("function", description.get("channelClassName"))
    return port_key(description) + (
        "device", description.get("deviceSKU"), description.get("deviceName"))


def server_key(description):
    return (description.get("serverUniqueName") or description.get("serverName"),)


def _token(kind, key):
    payload = json.dumps([kind, list(key)], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _untoken(token, expected_kind):
    try:
        raw = str(token)
        raw += "=" * (-len(raw) % 4)
        kind, key = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
        return tuple(key) if kind == expected_kind else None
    except Exception:
        return None


def device_token(description):
    return _token("device", device_key(description))


def server_token(description):
    return _token("server", server_key(description))


def port_token(description):
    return _token("port", port_key(description))


def target_token(description):
    return _token("target", target_key(description))


def channel_token(description):
    return _token("channel", channel_key(description))


def _saved_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def format_phidget_model(description):
    sku = description.get("deviceSKU")
    name = description.get("deviceName") or sku or "Unknown device"
    if name.startswith("Phidget"):
        name = name[len("Phidget"):]
    if sku and sku not in name:
        name = "%s (%s)" % (name, sku)
    return name


def format_device_choice(description):
    if description.get("deviceClass") == 21:
        return "VINT Hub"
    return format_phidget_model(description)


def format_target_choice(description):
    if description.get("isHubPortDevice"):
        name = description.get("channelName") or description.get("channelClassName") or "Hub-port function"
        return name.replace("Phidget", "").strip()
    endpoint = description.get("channelName") or description.get("channelClassName") or "Channel"
    endpoint = endpoint.replace("Phidget", "").strip()
    sku = description.get("deviceSKU")
    return "%s (%s)" % (endpoint, sku) if sku else endpoint


def format_channel_choice(description):
    name = description.get("channelClassName") or description.get("channelName") or "Channel"
    if description.get("isHubPortDevice"):
        return "Channel %s" % description.get("channel")
    return "%s %s — %s" % (name, description.get("channel"), description.get("channelName") or name)


def format_channel(description):
    """Format one inventory row for the Indigo log."""
    server = description.get("serverName") or description.get("serverUniqueName") or "Local"
    device = description.get("deviceSKU") or description.get("deviceName") or "Unknown device"
    channel = description.get("channelClassName") or description.get("channelName") or "Unknown channel"
    label = description.get("deviceLabel")
    label_text = " label=%r" % label if label else ""
    return (
        "server=%s device=%s serial=%s hubPort=%s channel=%s class=%s%s"
        % (
            server,
            device,
            description.get("serialNumber"),
            description.get("hubPort"),
            description.get("channel"),
            channel,
            label_text,
        )
    )


def format_network_diagram(channels):
    """Render discovered topology as an indented, log-friendly hierarchy."""
    servers = {}
    for item in sorted((dict(channel) for channel in channels), key=channel_sort_key):
        server = item.get("serverName") or item.get("serverUniqueName") or "Local"
        servers.setdefault(server, {}).setdefault(device_key(item), []).append(item)

    lines = ["Phidgets network diagram:"]
    if not servers:
        return lines + ["  (no Phidget channels discovered)"]

    for server in sorted(servers, key=lambda value: value.lower()):
        lines.append("Server: %s" % server)
        devices = servers[server]
        for key, items in sorted(devices.items(), key=lambda pair: channel_sort_key(pair[1][0])):
            sample = items[0]
            serial = sample.get("serialNumber")
            if sample.get("deviceClass") == 21:
                lines.append("  Device: VINT Hub — serial %s" % serial)
                ports = {}
                for item in items:
                    ports.setdefault(item.get("hubPort"), []).append(item)
                for port, port_items in sorted(ports.items(), key=lambda pair: pair[0]):
                    lines.append("    Port %s" % port)
                    endpoints = {}
                    for item in port_items:
                        endpoints[(format_target_choice(item), item.get("channel"))] = item
                    for (name, channel), item in sorted(endpoints.items()):
                        lines.append("      %s — channel %s" % (name, channel))
            else:
                lines.append("  Device: %s — serial %s" %
                             (format_phidget_model(sample), serial))
                for item in sorted(items, key=channel_sort_key):
                    lines.append("    %s — channel %s" %
                                 (item.get("channelName") or item.get("channelClassName"),
                                  item.get("channel")))
    return lines


class DiscoveryInventory(object):
    """Observe available channels without opening or configuring them."""

    def __init__(self, logger, manager_factory=Manager):
        self.logger = logger
        self.manager = manager_factory()
        self.channels = {}
        self.lock = threading.RLock()
        self.started = False

    def start(self):
        if self.started:
            return
        self.manager.setOnAttachHandler(self._on_attach)
        self.manager.setOnDetachHandler(self._on_detach)
        self.manager.open()
        self.started = True
        self.logger.debug("Started read-only Phidget discovery inventory")

    def stop(self):
        if not self.started:
            return
        self.manager.close()
        self.started = False
        with self.lock:
            self.channels.clear()
        self.logger.debug("Stopped read-only Phidget discovery inventory")

    def snapshot(self):
        with self.lock:
            return sorted((dict(item) for item in self.channels.values()), key=channel_sort_key)

    def compatible_channels(self, device_type):
        expected = CHANNEL_CLASSES_BY_DEVICE_TYPE.get(device_type)
        if expected is None:
            return []
        return [item for item in self.snapshot() if item.get("channelClassName") == expected]

    def selection_for_saved_address(self, device_type, saved):
        """Reverse-resolve one legacy address into the discovery hierarchy.

        Return no selection unless exactly one live channel matches. This is
        intentionally conservative because it is used while opening existing
        device dialogs and must never silently redirect a device.
        """
        try:
            serial_number = int(saved.get("serialNumber"))
        except (TypeError, ValueError):
            return None

        candidates = [item for item in self.compatible_channels(device_type)
                      if item.get("serialNumber") == serial_number]

        saved_server = str(saved.get("serverName") or "").strip()
        if saved_server:
            candidates = [item for item in candidates if saved_server in (
                str(item.get("serverName") or ""),
                str(item.get("serverUniqueName") or ""),
                str(item.get("serverHostname") or ""),
            )]

        saved_channel = saved.get("channel")
        if saved_channel not in (None, ""):
            try:
                channel_number = int(saved_channel)
            except (TypeError, ValueError):
                return None
            candidates = [item for item in candidates
                          if item.get("channel") == channel_number]

        is_vint_hub = _saved_bool(saved.get("isVintHub", False))
        is_vint_device = _saved_bool(saved.get("isVintDevice", False))
        if is_vint_hub:
            try:
                hub_port = int(saved.get("hubPort"))
            except (TypeError, ValueError):
                return None
            candidates = [item for item in candidates
                          if item.get("deviceClass") == 21 and
                          item.get("hubPort") == hub_port and
                          bool(not item.get("isHubPortDevice")) == is_vint_device]
        else:
            candidates = [item for item in candidates if item.get("deviceClass") != 21]

        if len(candidates) != 1:
            return None

        item = candidates[0]
        selection = {
            "discoveredServer": server_token(item),
            "discoveredDevice": device_token(item),
            "discoveredChannel": channel_token(item),
        }
        if item.get("deviceClass") == 21:
            selection.update({
                "discoveredPort": port_token(item),
                "discoveredTarget": target_token(item),
            })
        return selection

    def device_choices(self, device_type):
        return self.device_choices_for_server(device_type, None)

    def server_choices(self, device_type):
        servers = {}
        for item in self.compatible_channels(device_type):
            servers[server_key(item)] = item
        choices = []
        for item in servers.values():
            name = item.get("serverName") or item.get("serverUniqueName") or "Local"
            choices.append((server_token(item), name))
        return sorted(choices, key=lambda choice: choice[1].lower())

    def device_choices_for_server(self, device_type, selected_server):
        selected_key = _untoken(selected_server, "server") if selected_server else None
        devices = {}
        for item in self.compatible_channels(device_type):
            if selected_key is not None and server_key(item) != selected_key:
                continue
            devices[device_key(item)] = item
        return [(device_token(item), format_device_choice(item))
                for item in sorted(devices.values(), key=lambda value: format_device_choice(value).lower())]

    def is_vint_device(self, selected_device):
        selected_key = _untoken(selected_device, "device")
        return bool(selected_key and len(selected_key) == 3 and selected_key[-1] == "VINT_HUB")

    def port_choices(self, device_type, selected_device):
        selected_key = _untoken(selected_device, "device")
        if selected_key is None or not self.is_vint_device(selected_device):
            return []
        all_items = [item for item in self.snapshot() if device_key(item) == selected_key]
        ports = {}
        for item in all_items:
            ports[port_key(item)] = item
        return [(port_token(item), "Port %s" % item.get("hubPort"))
                for item in sorted(ports.values(), key=lambda value: value.get("hubPort"))]

    def target_choices(self, device_type, selected_port):
        selected_key = _untoken(selected_port, "port")
        if selected_key is None:
            return []
        all_items = [item for item in self.snapshot() if port_key(item) == selected_key]
        actual_items = [item for item in all_items if not item.get("isHubPortDevice")]
        candidates = actual_items if actual_items else [item for item in all_items if item.get("isHubPortDevice")]
        candidates = [item for item in candidates
                      if item.get("channelClassName") == CHANNEL_CLASSES_BY_DEVICE_TYPE.get(device_type)]
        targets = {}
        for item in candidates:
            targets[target_key(item)] = item
        return [(target_token(item), format_target_choice(item))
                for item in sorted(targets.values(), key=lambda value: format_target_choice(value).lower())]

    def channel_choices(self, device_type, selected_device, selected_target=None):
        device_selection = _untoken(selected_device, "device")
        target_selection = _untoken(selected_target, "target") if selected_target else None
        if device_selection is None:
            return []
        items = self.compatible_channels(device_type)
        if target_selection is not None:
            items = [item for item in items if target_key(item) == target_selection]
        else:
            items = [item for item in items if device_key(item) == device_selection]
        return [(channel_token(item), format_channel_choice(item)) for item in items]

    def resolve_channel(self, token):
        selected_key = _untoken(token, "channel")
        if selected_key is None:
            return None
        for item in self.snapshot():
            if channel_key(item) == selected_key:
                return item
        return None

    def resolve_device(self, token):
        selected_key = _untoken(token, "device")
        if selected_key is None:
            return None
        for item in self.snapshot():
            if device_key(item) == selected_key:
                return item
        return None

    def _on_attach(self, manager, channel):
        try:
            description = describe_channel(channel)
            with self.lock:
                self.channels[channel_key(description)] = description
            self.logger.debug("Discovery observed attach: %s", format_channel(description))
        except Exception:
            self.logger.exception("Unable to record discovered Phidget channel")

    def _on_detach(self, manager, channel):
        try:
            description = describe_channel(channel)
            with self.lock:
                self.channels.pop(channel_key(description), None)
            self.logger.debug("Discovery observed detach: %s", format_channel(description))
        except Exception:
            self.logger.exception("Unable to remove detached Phidget channel from discovery inventory")
