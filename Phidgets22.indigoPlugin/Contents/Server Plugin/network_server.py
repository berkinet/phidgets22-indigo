# -*- coding: utf-8 -*-

"""Indigo representation of a discovered Phidget Network Server."""

import datetime
import threading
import time

from Phidget22.Net import Net
from Phidget22.PhidgetServerType import PhidgetServerType


def _timestamp():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


class NetworkServerDevice(object):
    """Monitor one advertised Phidget server without owning a channel."""

    def __init__(self, indigo_plugin, indigoDevice, serverName, logger):
        self.indigo_plugin = indigo_plugin
        self.indigoDevice = indigoDevice
        self.serverName = str(serverName).strip()
        self.logger = logger
        self._state = "stopped"
        self._lock = threading.RLock()
        self._detached_at = None
        self._ever_attached = False
        self._reconnect_count = 0
        self._detach_timer = None
        self._detach_generation = 0

    def start(self):
        with self._lock:
            self._state = "detached"
        # A server already present in the discovery cache is applied
        # synchronously during registration. Ensure Indigo knows the dynamic
        # states before that first update is attempted.
        self.indigoDevice.stateListOrDisplayStateIdChanged()
        self.indigo_plugin.registerNetworkServerDevice(self)

    def stop(self):
        self._cancel_detach_timer()
        self.indigo_plugin.unregisterNetworkServerDevice(self)
        with self._lock:
            self._state = "stopped"

    def serverAvailable(self, server):
        self._cancel_detach_timer()
        with self._lock:
            was_attached = self._state == "attached"
            outage_seconds = 0.0
            if self._detached_at is not None:
                outage_seconds = max(0.0, time.monotonic() - self._detached_at)
            if not was_attached and self._ever_attached:
                self._reconnect_count += 1
            self._state = "attached"
            self._detached_at = None
            first_attachment = not self._ever_attached
            self._ever_attached = True
            reconnect_count = self._reconnect_count

        values = {
            "onOffState": True,
            "availability": "attached",
            "serverName": server.name or self.serverName,
            "serviceType": server.stype or "",
            "serverType": PhidgetServerType.getName(server.type),
            "address": server.addr or "",
            "host": server.host or "",
            "port": int(server.port or 0),
            "authenticationRequired": bool(server.flags & Net.AUTHREQUIRED),
            "flags": int(server.flags or 0),
            "lastAttached": _timestamp(),
            "lastOutageSeconds": round(outage_seconds, 1),
            "reconnectCount": reconnect_count,
        }
        self._update_states(values)
        try:
            self.indigoDevice.setErrorStateOnServer(None)
        except Exception:
            pass
        if not was_attached:
            self.indigo_plugin.triggerEvent(self, "deviceAttached")
            log = self.logger.debug if first_attachment else self.logger.info
            log("Phidget network server '%s' %s%s", self.serverName,
                "available" if first_attachment else "recovered",
                "" if first_attachment else " after %.1f seconds" % outage_seconds)

    def serverUnavailable(self):
        with self._lock:
            if self._state != "attached":
                return
            self._detach_generation += 1
            generation = self._detach_generation
            timer = threading.Timer(
                2.0, self._confirmUnavailable, args=(generation,))
            timer.daemon = True
            self._detach_timer = timer
        timer.start()

    def _cancel_detach_timer(self):
        with self._lock:
            self._detach_generation += 1
            timer = self._detach_timer
            self._detach_timer = None
        if timer is not None:
            timer.cancel()

    def _confirmUnavailable(self, generation):
        with self._lock:
            if (generation != self._detach_generation or
                    self._state != "attached"):
                return
            self._detach_timer = None
            self._state = "detached"
            self._detached_at = time.monotonic()
        self._update_states({
            "onOffState": False,
            "availability": "detached",
            "lastDetached": _timestamp(),
            "lastOutageSeconds": 0.0,
        })
        try:
            self.indigoDevice.setErrorStateOnServer("Detached")
        except Exception:
            pass
        self.indigo_plugin.triggerEvent(self, "deviceDetached")
        self.logger.warning(
            "Phidget network server '%s' unavailable; awaiting rediscovery",
            self.serverName)

    def _update_states(self, values):
        for key, value in values.items():
            self.indigoDevice.updateStateOnServer(key, value=value)

    def getDeviceStateList(self):
        states = []
        definitions = (
            ("bool", "onOffState", "Available"),
            ("string", "availability", "Availability"),
            ("string", "serverName", "Server name"),
            ("string", "serviceType", "Service type"),
            ("string", "serverType", "Server type"),
            ("string", "address", "Address"),
            ("string", "host", "Host"),
            ("number", "port", "Port"),
            ("bool", "authenticationRequired", "Authentication required"),
            ("number", "flags", "Flags"),
            ("string", "lastAttached", "Last attached"),
            ("string", "lastDetached", "Last detached"),
            ("number", "lastOutageSeconds", "Last outage (seconds)"),
            ("number", "reconnectCount", "Reconnect count"),
        )
        for state_type, state_id, label in definitions:
            if state_type == "bool":
                state = self.indigo_plugin.getDeviceStateDictForBoolOnOffType(
                    state_id, label, state_id)
            elif state_type == "number":
                state = self.indigo_plugin.getDeviceStateDictForNumberType(
                    state_id, label, state_id)
            else:
                state = self.indigo_plugin.getDeviceStateDictForStringType(
                    state_id, label, state_id)
            states.append(state)
        return states

    def getDeviceDisplayStateId(self):
        return "onOffState"
