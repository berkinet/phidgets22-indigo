# -*- coding: utf-8 -*-

"""Coalesced reporting for channel, physical-device, and server outages."""

import threading
import time

from connection_identity import (PhysicalDeviceIdentity, PortIdentity,
                                 ServerIdentity)


class OutageCoordinator(object):
    COALESCE_SECONDS = 0.3

    def __init__(self, logger, channel_snapshot,
                 timer_factory=threading.Timer, clock=time.monotonic):
        self.logger = logger
        self._channel_snapshot = channel_snapshot
        self._timer_factory = timer_factory
        self._clock = clock
        self._lock = threading.RLock()
        self._batches = {
            "detach": {},
            "recovery": {},
            "startup-contention": {},
            "startup-unavailable": {},
            "startup-open-failure": {},
        }
        self._timers = {}
        self._server_outages = {}
        self._open_failure_last_logged = {}

    def _channels_for_server(self, server_key):
        return [phidget for phidget in self._channel_snapshot()
                if phidget.channelInfo.netInfo.isRemote and
                ServerIdentity.from_wrapper(phidget).key == server_key]

    def _schedule(self, kind, key, callback):
        timer_key = (kind, key)
        token = object()
        timer = self._timer_factory(
            self.COALESCE_SECONDS, callback, args=(key, token))
        timer.daemon = True
        with self._lock:
            old_timer = self._timers.pop(timer_key, None)
            self._timers[timer_key] = (timer, token)
        if old_timer is not None:
            old_timer[0].cancel()
        timer.start()

    def detach_announced(self, phidget):
        server_key = ServerIdentity.from_wrapper(phidget).key
        with self._lock:
            self._batches["detach"].setdefault(server_key, set()).add(phidget)
        self._schedule("detach", server_key, self.flush_detach)

    def startup_contention(self, phidget, detached_for):
        key = PortIdentity.from_wrapper(phidget)
        with self._lock:
            self._batches["startup-contention"].setdefault(
                key, {})[phidget] = detached_for
        self._schedule("startup-contention", key, self.flush_startup_contention)

    def startup_unavailable(self, phidget, detached_for, state):
        key = PhysicalDeviceIdentity.from_wrapper(phidget)
        with self._lock:
            self._batches["startup-unavailable"].setdefault(
                key, {})[phidget] = (detached_for, state)
        self._schedule("startup-unavailable", key, self.flush_startup_unavailable)

    def startup_open_failure(self, phidget, detached_for, message):
        key = PhysicalDeviceIdentity.from_wrapper(phidget)
        with self._lock:
            self._batches["startup-open-failure"].setdefault(
                key, {})[phidget] = (detached_for, str(message))
        self._schedule(
            "startup-open-failure", key, self.flush_startup_open_failure)

    def attach_completed(self, phidget, detached_for):
        server_key = ServerIdentity.from_wrapper(phidget).key
        with self._lock:
            self._batches["recovery"].setdefault(
                server_key, {})[phidget] = detached_for
        self._schedule("recovery", server_key, self.flush_recovery)

    def clear_open_failure(self, physical_key):
        with self._lock:
            self._open_failure_last_logged.pop(physical_key, None)

    def _take_batch(self, kind, key, default, token=None):
        with self._lock:
            current = self._timers.get((kind, key))
            if token is not None and (current is None or current[1] is not token):
                return default
            self._timers.pop((kind, key), None)
            return self._batches[kind].pop(key, default)

    def flush_startup_open_failure(self, key, token=None):
        pending = self._take_batch(
            "startup-open-failure", key, {}, token)
        affected = {
            phidget: details for phidget, details in pending.items()
            if (phidget._state in ("starting", "detached") and
                phidget._startup_error_message)
        }
        if not affected:
            return
        now = self._clock()
        reminder_interval = min(
            phidget.detached_reminder_interval for phidget in affected)
        with self._lock:
            last_logged = self._open_failure_last_logged.get(key)
            if (last_logged is not None and
                    now - last_logged < reminder_interval):
                return
            self._open_failure_last_logged[key] = now
        first = next(iter(affected))
        names = ", ".join(sorted(
            "'%s' (hub port %s, channel %s)" % (
                phidget.indigoDevice.name, phidget.channelInfo.hubPort,
                phidget.channelInfo.channel)
            for phidget in affected))
        longest = max(details[0] for details in affected.values())
        messages = sorted(set(details[1] for details in affected.values()))
        self.logger.error(
            "Phidget open failed after %.1f seconds on server '%s', physical "
            "serial %s; %d configured channels remain unavailable: %s. %s "
            "Automatic attachment remains active.",
            longest, first.serverDisplayName(), first.channelInfo.serialNumber,
            len(affected), names, "; ".join(messages))

    def flush_startup_unavailable(self, physical_device, token=None):
        pending = self._take_batch(
            "startup-unavailable", physical_device, {}, token)
        affected = {
            phidget: details for phidget, details in pending.items()
            if phidget._state in ("starting", "detached")
        }
        if not affected:
            return
        configured = [
            phidget for phidget in self._channel_snapshot()
            if PhysicalDeviceIdentity.from_wrapper(phidget) == physical_device]
        if not (len(configured) > 1 and set(affected) == set(configured)):
            for phidget, (detached_for, state) in affected.items():
                self.logger.error(
                    "Phidget remains detached after %.1f seconds (%s): %s; "
                    "automatic attachment remains active",
                    detached_for, state, phidget._identity())
            return
        servers = ", ".join(sorted(set(
            phidget.serverDisplayName() for phidget in affected)))
        names = ", ".join(sorted(
            "'%s' (hub port %s, channel %s)" % (
                phidget.indigoDevice.name, phidget.channelInfo.hubPort,
                phidget.channelInfo.channel)
            for phidget in affected))
        longest = max(details[0] for details in affected.values())
        self.logger.error(
            "Physical Phidget serial %s remains unavailable after %.1f seconds; "
            "all %d configured channels are detached (server: %s): %s. "
            "Check the Phidget and Network Server; automatic attachment "
            "remains active.",
            physical_device.serial_number, longest, len(affected), servers,
            names)

    def flush_startup_contention(self, key, token=None):
        pending = self._take_batch("startup-contention", key, {}, token)
        affected = [
            (phidget, detached_for)
            for phidget, detached_for in pending.items()
            if (phidget._state != "attached" and
                phidget._startup_contention_message)
        ]
        if not affected:
            return
        names = ", ".join(sorted(
            "'%s' (channel %s)" % (
                phidget.indigoDevice.name, phidget.channelInfo.channel)
            for phidget, _ in affected))
        longest = max(detached_for for _, detached_for in affected)
        first = affected[0][0]
        self.logger.error(
            "Phidget channels remained in use for %.1f seconds on server '%s', "
            "serial %s, hub port %s: %s. Check for another Indigo plugin "
            "instance, Phidget Control Panel, or another program using them.",
            longest, first.serverDisplayName(), first.channelInfo.serialNumber,
            first.channelInfo.hubPort, names)

    def flush_detach(self, server_key, token=None):
        pending = self._take_batch("detach", server_key, set(), token)
        configured = self._channels_for_server(server_key)
        affected = [phidget for phidget in configured
                    if phidget._state == "detached" and
                    phidget._detach_announced]
        if len(configured) > 1 and len(affected) == len(configured):
            detached_at = min(phidget._detached_at for phidget in affected)
            serials = {phidget.channelInfo.serialNumber for phidget in affected}
            with self._lock:
                self._server_outages[server_key] = {
                    "detachedAt": detached_at,
                    "channelCount": len(affected),
                    "serialCount": len(serials),
                    "displayName": affected[0].serverDisplayName(),
                }
            self.logger.warning(
                "Phidget server '%s' disconnected; %d configured channels "
                "across %d physical Phidgets are unavailable and awaiting "
                "automatic reattach", affected[0].serverDisplayName(),
                len(affected), len(serials))
            return
        for phidget in pending:
            if phidget._state == "detached" and phidget._detach_announced:
                detached_for = self._clock() - phidget._detached_at
                self.logger.warning(
                    "Phidget remains detached after %.1f seconds; awaiting "
                    "automatic reattach: %s", detached_for,
                    phidget._identity())

    def flush_recovery(self, server_key, token=None):
        pending = self._take_batch("recovery", server_key, {}, token)
        with self._lock:
            outage = self._server_outages.get(server_key)
        configured = self._channels_for_server(server_key)
        if outage is not None:
            if configured and all(
                    phidget._state == "attached" for phidget in configured):
                duration = self._clock() - outage["detachedAt"]
                self.logger.info(
                    "Phidget server '%s' recovered after %.1f seconds; all %d "
                    "configured channels across %d physical Phidgets reattached",
                    outage["displayName"], duration, outage["channelCount"],
                    outage["serialCount"])
                with self._lock:
                    self._server_outages.pop(server_key, None)
            return
        for phidget, detached_for in pending.items():
            self.logger.info(
                "Phidget reattached in %.1f seconds (attach #%d): %s",
                detached_for, phidget._attach_count, phidget._identity())

    def stop(self):
        with self._lock:
            timers = [item[0] for item in self._timers.values()]
            self._timers.clear()
            for batches in self._batches.values():
                batches.clear()
            self._server_outages.clear()
            self._open_failure_last_logged.clear()
        for timer in timers:
            timer.cancel()
