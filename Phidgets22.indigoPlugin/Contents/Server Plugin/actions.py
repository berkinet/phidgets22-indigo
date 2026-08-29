# -*- coding: utf-8 -*-

"""Indigo action dispatch and action-configuration UI callbacks."""

import re

import indigo

from lcd import LCDPhidget
from formula import Formula
from config_util import bounded_float, bounded_int


SUBSTITUTION_PATTERN = re.compile(
    r"%%(?:v:\d+|d:\d+:[^%]+)%%")


class ActionsMixin(object):
    def actionControlDevice(self, action, device):
        if device.id in self.activePhidgets:
            return self.activePhidgets[device.id].actionControlDevice(action)
        raise Exception("Unexpected device: %s" % device.id)

    def actionControlSensor(self, action, device):
        if device.id in self.activePhidgets:
            return self.activePhidgets[device.id].actionControlSensor(action)
        raise Exception("Unexpected device: %s" % device.id)

    def _lcdForAction(self, action, device=None):
        device_id = getattr(action, "deviceId", None)
        if not device_id and device is not None:
            device_id = getattr(device, "id", None)
        try:
            device_id = int(device_id)
        except (TypeError, ValueError):
            raise ValueError("LCD action has no target device")

        lcd = self.activePhidgets.get(device_id)
        if lcd is None or not isinstance(lcd, LCDPhidget):
            device_name = getattr(device, "name", None)
            if not device_name:
                try:
                    device_name = indigo.devices[device_id].name
                except (AttributeError, IndexError, KeyError, TypeError):
                    device_name = str(device_id)
            raise ValueError("LCD device '%s' is not active" % device_name)
        return lcd

    def lcdClear(self, action, device=None):
        self._lcdForAction(action, device).clear()

    def lcdSleep(self, action, device=None):
        self._lcdForAction(action, device).setSleeping(True)

    def lcdWake(self, action, device=None):
        self._lcdForAction(action, device).setSleeping(False)

    def lcdSetDisplay(self, action, device=None):
        line_count = int(action.props.get("lineCount", 0))
        mode = action.props.get("animationMode", "static")
        if mode == "virtualMarquee":
            virtual_text = self.substitute(action.props.get("virtualText", ""))
            virtual_text = virtual_text.replace("\r\n", " ").replace(
                "\r", " ").replace("\n", " ")
            lines_a = [virtual_text]
        else:
            lines_a = [
                self.substitute(action.props.get(
                    "animationLine%d" % line_number, ""))
                for line_number in range(1, line_count + 1)
            ]
        lines_b = [
            self.substitute(action.props.get("alternateLine%d" % line_number, ""))
            for line_number in range(1, line_count + 1)
        ]
        lcd = self._lcdForAction(action, device)
        backlight = float(action.props.get("backlight", 1.0))
        contrast = float(action.props.get("contrast", 0.5))
        overflow_behavior = action.props.get(
            "staticOverflowBehavior", "truncate")
        overflow_interval = float(action.props.get(
            "overflowMarqueeInterval", 0.4))
        overflow_direction = action.props.get(
            "overflowMarqueeDirection", "left")
        overflow_gap = int(action.props.get("overflowMarqueeGap", 3))
        animation_interval = float(action.props.get(
            "marqueeInterval" if mode in ("marquee", "virtualMarquee")
            else "flashInterval",
            0.4 if mode in ("marquee", "virtualMarquee") else 1.0))
        animation_direction = action.props.get("marqueeDirection", "left")
        animation_gap = int(action.props.get("marqueeGap", 3))
        graphic_text = self.substitute(action.props.get("graphicText", ""))
        graphic_font = int(action.props.get("graphicFont", 4))
        graphic_lines = [
            self.substitute(action.props.get("graphicLine%d" % number, ""))
            for number in range(1, 9)
        ]
        graphic_content = action.props.get("graphicContentType", "text")
        formula_expression = action.props.get("formulaExpression", "sin(x)")
        donut_interval = float(action.props.get("donutInterval", 0.15))
        graphic_x = int(action.props.get("graphicX", 0))
        graphic_y = int(action.props.get("graphicY", 0))

        def apply_display():
            # A display action implies that the panel should be visible. This
            # exits backlight-based sleep emulation before setting brightness.
            lcd.setSleeping(False)
            lcd.setBacklight(backlight)
            lcd.setContrast(contrast)
            if mode == "static":
                if line_count:
                    screen_width = getattr(lcd, "screenWidth", None)
                    overflowing = any(
                        screen_width is not None and len(line) > screen_width
                        for line in lines_a)
                    if overflowing and overflow_behavior == "reject":
                        raise ValueError(
                            "Substituted static LCD text exceeds the "
                            "%d-character row width" % screen_width)
                    if overflowing and overflow_behavior == "marquee":
                        lcd.startAnimation(
                            mode="marquee",
                            lines_a=lines_a,
                            lines_b=[""] * line_count,
                            interval=overflow_interval,
                            direction=overflow_direction,
                            gap=overflow_gap)
                    else:
                        lcd.writeLines(lines_a)
                else:
                    if graphic_content == "formula":
                        lcd.plotFormula(
                            formula_expression,
                            action.props.get("formulaXMin", "-6.283185307"),
                            action.props.get("formulaXMax", "6.283185307"),
                            action.props.get("formulaYMin", "-1.2"),
                            action.props.get("formulaYMax", "1.2"),
                            str(action.props.get("formulaShowAxes", True)).lower()
                            in ("true", "1", "yes", "on"),
                            action.props.get("formulaStyle", "line"))
                    elif graphic_content == "donut":
                        lcd.startDonut(donut_interval)
                    elif any(graphic_lines):
                        lcd.writeGraphicLines(graphic_lines, graphic_font)
                    else:
                        # Preserve coordinate-based actions saved before the
                        # multi-line graphic text UI was introduced.
                        lcd.writeText(graphic_text, graphic_x, graphic_y)
            else:
                lcd.startAnimation(
                    mode=mode,
                    lines_a=lines_a,
                    lines_b=lines_b,
                    interval=animation_interval,
                    direction=animation_direction,
                    gap=animation_gap)

        lcd.runDisplayWhenAttached(apply_display)

    def lcdStopAnimation(self, action, device=None):
        self._lcdForAction(action, device).turnOff()

    def _lcdActionLineCount(self, deviceId):
        try:
            device = indigo.devices[int(deviceId)]
            if str(device.states.get("lcdType", "")) == "text":
                height = int(device.states.get("screenHeight", 0))
                if 1 <= height <= 4:
                    return height
            screen_size = int(device.pluginProps.get("lcdScreenSize", 1))
            return {
                2: 1, 3: 2, 4: 1, 5: 2, 6: 4, 7: 2,
                8: 4, 9: 2, 10: 1, 11: 2, 12: 4,
            }.get(screen_size, 0)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            return 0

    def _lcdDisplayLayout(self, mode, line_count):
        if line_count:
            return "%s%d" % (mode, line_count)
        return "static0" if mode == "static" else "unsupported"

    def _graphicContentLayout(self, line_count, content="text"):
        if line_count:
            return "hidden"
        return content if content in ("text", "formula", "donut") else "text"

    def _graphicTextLayout(self, font, content="text", line_count=0):
        if line_count or content != "text":
            return "hidden"
        return {4: "graphic8", 3: "graphic6", 5: "graphic5"}.get(
            int(font), "graphic8")

    def _updateVirtualTextStatus(self, values):
        text = str(values.get("virtualText", "") or "")
        if not text:
            values["virtualTextStatus"] = "∅ empty"
        else:
            line_count = (len(text.splitlines())
                          if "\r" in text or "\n" in text else 1)
            if line_count > 1:
                values["virtualTextStatus"] = (
                    "⚠ %d characters stored across %d lines" %
                    (len(text), line_count))
            else:
                values["virtualTextStatus"] = (
                    "→ %d character%s stored" %
                    (len(text), "" if len(text) == 1 else "s"))
        return values

    def _updateStaticOverflowLayout(self, values, mode, line_count):
        contains_substitution = (
            mode == "static" and line_count > 0 and
            any(SUBSTITUTION_PATTERN.search(str(values.get(
                "animationLine%d" % line_number, "") or ""))
                for line_number in range(1, line_count + 1)))
        if not contains_substitution:
            values["staticOverflowLayout"] = "hidden"
        elif values.get("staticOverflowBehavior", "truncate") == "marquee":
            values["staticOverflowLayout"] = "marquee"
        else:
            values["staticOverflowLayout"] = "show"
        return values

    def getActionConfigUiValues(self, pluginProps, typeId, deviceId):
        errors = indigo.Dict()
        if typeId == "lcdStartAnimation":
            line_count = self._lcdActionLineCount(deviceId)
            mode = pluginProps.get("animationMode", "static")
            pluginProps["lineCount"] = str(line_count)
            pluginProps["animationMode"] = mode
            pluginProps["animationLayout"] = self._lcdDisplayLayout(mode, line_count)
            graphic_font = int(pluginProps.get("graphicFont", 4))
            pluginProps["graphicFont"] = str(graphic_font)
            pluginProps["graphicContentType"] = pluginProps.get(
                "graphicContentType", "text")
            pluginProps["graphicContentLayout"] = self._graphicContentLayout(
                line_count, pluginProps["graphicContentType"])
            pluginProps["graphicLineLayout"] = self._graphicTextLayout(
                graphic_font, pluginProps["graphicContentType"], line_count)
            if (line_count == 0 and not pluginProps.get("graphicLine1") and
                    pluginProps.get("graphicText")):
                pluginProps["graphicLine1"] = pluginProps["graphicText"]
            self._updateVirtualTextStatus(pluginProps)
            for field, default in (
                    ("staticOverflowBehavior", "truncate"),
                    ("overflowMarqueeDirection", "left"),
                    ("overflowMarqueeGap", "3"),
                    ("overflowMarqueeInterval", "0.4")):
                if field not in pluginProps:
                    pluginProps[field] = default
            self._updateStaticOverflowLayout(pluginProps, mode, line_count)
            try:
                device = indigo.devices[int(deviceId)]
                if "backlight" not in pluginProps:
                    pluginProps["backlight"] = str(device.states.get(
                        "backlight", device.pluginProps.get("lcdBacklight", 1.0)))
                if "contrast" not in pluginProps:
                    pluginProps["contrast"] = str(device.states.get(
                        "contrast", device.pluginProps.get("lcdContrast", 0.5)))
            except (AttributeError, IndexError, KeyError, TypeError, ValueError):
                if "backlight" not in pluginProps:
                    pluginProps["backlight"] = "1.0"
                if "contrast" not in pluginProps:
                    pluginProps["contrast"] = "0.5"
        return (pluginProps, errors)

    def lcdAnimationConfigChanged(self, valuesDict, typeId, deviceId):
        line_count = self._lcdActionLineCount(deviceId)
        mode = valuesDict.get("animationMode", "static")
        valuesDict["lineCount"] = str(line_count)
        valuesDict["animationLayout"] = self._lcdDisplayLayout(mode, line_count)
        graphic_font = int(valuesDict.get("graphicFont", 4))
        valuesDict["graphicContentType"] = valuesDict.get(
            "graphicContentType", "text")
        valuesDict["graphicContentLayout"] = self._graphicContentLayout(
            line_count, valuesDict["graphicContentType"])
        valuesDict["graphicLineLayout"] = self._graphicTextLayout(
            graphic_font, valuesDict["graphicContentType"], line_count)
        self._updateVirtualTextStatus(valuesDict)
        return self._updateStaticOverflowLayout(valuesDict, mode, line_count)

    def _validateGraphicAction(self, values, errors, line_count, mode):
        content = values.get("graphicContentType", "text")
        if content not in ("text", "formula", "donut"):
            errors["graphicContentType"] = (
                "Select Text page, Formula graph, or Spinning donut.")
        try:
            font = bounded_int(values.get("graphicFont", 4), choices=(3, 4, 5))
            values["graphicFont"] = str(font)
            values["graphicContentLayout"] = self._graphicContentLayout(
                line_count, content)
            values["graphicLineLayout"] = self._graphicTextLayout(
                font, content, line_count)
        except (TypeError, ValueError):
            errors["graphicFont"] = "Select a supported LCD font."
        if mode != "static" or line_count:
            return
        if content == "formula":
            try:
                Formula(values.get("formulaExpression", "")).validateOutputType(
                    "number")
            except ValueError as error:
                errors["formulaExpression"] = str(error)
            ranges = {}
            for field in ("formulaXMin", "formulaXMax", "formulaYMin", "formulaYMax"):
                try:
                    ranges[field] = bounded_float(values.get(field, ""))
                    values[field] = str(ranges[field])
                except (TypeError, ValueError):
                    errors[field] = "Enter a finite number."
            if ranges.get("formulaXMin", 0) >= ranges.get("formulaXMax", 1):
                errors["formulaXMin"] = "X minimum must be less than X maximum."
            if ranges.get("formulaYMin", 0) >= ranges.get("formulaYMax", 1):
                errors["formulaYMin"] = "Y minimum must be less than Y maximum."
            if values.get("formulaStyle", "line") not in ("line", "pixels"):
                errors["formulaStyle"] = "Select Connected line or Pixels."
        elif content == "donut":
            try:
                values["donutInterval"] = str(bounded_float(
                    values.get("donutInterval", "0.15"), 0.1, 2.0))
            except (TypeError, ValueError):
                errors["donutInterval"] = "Enter an interval from 0.1 to 2 seconds."

    def _validateLCDLevelsAndPosition(self, values, errors, line_count, mode):
        for field in ("backlight", "contrast"):
            try:
                values[field] = str(bounded_float(values.get(field, ""), 0.0, 1.0))
            except (TypeError, ValueError):
                errors[field] = "Enter a value from 0.0 to 1.0."
        if mode == "static" and line_count == 0:
            for field, label in (("graphicX", "X"), ("graphicY", "Y")):
                try:
                    values[field] = str(bounded_int(values.get(field, "0"), 0))
                except (TypeError, ValueError):
                    errors[field] = "%s must be zero or greater." % label

    def _validateLCDAnimation(self, values, errors, line_count, mode):
        has_substitution = (
            mode == "static" and line_count > 0 and
            any(SUBSTITUTION_PATTERN.search(str(values.get(
                "animationLine%d" % number, "") or ""))
                for number in range(1, line_count + 1)))
        if has_substitution:
            behavior = values.get("staticOverflowBehavior", "truncate")
            if behavior not in ("truncate", "marquee", "reject"):
                errors["staticOverflowBehavior"] = "Select a valid overflow behavior."
            elif behavior == "marquee":
                if values.get("overflowMarqueeDirection", "left") not in ("left", "right"):
                    errors["overflowMarqueeDirection"] = "Select Left or Right."
                for field, minimum, maximum, message, cast in (
                        ("overflowMarqueeGap", 1, 100,
                         "Enter a gap from 1 to 100 characters.", bounded_int),
                        ("overflowMarqueeInterval", 0.1, 60.0,
                         "Enter an interval from 0.1 to 60 seconds.", bounded_float)):
                    try:
                        values[field] = str(cast(values.get(field, ""), minimum, maximum))
                    except (TypeError, ValueError):
                        errors[field] = message
        if mode != "static" and line_count == 0:
            errors["animationMode"] = "LCD animation currently requires a text LCD."
        if mode in ("marquee", "virtualMarquee", "flash"):
            interval_field = ("marqueeInterval" if mode != "flash" else "flashInterval")
            try:
                values[interval_field] = str(bounded_float(
                    values.get(interval_field, ""), 0.1, 60.0))
            except (TypeError, ValueError):
                errors[interval_field] = "Enter an interval from 0.1 to 60 seconds."
            if mode in ("marquee", "virtualMarquee"):
                try:
                    values["marqueeGap"] = str(bounded_int(
                        values.get("marqueeGap", "3"), 1, 100))
                except (TypeError, ValueError):
                    errors["marqueeGap"] = "Enter a gap from 1 to 100 characters."
        if (mode == "virtualMarquee" and
                any(character in values.get("virtualText", "")
                    for character in ("\r", "\n"))):
            errors["virtualText"] = "Virtual single-line marquee text must be one line."

    def validateActionConfigUi(self, valuesDict, typeId, deviceId):
        errors = indigo.Dict()
        if typeId != "lcdStartAnimation":
            return (True, valuesDict)
        for field in (["virtualText", "graphicText"] +
                      ["graphicLine%d" % line for line in range(1, 9)] +
                      ["animationLine%d" % line for line in range(1, 5)] +
                      ["alternateLine%d" % line for line in range(1, 5)]):
            valuesDict[field] = str(valuesDict.get(field, "") or "")
        line_count = int(valuesDict.get("lineCount", 0))
        mode = valuesDict.get("animationMode", "static")
        self._validateGraphicAction(valuesDict, errors, line_count, mode)
        self._validateLCDLevelsAndPosition(valuesDict, errors, line_count, mode)
        self._validateLCDAnimation(valuesDict, errors, line_count, mode)
        if errors:
            errors["showAlertText"] = "Correct the LCD action settings."
            return (False, valuesDict, errors)
        return (True, valuesDict)
