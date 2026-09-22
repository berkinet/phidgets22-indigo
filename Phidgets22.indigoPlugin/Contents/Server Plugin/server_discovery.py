"""Resolve server endpoints from current remote-channel discovery."""

from types import SimpleNamespace
from urllib.parse import urlsplit

from connection_identity import ServerIdentity
from Phidget22.PhidgetServerType import PhidgetServerType


def channel_server_records(inventory):
    if inventory is None:
        return {}
    candidates = {}
    for channel in inventory.snapshot():
        identity = ServerIdentity.from_description(channel)
        if not identity.remote or not identity.name:
            continue
        try:
            endpoint = urlsplit("//" + identity.peer)
            host, port = endpoint.hostname, endpoint.port
        except ValueError:
            continue
        if not host or not port or not 0 < port < 65536:
            continue
        record = SimpleNamespace(
            name=identity.name, host=identity.hostname, addr=host, port=port,
            type=PhidgetServerType.PHIDGETSERVER_DEVICEREMOTE,
            stype="", flags=None)
        # Do not guess which server a duplicated name refers to.
        for alias in identity.aliases:
            candidates.setdefault(alias, {})[(host, port)] = record
    return {alias: next(iter(records.values()))
            for alias, records in candidates.items() if len(records) == 1}
