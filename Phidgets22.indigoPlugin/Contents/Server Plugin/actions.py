# -*- coding: utf-8 -*-

"""Indigo action dispatch and action-configuration UI callbacks."""

import indigo

from lcd import LCDPhidget


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
        # A display action implies that the panel should be visible. This also
        # exits backlight-based sleep emulation before applying its brightness.
        lcd.setSleeping(False)
        lcd.setBacklight(float(action.props.get("backlight", 1.0)))
        lcd.setContrast(float(action.props.get("contrast", 0.5)))
        if mode == "static":
            if line_count:
                lcd.writeLines(lines_a)
            else:
                lcd.writeText(
                    self.substitute(action.props.get("graphicText", "")),
                    int(action.props.get("graphicX", 0)),
                    int(action.props.get("graphicY", 0)))
        else:
            lcd.startAnimation(
                mode=mode,
                lines_a=lines_a,
                lines_b=lines_b,
                interval=float(action.props.get(
                    "marqueeInterval" if mode in ("marquee", "virtualMarquee")
                    else "flashInterval",
                    0.4 if mode in ("marquee", "virtualMarquee") else 1.0)),
                direction=action.props.get("marqueeDirection", "left"),
                gap=int(action.props.get("marqueeGap", 3)))

    def lcdStopAnimation(self, action, device=None):
        self._lcdForAction(action, device).stopAnimation()

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

    def getActionConfigUiValues(self, pluginProps, typeId, deviceId):
        errors = indigo.Dict()
        if typeId == "lcdStartAnimation":
            line_count = self._lcdActionLineCount(deviceId)
            mode = pluginProps.get("animationMode", "static")
            pluginProps["lineCount"] = str(line_count)
            pluginProps["animationMode"] = mode
            pluginProps["animationLayout"] = self._lcdDisplayLayout(mode, line_count)
            self._updateVirtualTextStatus(pluginProps)
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
        return self._updateVirtualTextStatus(valuesDict)

    def validateActionConfigUi(self, valuesDict, typeId, deviceId):
        errors = indigo.Dict()
        if typeId == "lcdStartAnimation":
            line_count = int(valuesDict.get("lineCount", 0))
            mode = valuesDict.get("animationMode", "static")
            for field in ("backlight", "contrast"):
                try:
                    value = float(valuesDict.get(field, ""))
                    if value < 0.0 or value > 1.0:
                        raise ValueError
                    valuesDict[field] = str(value)
                except (TypeError, ValueError):
                    errors[field] = "Enter a value from 0.0 to 1.0."
            if mode == "static" and line_count == 0:
                for field, label in (("graphicX", "X"), ("graphicY", "Y")):
                    try:
                        value = int(valuesDict.get(field, "0"))
                        if value < 0:
                            raise ValueError
                        valuesDict[field] = str(value)
                    except (TypeError, ValueError):
                        errors[field] = (
                            "%s must be a whole number of zero or greater." % label)
            if mode != "static" and line_count == 0:
                errors["animationMode"] = (
                    "LCD animation currently requires a text LCD.")
            if mode in ("marquee", "virtualMarquee", "flash"):
                interval_field = (
                    "marqueeInterval" if mode in ("marquee", "virtualMarquee")
                    else "flashInterval")
                try:
                    interval = float(valuesDict.get(interval_field, ""))
                    if interval < 0.1 or interval > 60.0:
                        raise ValueError
                    valuesDict[interval_field] = str(interval)
                except (TypeError, ValueError):
                    errors[interval_field] = (
                        "Enter an interval from 0.1 to 60 seconds.")
                if mode in ("marquee", "virtualMarquee"):
                    try:
                        gap = int(valuesDict.get("marqueeGap", "3"))
                        if gap < 1 or gap > 100:
                            raise ValueError
                        valuesDict["marqueeGap"] = str(gap)
                    except (TypeError, ValueError):
                        errors["marqueeGap"] = (
                            "Enter a gap from 1 to 100 characters.")
            if (mode == "virtualMarquee" and
                    any(character in valuesDict.get("virtualText", "")
                        for character in ("\r", "\n"))):
                errors["virtualText"] = (
                    "Virtual single-line marquee text must be one line.")

        if errors:
            errors["showAlertText"] = "Correct the LCD action settings."
            return (False, valuesDict, errors)
        return (True, valuesDict)
