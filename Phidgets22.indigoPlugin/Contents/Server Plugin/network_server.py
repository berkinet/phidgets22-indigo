# -*- coding: utf-8 -*-

"""Indigo representation of a discovered Phidget Network Server."""

import datetime
import socket
import threading
import time

import indigo

from phidget import update_indigo_state

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
        self._pending_detached_at = None
        self._ever_attached = False
        self._reconnect_count = 0
        self._detach_timer = None
        self._detach_generation = 0
        self._unavailable_timer = None
        self._unavailable_generation = 0
        self._unavailable_announced = False
        self._server_endpoint = None
        self._server_record = None
        self._liveness_timer = None
        self._liveness_generation = 0
        self._liveness_failures = 0
        self._liveness_interval = 5.0
        self._liveness_failure_limit = 2
        self._initial_unavailable_timeout = max(
            30, int(indigo_plugin.pluginPrefs.get("attachTimeout", "30")))
        self._reminder_interval = max(
            1, int(indigo_plugin.pluginPrefs.get(
                "detachedReminderInterval", "3600")))

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
        self._cancel_unavailable_timer()
        self._cancel_liveness_timer()
        self.indigo_plugin.unregisterNetworkServerDevice(self)
        with self._lock:
            self._state = "stopped"

    def serverAvailable(self, server):
        self._cancel_detach_timer()
        self._cancel_unavailable_timer()
        with self._lock:
            was_attached = self._state == "attached"
            outage_seconds = 0.0
            if self._detached_at is not None:
                outage_seconds = max(0.0, time.monotonic() - self._detached_at)
            if not was_attached and self._ever_attached:
                self._reconnect_count += 1
            self._state = "attached"
            self._detached_at = None
            self._pending_detached_at = None
            first_attachment = not self._ever_attached
            self._ever_attached = True
            reconnect_count = self._reconnect_count
            unavailable_announced = self._unavailable_announced
            self._unavailable_announced = False
            address = str(server.addr or server.host or "").strip()
            port = int(server.port or 0)
            self._server_endpoint = (address, port) if address and port else None
            self._server_record = server
            self._liveness_failures = 0

        values = {
            "onOffState": True,
            "availability": "Online",
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
        self.indigoDevice.updateStateImageOnServer(
            indigo.kStateImageSel.SensorOn)
        if not was_attached:
            if not first_attachment:
                self.indigo_plugin.triggerEvent(self, "deviceAttached")
            log = (self.logger.debug if first_attachment and
                   not unavailable_announced else self.logger.info)
            log("Phidget network server '%s' %s%s", self.serverName,
                "available" if first_attachment and not unavailable_announced
                else "recovered",
                "" if first_attachment and not unavailable_announced
                else " after %.1f seconds" % outage_seconds)
        self._schedule_liveness_check()

    def serverInitiallyUnavailable(self):
        """Begin monitoring a configured server absent during plugin startup."""
        with self._lock:
            self._state = "detached"
            self._detached_at = time.monotonic()
            self._unavailable_announced = False
        self._update_states({
            "onOffState": False,
            "availability": "Offline",
            "serverName": self.serverName,
            "reconnectCount": 0,
        })
        try:
            self.indigoDevice.setErrorStateOnServer("Offline")
        except Exception:
            pass
        self.indigoDevice.updateStateImageOnServer(
            indigo.kStateImageSel.Error)
        self._schedule_unavailable_timer(self._initial_unavailable_timeout)

    def serverUnavailable(self):
        with self._lock:
            if self._state != "attached":
                return
            self._pending_detached_at = time.monotonic()
            self._detach_generation += 1
            generation = self._detach_generation
            timer = threading.Timer(
                2.0, self._confirmUnavailable, args=(generation,))
            timer.daemon = True
            self._detach_timer = timer
        timer.start()

    def _cancel_liveness_timer(self):
        with self._lock:
            self._liveness_generation += 1
            timer = self._liveness_timer
            self._liveness_timer = None
        if timer is not None:
            timer.cancel()

    def _schedule_liveness_check(self):
        self._cancel_liveness_timer()
        with self._lock:
            if self._state not in ("attached", "detached") or self._server_endpoint is None:
                return
            generation = self._liveness_generation
            timer = threading.Timer(
                self._liveness_interval, self._check_liveness,
                args=(generation,))
            timer.daemon = True
            self._liveness_timer = timer
        timer.start()

    def _check_liveness(self, generation):
        """Detect a hard network loss when SDK removal discovery goes stale."""
        with self._lock:
            if (generation != self._liveness_generation or
                    self._state not in ("attached", "detached") or
                    self._server_endpoint is None):
                return
            self._liveness_timer = None
            endpoint = self._server_endpoint
            state = self._state

        reachable = False
        try:
            connection = socket.create_connection(endpoint, timeout=2.0)
            connection.close()
            reachable = True
        except Exception as error:
            self.logger.debug(
                "Phidget network server '%s' reachability check failed: %s",
                self.serverName, error)

        with self._lock:
            if (generation != self._liveness_generation or
                    self._state not in ("attached", "detached")):
                return
            state = self._state
            if reachable:
                self._liveness_failures = 0
            else:
                self._liveness_failures += 1
            failures = self._liveness_failures

        if state == "detached":
            channels_seen = getattr(
                self.indigo_plugin, "networkServerHasChannels",
                lambda server_name: False)(self.serverName)
            if reachable and channels_seen and self._server_record is not None:
                self.serverAvailable(self._server_record)
                return
            self._schedule_liveness_check()
            return

        if failures >= self._liveness_failure_limit:
            self.logger.debug(
                "Phidget network server '%s' failed %d consecutive "
                "reachability checks", self.serverName, failures)
            self.serverUnavailable()
            return
        self._schedule_liveness_check()

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
            self._detached_at = self._pending_detached_at or time.monotonic()
            self._pending_detached_at = None
            self._liveness_failures = 0
        self._cancel_liveness_timer()
        self._update_states({
            "onOffState": False,
            "availability": "Offline",
            "lastDetached": _timestamp(),
            "lastOutageSeconds": 0.0,
        })
        try:
            self.indigoDevice.setErrorStateOnServer("Offline")
        except Exception:
            pass
        self.indigoDevice.updateStateImageOnServer(
            indigo.kStateImageSel.Error)
        self.indigo_plugin.triggerEvent(self, "deviceDetached")
        self.logger.warning(
            "Phidget network server '%s' unavailable; awaiting rediscovery",
            self.serverName)
        self._schedule_unavailable_timer(self._initial_unavailable_timeout)
        self._schedule_liveness_check()

    def _cancel_unavailable_timer(self):
        with self._lock:
            self._unavailable_generation += 1
            timer = self._unavailable_timer
            self._unavailable_timer = None
        if timer is not None:
            timer.cancel()

    def _schedule_unavailable_timer(self, delay):
        self._cancel_unavailable_timer()
        with self._lock:
            if self._state != "detached":
                return
            generation = self._unavailable_generation
            timer = threading.Timer(
                delay, self._unavailableReminder, args=(generation,))
            timer.daemon = True
            self._unavailable_timer = timer
        timer.start()

    def _unavailableReminder(self, generation):
        with self._lock:
            if (generation != self._unavailable_generation or
                    self._state != "detached"):
                return
            self._unavailable_timer = None
            unavailable_for = max(
                0.0, time.monotonic() - self._detached_at)
            self._unavailable_announced = True
        self.logger.error(
            "Phidget network server '%s' remains unavailable after %.1f "
            "seconds; awaiting rediscovery",
            self.serverName, unavailable_for)
        self._schedule_unavailable_timer(self._reminder_interval)

    def _update_states(self, values):
        for key, value in values.items():
            update_indigo_state(self, key, value)

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
            ("string", "serverVersion", "Server protocol version"),
            ("string", "serverVersionStatus", "Version collection status"),
            ("string", "lastVersionCheck", "Last version check"),
            ("string", "versionCheckError", "Version check error"),
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
        return "availability"
