# -*- coding: utf-8 -*-

"""Cancellable, paired detach/attach event delivery."""

import threading

import indigo


class EventCoordinator(object):
    def __init__(self, timer_factory=threading.Timer):
        self.triggers = {}
        self._lock = threading.RLock()
        self._timers = {}
        self._reported_detaches = set()
        self._timer_factory = timer_factory

    def start_processing(self, trigger):
        if trigger.pluginTypeId == "firmwareUpdateAvailable":
            with self._lock:
                self.triggers[trigger.id] = {
                    "devid": None, "event": trigger.pluginTypeId, "delay": 0.0}
            return
        device_id = int(trigger.pluginProps["indigoDevice"])
        try:
            delay = float(trigger.pluginProps.get("detachDelay", 0) or 0)
        except (TypeError, ValueError):
            delay = 0.0
        with self._lock:
            pending = self._timers.pop(trigger.id, None)
            self.triggers[trigger.id] = {
                "devid": device_id,
                "event": trigger.pluginTypeId,
                "delay": max(0.0, delay),
            }
        if pending is not None:
            pending[0].cancel()

    def stop_processing(self, trigger):
        with self._lock:
            self.triggers.pop(trigger.id, None)
            pending = self._timers.pop(trigger.id, None)
        if pending is not None:
            pending[0].cancel()

    def _cancel_delayed_detach(self, device_id):
        with self._lock:
            trigger_ids = [
                trigger_id for trigger_id, details in self.triggers.items()
                if details["devid"] == device_id]
            timers = [self._timers.pop(trigger_id)[0]
                      for trigger_id in trigger_ids
                      if trigger_id in self._timers]
        for timer in timers:
            timer.cancel()

    def _schedule_detach(self, trigger_id, source, delay):
        device_id = source.indigoDevice.id
        token = object()
        timer = self._timer_factory(
            delay, self._execute_delayed_detach,
            args=(trigger_id, source, token))
        timer.daemon = True
        with self._lock:
            old = self._timers.pop(trigger_id, None)
            self._timers[trigger_id] = (timer, token)
        if old is not None:
            old[0].cancel()
        timer.start()

    def _execute_delayed_detach(self, trigger_id, source, token):
        device_id = source.indigoDevice.id
        with self._lock:
            pending = self._timers.get(trigger_id)
            details = self.triggers.get(trigger_id)
            if (pending is None or pending[1] is not token or
                    details is None or details["devid"] != device_id or
                    details["event"] != "deviceDetached"):
                return
            self._timers.pop(trigger_id, None)
            if getattr(source, "_state", None) != "detached":
                return
            self._reported_detaches.add(device_id)
        indigo.trigger.execute(trigger_id)

    def trigger_event(self, source, event):
        device_id = source.indigoDevice.id
        if event == "deviceAttached":
            self._cancel_delayed_detach(device_id)
        with self._lock:
            triggers = list(self.triggers.items())
            detach_tracked = any(
                details["devid"] == device_id and
                details["event"] == "deviceDetached"
                for details in self.triggers.values())
            detach_reported = device_id in self._reported_detaches
            if event == "deviceAttached" and detach_reported:
                self._reported_detaches.discard(device_id)
        if event == "deviceAttached" and detach_tracked and not detach_reported:
            return
        for trigger_id, trigger in triggers:
            if trigger["devid"] != device_id or trigger["event"] != event:
                continue
            delay = trigger.get("delay", 0.0)
            if event == "deviceDetached" and delay > 0:
                self._schedule_detach(trigger_id, source, delay)
            else:
                if event == "deviceDetached":
                    with self._lock:
                        self._reported_detaches.add(device_id)
                indigo.trigger.execute(trigger_id)

    def trigger_global_event(self, event):
        with self._lock:
            trigger_ids = [trigger_id for trigger_id, details
                           in self.triggers.items()
                           if details["devid"] is None and
                           details["event"] == event]
        for trigger_id in trigger_ids:
            indigo.trigger.execute(trigger_id)

    def stop(self):
        with self._lock:
            timers = [item[0] for item in self._timers.values()]
            self._timers.clear()
            self._reported_detaches.clear()
        for timer in timers:
            timer.cancel()
