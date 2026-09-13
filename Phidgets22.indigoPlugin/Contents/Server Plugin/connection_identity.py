# -*- coding: utf-8 -*-

"""Immutable identities for servers, physical devices, ports, and channels."""

from dataclasses import dataclass


def _text(value):
    return str(value or "").strip()


@dataclass(frozen=True)
class ServerIdentity(object):
    remote: bool = False
    configured_name: str = ""
    name: str = ""
    unique_name: str = ""
    hostname: str = ""
    peer: str = ""

    def __post_init__(self):
        object.__setattr__(self, "remote", bool(self.remote))
        for field in ("configured_name", "name", "unique_name",
                      "hostname", "peer"):
            object.__setattr__(self, field, _text(getattr(self, field)))

    @property
    def key(self):
        if not self.remote:
            return "local"
        return (self.unique_name or self.name or self.configured_name or
                self.hostname or self.peer or "local")

    @property
    def discovery_key(self):
        return self.unique_name or self.name or None

    @property
    def display_name(self):
        if not self.remote:
            return "Local USB"
        return (self.name or self.hostname or self.unique_name or
                self.configured_name or "any")

    @property
    def topology_name(self):
        return self.display_name if self.remote else "Local"

    @property
    def aliases(self):
        return frozenset(value for value in (
            self.configured_name, self.name, self.unique_name,
            self.hostname, self.peer) if value)

    def matches(self, name):
        return _text(name) in self.aliases

    @classmethod
    def from_description(cls, description):
        remote = bool(description.get("isRemote", False) or any(
            description.get(key) for key in (
                "serverName", "serverUniqueName", "serverHostname",
                "serverPeerName")))
        return cls(
            remote=remote,
            configured_name=description.get("serverName"),
            name=description.get("serverName"),
            unique_name=description.get("serverUniqueName"),
            hostname=description.get("serverHostname"),
            peer=description.get("serverPeerName"),
        )

    @classmethod
    def from_wrapper(cls, wrapper):
        channel_info = getattr(wrapper, "channelInfo", None)
        net_info = getattr(channel_info, "netInfo", None)
        return cls(
            remote=getattr(net_info, "isRemote", False),
            configured_name=getattr(net_info, "serverName", None),
            name=getattr(wrapper, "runtimeServerName", None),
            unique_name=getattr(wrapper, "runtimeServerUniqueName", None),
            hostname=getattr(wrapper, "runtimeServerHostname", None),
            peer=getattr(wrapper, "runtimeServerPeerName", None),
        )


@dataclass(frozen=True)
class PhysicalDeviceIdentity(object):
    server_key: str
    serial_number: object

    @classmethod
    def from_description(cls, description):
        return cls(ServerIdentity.from_description(description).key,
                   description.get("serialNumber"))

    @classmethod
    def from_wrapper(cls, wrapper):
        return cls(ServerIdentity.from_wrapper(wrapper).key,
                   wrapper.channelInfo.serialNumber)


@dataclass(frozen=True)
class PortIdentity(object):
    physical_device: PhysicalDeviceIdentity
    hub_port: object

    @classmethod
    def from_description(cls, description):
        return cls(PhysicalDeviceIdentity.from_description(description),
                   description.get("hubPort"))

    @classmethod
    def from_wrapper(cls, wrapper):
        return cls(PhysicalDeviceIdentity.from_wrapper(wrapper),
                   wrapper.channelInfo.hubPort)


@dataclass(frozen=True)
class ChannelIdentity(object):
    port: PortIdentity
    hub_port_device: bool
    channel: object
    channel_class: object

    @classmethod
    def from_description(cls, description):
        server = ServerIdentity.from_description(description)
        return cls(
            PortIdentity(
                PhysicalDeviceIdentity(
                    server.discovery_key, description.get("serialNumber")),
                description.get("hubPort")),
            bool(description.get("isHubPortDevice")),
            description.get("channel"),
            description.get("channelClass"),
        )

    @classmethod
    def from_wrapper(cls, wrapper, channel_class=None):
        return cls(
            PortIdentity.from_wrapper(wrapper),
            bool(wrapper.channelInfo.isHubPortDevice),
            wrapper.channelInfo.channel,
            channel_class,
        )

    def discovery_key(self):
        return (
            self.port.physical_device.server_key,
            self.port.physical_device.serial_number,
            self.port.hub_port,
            self.hub_port_device,
            self.channel,
            self.channel_class,
        )


@dataclass(frozen=True)
class ConfiguredChannelIdentity(object):
    """A saved Indigo address before runtime metadata is available."""
    channel: ChannelIdentity
    vint_hub: bool
    vint_device: bool

    @classmethod
    def from_properties(cls, properties, device_type, saved_bool):
        try:
            server_name = _text(properties.get("serverName"))
            vint_hub = saved_bool(properties.get("isVintHub", False))
            vint_device = saved_bool(properties.get("isVintDevice", False))
            physical = PhysicalDeviceIdentity(
                server_name or "local", int(properties.get("serialNumber")))
            port = PortIdentity(
                physical, int(properties.get("hubPort", -1) or -1))
            channel = ChannelIdentity(
                port, bool(vint_hub and not vint_device),
                int(properties.get("channel", -1) or -1),
                _text(device_type))
            return cls(channel, vint_hub, vint_device)
        except (TypeError, ValueError):
            return None


def discovery_device_key(description):
    """Retain discovery hierarchy semantics using canonical server identity."""
    server = ServerIdentity.from_description(description).discovery_key
    serial = description.get("serialNumber")
    if description.get("deviceClass") == 21:
        return (server, serial, "VINT_HUB")
    return (server, serial, description.get("deviceClass"),
            description.get("deviceSKU"))
