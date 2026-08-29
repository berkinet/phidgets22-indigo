# -*- coding: utf-8 -*-

"""Configurable HD44780/PCF8574 transport over a shared DataAdapter."""

import threading
import time

from Phidget22.ChannelSubclass import ChannelSubclass
from Phidget22.LCDScreenSize import LCDScreenSize
from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException

from lcd import LCDPhidget
from phidget import PeripheralUnavailableError


class HD44780PCF8574Channel(object):
    """LCD-like channel backed by a PCF8574-compatible I2C expander."""

    GEOMETRIES = {
        int(LCDScreenSize.SCREEN_SIZE_2x16): (16, 2, (0x00, 0x40)),
        int(LCDScreenSize.SCREEN_SIZE_4x20): (20, 4, (0x00, 0x40, 0x14, 0x54)),
    }

    def __init__(self, adapter_device_id, screen_size=8, address=0x27,
                 pin_mapping=None, backlight_active_high=True):
        self.parent = None
        self.adapterDeviceId = int(adapter_device_id)
        self.address = int(address)
        mapping = dict(pin_mapping or {
            "rs": 0, "rw": 1, "enable": 2, "backlight": 3,
            "d4": 4, "d5": 5, "d6": 6, "d7": 7,
        })
        self.pinMapping = mapping
        self._rs_mask = 1 << mapping["rs"]
        self._enable_mask = 1 << mapping["enable"]
        self._backlight_mask = 1 << mapping["backlight"]
        self._data_masks = tuple(1 << mapping["d%d" % bit]
                                 for bit in range(4, 8))
        self.backlightActiveHigh = bool(backlight_active_high)
        self.adapter = None
        self._attach_handler = None
        self._detach_handler = None
        self._error_handler = None
        self._backlight = 1.0
        self._contrast = 0.5
        self._sleeping = False
        self.setScreenSize(screen_size)
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
        if (getattr(self.adapter, "_state", None) == "attached" and
                self._attach_handler is not None):
            self._attach_handler(self)

    def providerAttached(self):
        """Complete logical attachment after the shared adapter is ready."""
        self.adapter = LCDPhidget.resolveAdapterProvider(
            self.parent.indigo_plugin, self.adapterDeviceId)
        if getattr(self.adapter, "_state", None) != "attached":
            return False
        if self._attach_handler is not None:
            self._attach_handler(self)
        return True

    def close(self):
        self.adapter = None

    def getDeviceName(self): return "HD44780 / PCF8574-compatible LCD"
    def getDeviceSKU(self): return "HD44780-PCF8574-COMPATIBLE"
    def getChannelName(self): return "LCD"

    def _send(self, values):
        if self.adapter is None:
            raise RuntimeError("The selected display provider is not active")
        if self._pending_bytes is not None:
            self._pending_bytes.extend(values)
            return b""
        return self.adapter.i2cSendReceive(self.address, values, 0)

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
                self.address, values[offset:offset + maximum], 0)

    def _backlight_bits(self):
        lit = self._backlight > 0 and not self._sleeping
        return self._backlight_mask if lit == self.backlightActiveHigh else 0

    def _expander(self, value):
        value |= self._backlight_bits()
        self._send([value])

    def _nibble(self, nibble, register_select=False):
        value = 0
        for bit, mask in enumerate(self._data_masks):
            if int(nibble) & (1 << bit):
                value |= mask
        if register_select:
            value |= self._rs_mask
        value |= self._backlight_bits()
        self._send([
            value,
            value | self._enable_mask,
            value,
        ])

    def _byte(self, value, register_select=False):
        self._nibble((value >> 4) & 0x0f, register_select)
        self._nibble(value & 0x0f, register_select)

    def _command(self, value):
        self._byte(value, False)

    def initialize(self):
        try:
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
        except PhidgetException as error:
            if error.code == ErrorCode.EPHIDGET_NACK:
                raise PeripheralUnavailableError(
                    "No I2C display responded at 0x%02X. Verify the configured "
                    "address, address jumpers, power, and wiring." % self.address
                ) from None
            raise

    def getChannelSubclass(self):
        return ChannelSubclass.PHIDCHSUBCLASS_LCD_TEXT

    def setScreenSize(self, value):
        screen_size = int(value)
        if screen_size not in self.GEOMETRIES:
            raise ValueError("This I2C LCD supports 2 rows × 16 characters or "
                             "4 rows × 20 characters")
        self.screenSize = screen_size
        self.WIDTH, self.HEIGHT, self.ROW_ADDRESSES = self.GEOMETRIES[screen_size]
        self._buffer = [[" "] * self.WIDTH for _ in range(self.HEIGHT)]

    def getScreenSize(self): return LCDScreenSize(self.screenSize)
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

    # Contrast is adjusted by the physical potentiometer on these modules.
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

    PROFILE = "hd44780-pcf8574-compatible"

    def __init__(self, adapterDeviceId, i2cAddress=0x27, pinMapping=None,
                 backlightActiveHigh=True, *args, **kwargs):
        kwargs["phidget"] = HD44780PCF8574Channel(
            adapterDeviceId, screen_size=kwargs.get("screenSize", 8),
            address=i2cAddress, pin_mapping=pinMapping,
            backlight_active_high=backlightActiveHigh)
        super(I2CLCDPhidget, self).__init__(*args, **kwargs)
        self.adapterDeviceId = int(adapterDeviceId)
        self._provider_retry_timer = None
        self._provider_retry_generation = 0

    def _cancelProviderRetry(self):
        self._provider_retry_generation += 1
        timer, self._provider_retry_timer = self._provider_retry_timer, None
        if timer is not None:
            timer.cancel()

    def _scheduleProviderRetry(self):
        self._cancelProviderRetry()
        generation = self._provider_retry_generation
        timer = threading.Timer(1.0, self._retryProvider, (generation,))
        timer.daemon = True
        self._provider_retry_timer = timer
        timer.start()

    def _retryProvider(self, generation):
        if (generation != self._provider_retry_generation or
                self._state in ("stopping", "stopped")):
            return
        self._provider_retry_timer = None
        self.phidget.providerAttached()

    def onAttachHandler(self, ph):
        super(I2CLCDPhidget, self).onAttachHandler(ph)
        if self._state == "attached":
            self._cancelProviderRetry()
        elif (self.phidget.adapter is not None and
              getattr(self.phidget.adapter, "_state", None) == "attached"):
            self._scheduleProviderRetry()

    def providerReattached(self):
        """Reinitialize the controller after its shared adapter reconnects."""
        return self.phidget.providerAttached()

    def providerStopping(self):
        self._cancelProviderRetry()
        super(I2CLCDPhidget, self).providerStopping()

    def stop(self):
        self._cancelProviderRetry()
        super(I2CLCDPhidget, self).stop()


# Source compatibility for code written against the first fixed profile.
FreenoveLCD2004Channel = HD44780PCF8574Channel
