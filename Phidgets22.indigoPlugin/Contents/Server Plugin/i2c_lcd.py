# -*- coding: utf-8 -*-

"""Freenove LCD2004 transport over a shared Phidget DataAdapter."""

import time

from Phidget22.ChannelSubclass import ChannelSubclass
from Phidget22.LCDScreenSize import LCDScreenSize

from lcd import LCDPhidget


class FreenoveLCD2004Channel(object):
    """LCD-like compatibility channel backed by PCF8574T at address 0x27."""

    ADDRESS = 0x27
    WIDTH = 20
    HEIGHT = 4
    ROW_ADDRESSES = (0x00, 0x40, 0x14, 0x54)
    ENABLE = 0x04
    BACKLIGHT = 0x08
    REGISTER_SELECT = 0x01

    def __init__(self, adapter_device_id):
        self.parent = None
        self.adapterDeviceId = int(adapter_device_id)
        self.adapter = None
        self._attach_handler = None
        self._detach_handler = None
        self._error_handler = None
        self._backlight = 1.0
        self._contrast = 0.5
        self._sleeping = False
        self._buffer = [[" "] * self.WIDTH for _ in range(self.HEIGHT)]
        self._pending_bytes = None

    # PhidgetBase addressing/lifecycle compatibility. The physical channel is
    # already owned and opened by DataAdapterPhidget.
    def setDeviceSerialNumber(self, value): pass
    def setChannel(self, value): pass
    def setIsRemote(self, value): pass
    def setServerName(self, value): pass
    def setIsHubPortDevice(self, value): pass
    def setHubPort(self, value): pass
    def setOnAttachHandler(self, handler): self._attach_handler = handler
    def setOnDetachHandler(self, handler): self._detach_handler = handler
    def setOnErrorHandler(self, handler): self._error_handler = handler

    def open(self):
        self.adapter = LCDPhidget.resolveAdapterProvider(
            self.parent.indigo_plugin, self.adapterDeviceId)
        if self._attach_handler is not None:
            self._attach_handler(self)

    def close(self):
        self.adapter = None

    def getDeviceName(self): return "Freenove LCD2004"
    def getDeviceSKU(self): return "FREENOVE-LCD2004-PCF8574T"
    def getChannelName(self): return "LCD"

    def _send(self, values):
        if self.adapter is None:
            raise RuntimeError("The selected display provider is not active")
        if self._pending_bytes is not None:
            self._pending_bytes.extend(values)
            return b""
        return self.adapter.i2cSendReceive(self.ADDRESS, values, 0)

    def _send_batched(self, values):
        maximum = int(self.adapter.phidget.getMaxSendPacketLength()) \
            if hasattr(self.adapter, "phidget") else 127
        # Every expander transition is a three-byte enable pulse. Keep packet
        # boundaries between pulses so a network round trip cannot leave E high.
        maximum -= maximum % 3
        if maximum < 3:
            raise ValueError("DataAdapter packet size is too small for LCD pulses")
        for offset in range(0, len(values), maximum):
            self.adapter.i2cSendReceive(
                self.ADDRESS, values[offset:offset + maximum], 0)

    def _expander(self, value):
        if self._backlight > 0 and not self._sleeping:
            value |= self.BACKLIGHT
        self._send([value])

    def _nibble(self, nibble, register_select=False):
        value = ((int(nibble) & 0x0f) << 4)
        if register_select:
            value |= self.REGISTER_SELECT
        self._send([
            value | (self.BACKLIGHT if self._backlight > 0 and not self._sleeping else 0),
            value | self.ENABLE |
            (self.BACKLIGHT if self._backlight > 0 and not self._sleeping else 0),
            value | (self.BACKLIGHT if self._backlight > 0 and not self._sleeping else 0),
        ])

    def _byte(self, value, register_select=False):
        self._nibble((value >> 4) & 0x0f, register_select)
        self._nibble(value & 0x0f, register_select)

    def _command(self, value):
        self._byte(value, False)

    def initialize(self):
        time.sleep(0.05)
        self._nibble(0x03)
        time.sleep(0.005)
        self._nibble(0x03)
        time.sleep(0.001)
        self._nibble(0x03)
        self._nibble(0x02)
        self._command(0x28)  # four-bit, two-line font mode (also used by 20x4)
        self._command(0x08)  # display off during setup
        self._command(0x01)
        time.sleep(0.002)
        self._command(0x06)  # increment cursor
        self._command(0x0c)  # display on, cursor and blink off

    def getChannelSubclass(self):
        return ChannelSubclass.PHIDCHSUBCLASS_LCD_TEXT

    def setScreenSize(self, value):
        if LCDScreenSize(int(value)) != LCDScreenSize.SCREEN_SIZE_4x20:
            raise ValueError("Freenove LCD2004 requires the 4 rows × 20 characters size")

    def getScreenSize(self): return LCDScreenSize.SCREEN_SIZE_4x20
    def setAutoFlush(self, value): pass
    def getWidth(self): return self.WIDTH
    def getHeight(self): return self.HEIGHT
    def setCursorBlink(self, value): pass
    def setCursorOn(self, value): pass

    def getMinBacklight(self): return 0.0
    def getMaxBacklight(self): return 1.0
    def getBacklight(self): return self._backlight

    def setBacklight(self, value):
        self._backlight = float(value)
        self._expander(0)

    # Contrast is adjusted by the physical potentiometer on this backpack.
    # Retain the requested value so the existing LCD contract remains stable.
    def getMinContrast(self): return 0.0
    def getMaxContrast(self): return 1.0
    def getContrast(self): return self._contrast
    def setContrast(self, value): self._contrast = float(value)

    def getSleeping(self): return self._sleeping

    def setSleeping(self, sleeping):
        self._sleeping = bool(sleeping)
        self._command(0x08 if self._sleeping else 0x0c)
        self._expander(0)

    def clear(self):
        self._buffer = [[" "] * self.WIDTH for _ in range(self.HEIGHT)]

    def writeText(self, font, x, y, text):
        x, y = int(x), int(y)
        for offset, character in enumerate(str(text)):
            column = x + offset
            if column >= self.WIDTH:
                break
            self._buffer[y][column] = character

    def flush(self):
        self._command(0x01)
        time.sleep(0.002)
        self._pending_bytes = []
        try:
            for row, address in enumerate(self.ROW_ADDRESSES):
                self._command(0x80 | address)
                for character in self._buffer[row]:
                    codepoint = ord(character)
                    self._byte(codepoint if codepoint <= 0xff else ord("?"), True)
            payload = self._pending_bytes
        finally:
            self._pending_bytes = None
        self._send_batched(payload)


class I2CLCDPhidget(LCDPhidget):
    """Existing LCD action contract implemented by a shared I2C adapter."""

    PROFILE = "freenove-lcd2004-pcf8574t"

    def __init__(self, adapterDeviceId, *args, **kwargs):
        kwargs["phidget"] = FreenoveLCD2004Channel(adapterDeviceId)
        super(I2CLCDPhidget, self).__init__(*args, **kwargs)
        self.adapterDeviceId = int(adapterDeviceId)

    def providerReattached(self):
        """Reinitialize the controller after its shared adapter reconnects."""
        with self._display_lock:
            self.phidget.adapter = self.resolveAdapterProvider(
                self.indigo_plugin, self.adapterDeviceId)
            self.configureAttachedPhidget(self.phidget)
            self.updateIndigoStatus()
            self._replay_pending_display_request()
