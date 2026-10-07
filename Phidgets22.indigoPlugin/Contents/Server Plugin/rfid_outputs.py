# -*- coding: utf-8 -*-
"""The 1024's three DigitalOutput channels, owned by one RFID device."""
import threading

from Phidget22.Devices.DigitalOutput import DigitalOutput

OUTPUTS = (
    ("digitalOutput", "Digital output (channel 0)"),
    ("ledDriver", "LED driver (channel 1)"),
    ("onboardLED", "Onboard LED (channel 2)"),
)


class RFIDOutputs:
    def __init__(self, owner, simulated=False):
        self.owner = owner
        self.simulated = simulated
        self.lock = threading.RLock()
        self.handles = {}
        self.values = [False] * 3
        self.errors = {}
        self.running = False
        self.timer = None
        self.generation = 0

    def _publish(self, channel, value=None, available=False):
        key = OUTPUTS[channel][0]
        if value is not None:
            self.owner.updateStateOnServer(key, bool(value))
        self.owner.updateStateOnServer(key + "Available", available)

    def _error(self, channel, operation, error):
        message = str(error).replace("\n", " ")
        if self.errors.get(channel) != (operation, message):
            self.owner.logger.error("RFID %s %s failed for '%s': %s",
                                    OUTPUTS[channel][1], operation,
                                    self.owner.indigoDevice.name, message)
        self.errors[channel] = (operation, message)
        try:
            self._publish(channel)
        except Exception as publish_error:
            self.owner.logger.error("RFID output availability update failed for '%s': %s",
                                    self.owner.indigoDevice.name,
                                    str(publish_error).replace("\n", " "))

    def start(self, ph=None):
        cleanup = []
        with self.lock:
            if self.running:
                return
            self.running = True
            self.generation += 1
            for channel in range(3):
                try:
                    self._publish(channel, False if self.simulated else None,
                                  available=self.simulated)
                    if self.simulated:
                        self.values[channel] = False
                        continue
                    handle = DigitalOutput()
                    self.handles[channel] = handle
                    # Use the attached reader's identity, never a wildcard or
                    # the RFID channel number (each API has its own numbering).
                    handle.setDeviceSerialNumber(ph.getDeviceSerialNumber())
                    remote = bool(ph.getIsRemote())
                    handle.setIsRemote(remote)
                    if remote:
                        handle.setServerName(ph.getServerName())
                    handle.setChannel(channel)
                    handle.setOnAttachHandler(lambda h, c=channel: self.refresh(c, h))
                    handle.setOnDetachHandler(lambda h, c=channel: self.detached(c, h))
                    handle.setOnErrorHandler(lambda h, code, description, c=channel:
                                             self.failed(c, h, code, description))
                    handle.open()
                except Exception as error:
                    self._error(channel, "initialization", error)
                    handle = self.handles.pop(channel, None)
                    if handle is not None:
                        cleanup.append((channel, handle))
            if not self.simulated:
                self._schedule()
        for channel, handle in cleanup:
            try:
                handle.close()
            except Exception as close_error:
                self._error(channel, "cleanup", close_error)

    def _schedule(self):
        try:
            self.timer = threading.Timer(1.0, self._poll, args=(self.generation,))
            self.timer.daemon = True
            self.timer.start()
        except Exception as error:
            for channel in range(3):
                self._error(channel, "status timer", error)

    def _poll(self, generation):
        with self.lock:
            if not self.running or generation != self.generation:
                return
            self.timer = None
            for channel, handle in self.handles.items():
                self.refresh(channel, handle)
            self._schedule()

    def refresh(self, channel, handle):
        with self.lock:
            if not self.running or self.handles.get(channel) is not handle:
                return
            try:
                if handle.getAttached():
                    self._publish(channel, handle.getState(), available=True)
                    self.errors.pop(channel, None)
                else:
                    self._publish(channel)
            except Exception as error:
                self._error(channel, "state read", error)

    def detached(self, channel, handle):
        with self.lock:
            if not self.running or self.handles.get(channel) is not handle:
                return
            try:
                self._publish(channel)
            except Exception as error:
                self._error(channel, "detach", error)

    def failed(self, channel, handle, code, description):
        with self.lock:
            if self.running and self.handles.get(channel) is handle:
                self._error(channel, "channel", "%s: %s" % (code, description))

    def set(self, channel, enabled):
        with self.lock:
            if channel not in range(3) or type(enabled) is not bool:
                raise ValueError("select an RFID output and On or Off")
            try:
                if not self.running or self.owner._state != "attached":
                    raise ValueError("RFID reader is not attached")
                if self.simulated:
                    self.values[channel] = enabled
                    self._publish(channel, enabled, available=True)
                else:
                    handle = self.handles.get(channel)
                    if handle is None or not handle.getAttached():
                        raise ValueError("output channel is not attached")
                    handle.setState(enabled)
                    self._publish(channel, handle.getState(), available=True)
                self.errors.pop(channel, None)
            except Exception as error:
                self._error(channel, "On/Off action", error)

    def stop(self):
        with self.lock:
            self.running = False
            self.generation += 1
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None
            handles, self.handles = self.handles, {}
            for channel in range(3):
                try:
                    self._publish(channel)
                except Exception as error:
                    self._error(channel, "stop", error)
        # Closing can wait for SDK callbacks; do not hold the callback lock.
        for channel, handle in handles.items():
            try:
                handle.close()
            except Exception as error:
                self._error(channel, "close", error)
