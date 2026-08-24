# -*- coding: utf-8 -*-

import threading

import indigo

from Phidget22.ChannelSubclass import ChannelSubclass
from Phidget22.Devices.LCD import LCD
from Phidget22.LCDFont import LCDFont
from Phidget22.LCDScreenSize import LCDScreenSize
from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException

from phidget import PhidgetBase


class LCDPhidget(PhidgetBase):
    """Indigo wrapper for Phidget22 text and graphic LCD channels."""

    def __init__(self, screenSize, backlight, contrast,
                 restoreInitialText, initialText, initialLines, initialX, initialY,
                 *args, **kwargs):
        super(LCDPhidget, self).__init__(phidget=LCD(), *args, **kwargs)
        self.screenSize = LCDScreenSize(int(screenSize))
        self.backlight = float(backlight)
        self.contrast = float(contrast)
        self.restoreInitialText = bool(restoreInitialText)
        self.initialText = initialText or ""
        self.initialLines = list(initialLines or [])
        self.initialX = int(initialX)
        self.initialY = int(initialY)
        self.lastText = ""
        self.lcdType = "unknown"
        self.screenWidth = None
        self.screenHeight = None
        self._supportsSleeping = False
        self._display_lock = threading.RLock()

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)

    def _read_optional(self, method_name, default=None):
        try:
            return getattr(self.phidget, method_name)()
        except Exception:
            return default

    def _subclass_name(self, channel_subclass):
        if channel_subclass == ChannelSubclass.PHIDCHSUBCLASS_LCD_TEXT:
            return "text"
        if channel_subclass == ChannelSubclass.PHIDCHSUBCLASS_LCD_GRAPHIC:
            return "graphic"
        return "unknown"

    def _set_bounded(self, label, value, minimum_method, maximum_method, setter):
        minimum = getattr(self.phidget, minimum_method)()
        maximum = getattr(self.phidget, maximum_method)()
        if value < minimum or value > maximum:
            raise ValueError("%s %.3f is outside the attached LCD range %.3f–%.3f" %
                             (label, value, minimum, maximum))
        getattr(self.phidget, setter)(value)

    def configureAttachedPhidget(self, ph):
        with self._display_lock:
            channel_subclass = self.phidget.getChannelSubclass()
            self.lcdType = self._subclass_name(channel_subclass)

            if (self.lcdType == "graphic" and
                    self.screenSize != LCDScreenSize.SCREEN_SIZE_NONE):
                raise ValueError("Use Automatic / graphic LCD for a graphic display")

            if self.screenSize != LCDScreenSize.SCREEN_SIZE_NONE:
                self.phidget.setScreenSize(self.screenSize)

            active_screen_size = self.phidget.getScreenSize()
            if (self.lcdType == "text" and
                    active_screen_size == LCDScreenSize.SCREEN_SIZE_NONE):
                raise ValueError(
                    "Select the dimensions of the LCD panel connected to this text LCD adapter")

            # Text adapters such as the 1204 need the attached panel initialized
            # after its dimensions have been selected. Some LCD channels do not
            # implement initialize(), so only invoke it for a configured text LCD.
            if (self.lcdType == "text" and
                    self.screenSize != LCDScreenSize.SCREEN_SIZE_NONE):
                try:
                    self.phidget.initialize()
                except PhidgetException as error:
                    if error.code != ErrorCode.EPHIDGET_UNSUPPORTED:
                        raise
                    self.logger.debug("LCD initialize is unavailable: %s", error)

            # The first release exposes complete display actions rather than
            # frame-buffer batching, so every action must become visible.
            self.phidget.setAutoFlush(True)
            self._set_bounded("Backlight", self.backlight,
                              "getMinBacklight", "getMaxBacklight", "setBacklight")
            self._set_bounded("Contrast", self.contrast,
                              "getMinContrast", "getMaxContrast", "setContrast")

            self.screenWidth = self.phidget.getWidth()
            self.screenHeight = self.phidget.getHeight()
            sleeping = self._read_optional("getSleeping")
            self._supportsSleeping = sleeping is not None

            if self.restoreInitialText:
                if any(self.initialLines):
                    self._write_lines(self.initialLines)
                elif self.initialText:
                    # Preserve coordinate-based settings saved by v0.2.1.35.
                    self._write_text(self.initialText, self.initialX, self.initialY)

    def onAttachHandler(self, ph):
        super(LCDPhidget, self).onAttachHandler(ph)
        if self._state == "attached":
            self.updateIndigoStatus()

    def _ensure_attached(self):
        if self._state != "attached":
            raise RuntimeError("LCD '%s' is not attached" % self.indigoDevice.name)

    def _validate_position(self, x, y):
        width = self.screenWidth if self.screenWidth is not None else self.phidget.getWidth()
        height = self.screenHeight if self.screenHeight is not None else self.phidget.getHeight()
        if x < 0 or x >= width:
            raise ValueError("LCD x position %d is outside 0–%d" % (x, width - 1))
        if y < 0 or y >= height:
            raise ValueError("LCD y position %d is outside 0–%d" % (y, height - 1))

    def _write_text(self, text, x, y):
        x = int(x)
        y = int(y)
        self._validate_position(x, y)
        self.phidget.writeText(LCDFont.FONT_5x8, x, y, text)
        # The 1204 accepts writeText without making it visible until flush is
        # called, even when auto-flush has been enabled.
        self.phidget.flush()
        self.lastText = text

    def writeText(self, text, x=0, y=0):
        with self._display_lock:
            self._ensure_attached()
            self._write_text(str(text), x, y)
            self.updateIndigoStatus()

    def _write_lines(self, lines):
        if self.lcdType != "text":
            raise ValueError("Write LCD lines is only available for text LCDs")
        height = self.screenHeight if self.screenHeight is not None else self.phidget.getHeight()
        width = self.screenWidth if self.screenWidth is not None else self.phidget.getWidth()
        normalized = [str(line or "") for line in lines]
        if any(normalized[height:]):
            raise ValueError("The attached LCD has only %d text line%s" %
                             (height, "" if height == 1 else "s"))
        for line_number, line in enumerate(normalized[:height]):
            if len(line) > width:
                raise ValueError("LCD line %d is longer than %d characters" %
                                 (line_number + 1, width))
        self.phidget.clear()
        for line_number, line in enumerate(normalized[:height]):
            if line:
                self.phidget.writeText(LCDFont.FONT_5x8, 0, line_number, line)
        self.phidget.flush()
        self.lastText = "\n".join(normalized[:height]).rstrip("\n")

    def writeLines(self, lines):
        with self._display_lock:
            self._ensure_attached()
            self._write_lines(lines)
            self.updateIndigoStatus()

    def clear(self):
        with self._display_lock:
            self._ensure_attached()
            self.phidget.clear()
            self.phidget.flush()
            self.lastText = ""
            self.updateIndigoStatus()

    def setBacklight(self, value):
        with self._display_lock:
            self._ensure_attached()
            self._set_bounded("Backlight", float(value),
                              "getMinBacklight", "getMaxBacklight", "setBacklight")
            self.updateIndigoStatus()

    def setContrast(self, value):
        with self._display_lock:
            self._ensure_attached()
            self._set_bounded("Contrast", float(value),
                              "getMinContrast", "getMaxContrast", "setContrast")
            self.updateIndigoStatus()

    def setSleeping(self, sleeping):
        with self._display_lock:
            self._ensure_attached()
            if not self._supportsSleeping:
                raise ValueError("The attached LCD does not support sleep/wake control")
            self.phidget.setSleeping(bool(sleeping))
            self.updateIndigoStatus()

    def updateIndigoStatus(self):
        values = {
            "lcdType": self.lcdType,
            "screenWidth": self.screenWidth,
            "screenHeight": self.screenHeight,
            "backlight": self._read_optional("getBacklight"),
            "contrast": self._read_optional("getContrast"),
            "sleeping": self._read_optional("getSleeping"),
            "lastText": self.lastText,
        }
        for state_id, value in values.items():
            if value is not None:
                self.indigoDevice.updateStateOnServer(state_id, value=value)

    def getDeviceStateList(self):
        states = indigo.List()
        states.append(self.indigo_plugin.getDeviceStateDictForStringType(
            "lcdType", "LCD type", "lcdType"))
        states.append(self.indigo_plugin.getDeviceStateDictForNumberType(
            "screenWidth", "Screen width", "screenWidth"))
        states.append(self.indigo_plugin.getDeviceStateDictForNumberType(
            "screenHeight", "Screen height", "screenHeight"))
        states.append(self.indigo_plugin.getDeviceStateDictForNumberType(
            "backlight", "Backlight", "backlight"))
        states.append(self.indigo_plugin.getDeviceStateDictForNumberType(
            "contrast", "Contrast", "contrast"))
        states.append(self.indigo_plugin.getDeviceStateDictForBoolOnOffType(
            "sleeping", "Sleeping", "sleeping"))
        states.append(self.indigo_plugin.getDeviceStateDictForStringType(
            "lastText", "Last text", "lastText"))
        return states

    def getDeviceDisplayStateId(self):
        return "lastText"
