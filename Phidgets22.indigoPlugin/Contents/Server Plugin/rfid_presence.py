# -*- coding: utf-8 -*-
"""Per-reader presence held until a delay after the last qualifying tag leaves."""
import threading
import time

from config_util import bounded_float


def clear_delay_seconds(props):
    return 60 * bounded_float(props.get("rfidPresenceClearMinutes", 0), 0, 1440)


class RFIDPresence(object):
    def __init__(self, owner, timer_factory=threading.Timer, clock=time.monotonic):
        self.owner = owner
        self.timer_factory = timer_factory
        self.clock = clock
        self.active = False
        self.qualifying_tag_present = False
        self.timer = None
        self.deadline = None
        self.generation = 0
        self.stopped = False
        self.reset()

    def _cancel(self):
        self.generation += 1
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        self.deadline = None

    def _publish(self, active):
        if active != self.active:
            self.owner.updateStateOnServer("presenceActive", active)
            self.active = active

    def reset(self):
        with self.owner._tag_lock:
            self._cancel()
            self.stopped = False
            self.qualifying_tag_present = False
            # Reconcile a stale true state after restart, and prime the state
            # publisher so the first real detection can fire an Indigo trigger.
            self.owner.updateStateOnServer("presenceActive", False, triggerEvents=True)
            self.active = False

    def stop(self):
        with self.owner._tag_lock:
            self.stopped = True
            self.qualifying_tag_present = False
            self._cancel()
            self._publish(False)

    def _arm(self, seconds):
        self.timer = self.timer_factory(seconds, self._expire, args=(self.generation,))
        self.timer.daemon = True
        self.timer.start()

    def update(self, qualifying):
        with self.owner._tag_lock:
            if self.stopped:
                return
            if qualifying:
                self._cancel()
                self.qualifying_tag_present = True
                self._publish(True)
            elif self.qualifying_tag_present:
                self.qualifying_tag_present = False
                self._cancel()
                try:
                    delay = clear_delay_seconds(self.owner.rfidPolicyProps)
                    if delay == 0:
                        self._publish(False)
                    else:
                        self.deadline = self.clock() + delay
                        self._arm(delay)
                except Exception as error:
                    self._cancel()
                    self._publish(False)
                    self.owner._report("presence countdown", error)
            # Repeated loss or denied tags must not restart an existing delay.

    def _expire(self, generation):
        with self.owner._tag_lock:
            if (self.stopped or generation != self.generation or
                    self.qualifying_tag_present or self.deadline is None):
                return
            self.timer = None
            try:
                remaining = self.deadline - self.clock()
                if remaining > 0:
                    self._arm(remaining)
                    return
                self._publish(False)
                self.deadline = None
            except Exception as error:
                self.owner._report("presence timeout", error)
                # Keep a failed state publication retryable, rather than leaving
                # Indigo reporting an active presence forever after one failure.
                try:
                    self._arm(1.0)
                except Exception as retry_error:
                    self.owner._report("presence timeout retry", retry_error)
