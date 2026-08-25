# -*- coding: utf-8 -*-

import threading
import traceback

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
        self._emulatedSleeping = False
        self._wakeBacklight = None
        self._display_lock = threading.RLock()
        self._animation_generation = 0
        self._animation_timer = None
        self._animation_mode = "off"
        self._animation_frame = 0
        self._animation_settings = None
        self._pending_display_request = None

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)

    def _read_optional(self, method_name, default=None):
        try:
            return getattr(self.phidget, method_name)()
        except Exception:
            return default

    def _write_optional(self, method_name, value):
        try:
            getattr(self.phidget, method_name)(value)
            return True
        except Exception:
            return False

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

            # Cursor modes persist in the controller and appear as vertical
            # bars among moving text. Animations never use a visible cursor.
            if self.lcdType == "text":
                self._write_optional("setCursorBlink", False)
                self._write_optional("setCursorOn", False)

            # Flush complete frames explicitly. This keeps multi-row animation
            # updates together instead of exposing one changed row at a time.
            self.phidget.setAutoFlush(False)
            self._set_bounded("Backlight", self.backlight,
                              "getMinBacklight", "getMaxBacklight", "setBacklight")
            self._set_bounded("Contrast", self.contrast,
                              "getMinContrast", "getMaxContrast", "setContrast")

            self.screenWidth = self.phidget.getWidth()
            self.screenHeight = self.phidget.getHeight()
            sleeping = self._read_optional("getSleeping")
            self._supportsSleeping = sleeping is not None
            self._emulatedSleeping = False
            self._wakeBacklight = None

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
            self._replay_pending_display_request()

    def onDetachHandler(self, ph):
        with self._display_lock:
            self._cancel_animation_locked()
        super(LCDPhidget, self).onDetachHandler(ph)

    def stop(self):
        with self._display_lock:
            self._cancel_animation_locked()
            self._pending_display_request = None
        super(LCDPhidget, self).stop()

    def runDisplayWhenAttached(self, callback):
        """Run a display request now or retain only the newest detached request."""
        with self._display_lock:
            if self._state != "attached":
                replaced = self._pending_display_request is not None
                self._pending_display_request = callback
                self.logger.warning(
                    "LCD display request %s until attachment: device='%s'",
                    "replaced the previously queued request" if replaced else "queued",
                    self.indigoDevice.name)
                return False
            callback()
            return True

    def _replay_pending_display_request(self):
        with self._display_lock:
            callback = self._pending_display_request
            self._pending_display_request = None
            if callback is None:
                return
            try:
                callback()
                self.logger.info(
                    "Queued LCD display request applied after attachment: device='%s'",
                    self.indigoDevice.name)
            except Exception:
                self.logger.error(
                    "Queued LCD display request failed after attachment: device='%s'\n%s",
                    self.indigoDevice.name, traceback.format_exc())

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
            self._cancel_animation_locked()
            self._write_text(str(text), x, y)
            self.updateIndigoStatus()

    def _clip_text_row(self, text, width, context, line_number):
        if len(text) <= width:
            return text
        clipped = text[:width]
        self.logger.warning(
            "LCD %s text clipped: device='%s', line=%d, width=%d, "
            "original=%r, displayed=%r",
            context, self.indigoDevice.name, line_number, width, text, clipped)
        return clipped

    def _write_lines(self, lines):
        if self.lcdType != "text":
            raise ValueError("Write LCD lines is only available for text LCDs")
        height = self.screenHeight if self.screenHeight is not None else self.phidget.getHeight()
        width = self.screenWidth if self.screenWidth is not None else self.phidget.getWidth()
        normalized = [str(line or "") for line in lines]
        if any(normalized[height:]):
            raise ValueError("The attached LCD has only %d text line%s" %
                             (height, "" if height == 1 else "s"))
        visible_lines = [
            self._clip_text_row(line, width, "Static", line_number + 1)
            for line_number, line in enumerate(normalized[:height])
        ]
        self.phidget.clear()
        for line_number, line in enumerate(visible_lines):
            if line:
                self.phidget.writeText(LCDFont.FONT_5x8, 0, line_number, line)
        self.phidget.flush()
        self.lastText = "\n".join(visible_lines).rstrip("\n")

    def writeLines(self, lines):
        with self._display_lock:
            self._ensure_attached()
            self._cancel_animation_locked()
            self._write_lines(lines)
            self.updateIndigoStatus()

    def _cancel_animation_locked(self):
        self._animation_generation += 1
        timer = self._animation_timer
        self._animation_timer = None
        if timer is not None:
            timer.cancel()
        self._animation_mode = "off"
        self._animation_settings = None

    def _schedule_animation_locked(self, generation, interval):
        timer = threading.Timer(interval, self._animation_tick, (generation,))
        timer.daemon = True
        self._animation_timer = timer
        timer.start()

    def _marquee_window(self, text, width, frame, direction, gap):
        text = str(text or "")
        if len(text) <= width:
            return text.ljust(width)
        cycle = text + (" " * gap)
        offset = frame % len(cycle)
        if direction == "right":
            offset = (-frame) % len(cycle)
        rotated = cycle[offset:] + cycle[:offset]
        repeats = (width // len(rotated)) + 2
        return (rotated * repeats)[:width]

    def _virtual_marquee_rows(self, text, width, height, frame, direction, gap):
        """Render row-major display cells as one continuous marquee line."""
        text = str(text or "")
        capacity = width * height
        cells = [" "] * capacity
        if not text or capacity <= 0:
            return ["".join(cells[offset:offset + width])
                    for offset in range(0, capacity, width)]

        # Start with one copy entering the display, then introduce each later
        # copy exactly `gap` cells behind the previous one. Multiple copies may
        # therefore be visible at once when the text is shorter than the
        # row-major display capacity.
        period = len(text) + gap
        if direction == "left":
            first_start = capacity - 1 - frame
            copy_number = max(
                0, ((-first_start - len(text)) // period) + 1)
            while first_start + (copy_number * period) < capacity:
                start = first_start + (copy_number * period)
                for character_number, character in enumerate(text):
                    position = start + character_number
                    if 0 <= position < capacity:
                        cells[position] = character
                copy_number += 1
        else:
            first_start = -(len(text) - 1) + frame
            copy_number = max(
                0, ((first_start - capacity) // period) + 1)
            while first_start - (copy_number * period) + len(text) > 0:
                start = first_start - (copy_number * period)
                for character_number, character in enumerate(text):
                    position = start + character_number
                    if 0 <= position < capacity:
                        cells[position] = character
                copy_number += 1
        return ["".join(cells[offset:offset + width])
                for offset in range(0, capacity, width)]

    def _render_animation_locked(self):
        settings = self._animation_settings
        width = self.screenWidth
        height = self.screenHeight
        if settings["mode"] == "marquee":
            rows = [
                self._marquee_window(line, width, self._animation_frame,
                                     settings["direction"], settings["gap"])
                for line in settings["lines_a"]
            ]
        elif settings["mode"] == "virtualMarquee":
            rows = self._virtual_marquee_rows(
                settings["lines_a"][0], width, height, self._animation_frame,
                settings["direction"], settings["gap"])
        else:
            source = settings["lines_a"] if self._animation_frame % 2 == 0 \
                else settings["lines_b"]
            rows = [line[:width].ljust(width) for line in source]

        # Compose and commit the complete multi-row frame atomically.
        self.phidget.clear()
        for row_number, row in enumerate(rows[:height]):
            self.phidget.writeText(LCDFont.FONT_5x8, 0, row_number, row)
        self.phidget.flush()
        self.lastText = "\n".join(row.rstrip() for row in rows[:height]).rstrip("\n")

    def _animation_tick(self, generation):
        with self._display_lock:
            if (generation != self._animation_generation or
                    self._animation_mode == "off" or self._state != "attached"):
                return
            try:
                self._animation_frame += 1
                self._render_animation_locked()
                self._schedule_animation_locked(
                    generation, self._animation_settings["interval"])
            except Exception:
                self.logger.error("LCD animation stopped after a write error: device='%s'\n%s",
                                  self.indigoDevice.name, traceback.format_exc())
                self._cancel_animation_locked()
                self.updateIndigoStatus()

    def startAnimation(self, mode, lines_a, lines_b=None, interval=0.4,
                       direction="left", gap=3):
        with self._display_lock:
            self._ensure_attached()
            if self.lcdType != "text":
                raise ValueError("LCD animations currently require a text LCD")
            if mode not in ("marquee", "virtualMarquee", "flash"):
                raise ValueError(
                    "LCD animation mode must be marquee, virtual marquee, or flash")
            interval = float(interval)
            if interval < 0.1 or interval > 60.0:
                raise ValueError("LCD animation interval must be from 0.1 to 60 seconds")
            if direction not in ("left", "right"):
                raise ValueError("LCD marquee direction must be left or right")
            gap = int(gap)
            if gap < 1 or gap > 100:
                raise ValueError("LCD marquee gap must be from 1 to 100 characters")

            height = self.screenHeight
            if mode == "virtualMarquee":
                source = list(lines_a or [])
                normalized_a = [str(source[0] or "") if source else ""]
                normalized_b = []
            else:
                normalized_a = [str(line or "") for line in list(lines_a)[:height]]
                normalized_a.extend([""] * (height - len(normalized_a)))
                normalized_b = [str(line or "") for line in list(lines_b or [])[:height]]
                normalized_b.extend([""] * (height - len(normalized_b)))
            if mode == "flash":
                width = self.screenWidth
                normalized_a = [
                    self._clip_text_row(line, width, "Flash set A", line_number + 1)
                    for line_number, line in enumerate(normalized_a)
                ]
                normalized_b = [
                    self._clip_text_row(line, width, "Flash set B", line_number + 1)
                    for line_number, line in enumerate(normalized_b)
                ]
            self._cancel_animation_locked()
            generation = self._animation_generation
            self._animation_mode = mode
            self._animation_frame = 0
            self._animation_settings = {
                "mode": mode,
                "lines_a": normalized_a,
                "lines_b": normalized_b,
                "interval": interval,
                "direction": direction,
                "gap": gap,
            }
            self._render_animation_locked()
            self._schedule_animation_locked(generation, interval)
            self.updateIndigoStatus()

    def stopAnimation(self):
        with self._display_lock:
            self._cancel_animation_locked()
            self.updateIndigoStatus()

    def clear(self):
        with self._display_lock:
            self._ensure_attached()
            self._cancel_animation_locked()
            self.phidget.clear()
            self.phidget.flush()
            self.lastText = ""
            self.updateIndigoStatus()

    def setBacklight(self, value):
        with self._display_lock:
            self._ensure_attached()
            value = float(value)
            if self._emulatedSleeping:
                minimum = self.phidget.getMinBacklight()
                maximum = self.phidget.getMaxBacklight()
                if value < minimum or value > maximum:
                    raise ValueError(
                        "Backlight %.3f is outside the attached LCD range %.3f–%.3f" %
                        (value, minimum, maximum))
                self._wakeBacklight = value
            else:
                self._set_bounded("Backlight", value,
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
            if sleeping:
                self._cancel_animation_locked()
            if self._supportsSleeping:
                self.phidget.setSleeping(bool(sleeping))
            elif sleeping and not self._emulatedSleeping:
                self._wakeBacklight = self.phidget.getBacklight()
                self.phidget.setBacklight(self.phidget.getMinBacklight())
                self._emulatedSleeping = True
            elif not sleeping and self._emulatedSleeping:
                wake_backlight = (self._wakeBacklight if self._wakeBacklight is not None
                                  else self.backlight)
                self._set_bounded("Backlight", float(wake_backlight),
                                  "getMinBacklight", "getMaxBacklight", "setBacklight")
                self._emulatedSleeping = False
                self._wakeBacklight = None
            self.updateIndigoStatus()

    def updateIndigoStatus(self):
        values = {
            "lcdType": self.lcdType,
            "screenWidth": self.screenWidth,
            "screenHeight": self.screenHeight,
            "backlight": self._read_optional("getBacklight"),
            "contrast": self._read_optional("getContrast"),
            "sleeping": (self._read_optional("getSleeping")
                         if self._supportsSleeping else self._emulatedSleeping),
            "lastText": self.lastText,
            "animationMode": self._animation_mode,
            "animationRunning": self._animation_mode != "off",
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
        states.append(self.indigo_plugin.getDeviceStateDictForStringType(
            "animationMode", "Animation mode", "animationMode"))
        states.append(self.indigo_plugin.getDeviceStateDictForBoolOnOffType(
            "animationRunning", "Animation running", "animationRunning"))
        return states

    def getDeviceDisplayStateId(self):
        return "lastText"
