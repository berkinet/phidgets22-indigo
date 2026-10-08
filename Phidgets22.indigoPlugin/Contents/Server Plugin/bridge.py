"""DAQ1500 calibration math and staged configuration callbacks."""
import json
import math

from config_util import saved_bool
from runtime_registry import registry_for


def finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Enter a finite number")
    return value


def calibration(zero, loaded, weight):
    zero, loaded, weight = finite(zero), finite(loaded), finite(weight)
    if weight <= 0:
        raise ValueError("Known weight must be greater than zero")
    if loaded == zero:
        raise ValueError("Loaded and unloaded readings must differ")
    return finite(weight / (loaded - zero)), -zero


def signature(values):
    """Calibration belongs to a single saved channel and hardware gain."""
    return json.dumps([str(values.get(key, "")) for key in
                       ("serverName", "serialNumber", "hubPort", "channel")] +
                      [int(values.get("bridgeGain", 128))])


def validate(values):
    errors = {}
    if not saved_bool(values.get("bridgeCalibrated", False)):
        return errors
    if not saved_bool(values.get("isDAQ1500", False)):
        errors["discoveredServer"] = ("This calibration belongs to a DAQ1500. Select the bridge again, "
                                     "click Clear calibration, then select the new device and Save.")
    if saved_bool(values.get("useCustomFormula", False)):
        errors["useCustomFormula"] = "Choose load-cell calibration or a custom formula."
    for field in ("bridgeScale", "bridgeOffset"):
        try:
            result = finite(values.get(field, ""))
            if field == "bridgeScale" and result == 0:
                raise ValueError("Calibration gain must not be zero")
        except (ValueError, TypeError, OverflowError) as error:
            errors[field] = str(error)
    if values.get("bridgeCalibrationUnits") != values.get("bridgeUnits", "kg"):
        errors["bridgeUnits"] = "Units changed. Recalibrate using a known weight in the new units."
    if values.get("bridgeUnits", "kg") not in ("kg", "g", "lb", "oz", "N"):
        errors["bridgeUnits"] = "Select kg, g, lb, oz, or N."
    if values.get("bridgeCalibrationSignature") != signature(values):
        field = "bridgeGain" if saved_bool(values.get("isDAQ1500", False)) else "discoveredServer"
        errors[field] = ("Connection or bridge gain changed. If you moved the same scale without changing "
                         "bridge gain or units, click Keep calibration for moved scale, then Save. "
                         "For a different load cell or gain, clear calibration and recalibrate.")
    return errors


def nonnegative(value):
    result = finite(value)
    if result < 0:
        raise ValueError("Enter a non-negative change threshold")
    return result


def trigger_scale(values):
    if not saved_bool(values.get("bridgeCalibrated", False)):
        raise ValueError("Weight change thresholds require calibration")
    scale = abs(finite(values.get("bridgeScale", 0)))
    if scale == 0:
        raise ValueError("Calibration gain must not be zero")
    return scale


def ratio_trigger(values):
    mode = values.get("bridgeTriggerMode", "ratio")
    if mode == "ratio":
        return nonnegative(values.get("voltageRatioChangeTrigger", 0))
    if mode != "weight":
        raise ValueError("Select voltage ratio or weight change units")
    weight = nonnegative(values.get("bridgeWeightChangeTrigger", ""))
    ratio = finite(weight / trigger_scale(values))
    if weight > 0 and ratio == 0:
        raise ValueError("Weight threshold is too small to represent in V/V")
    return ratio


def switch_trigger(values, previous, target):
    """Stage equivalent values; never mutate the source on failed conversion."""
    if target not in ("ratio", "weight") or previous not in ("ratio", "weight"):
        raise ValueError("Select voltage ratio or weight change units")
    if target == "weight":
        scale = trigger_scale(values)
        if previous == "ratio":
            ratio = nonnegative(values.get("voltageRatioChangeTrigger", 0))
            weight = finite(ratio * scale)
            if ratio > 0 and weight == 0:
                raise ValueError("V/V threshold is too small to represent in weight units")
            values["bridgeWeightChangeTrigger"] = repr(weight)
    elif previous == "weight":
        proposed = dict(values)
        proposed["bridgeTriggerMode"] = "weight"
        values["voltageRatioChangeTrigger"] = repr(ratio_trigger(proposed))
    values["bridgeTriggerMode"] = target
    values["bridgeTriggerPreviousMode"] = target


def initialize_trigger(values):
    mode = values.get("bridgeTriggerMode")
    if mode is None:
        # Old configurations only stored V/V. Change the display, not sensitivity.
        mode = "weight" if saved_bool(values.get("bridgeCalibrated", False)) else "ratio"
        switch_trigger(values, "ratio", mode)
    elif not saved_bool(values.get("bridgeCalibrated", False)):
        # A valid clear operation already converted to V/V. Ignore stale UI mode.
        values["bridgeTriggerMode"] = "ratio"
        mode = "ratio"
    values["bridgeTriggerPreviousMode"] = mode


class BridgeUiMixin:
    def initializeBridgeTrigger(self, values):
        try:
            initialize_trigger(values)
        except Exception as error:
            values["bridgeTriggerMode"] = "ratio"
            values["bridgeTriggerPreviousMode"] = "ratio"
            values["bridgeCalibrationStatus"] = str(error).replace("\n", " ")
            self.logger.error("Unable to initialize bridge threshold: %s",
                              values["bridgeCalibrationStatus"])
        return values

    def getBridgeTriggerUnits(self, filter="", valuesDict=None, typeId="", targetId=0):
        values = valuesDict if valuesDict is not None else {}
        choices = [("ratio", "Voltage ratio (V/V)")]
        if saved_bool(values.get("bridgeCalibrated", False)):
            choices.append(("weight", "Weight (%s)" % values.get("bridgeUnits", "kg")))
        return choices

    def bridgeTriggerUnitsChanged(self, valuesDict, typeId, devId):
        previous = valuesDict.get("bridgeTriggerPreviousMode", "ratio")
        try:
            switch_trigger(valuesDict, previous, valuesDict.get("bridgeTriggerMode", "ratio"))
        except Exception as error:
            valuesDict["bridgeTriggerMode"] = previous
            valuesDict["bridgeCalibrationStatus"] = str(error).replace("\n", " ")
            self.logger.error("Bridge threshold conversion failed for device %s: %s",
                              devId, valuesDict["bridgeCalibrationStatus"])
        return valuesDict

    def _bridgeReading(self, values, dev_id):
        from voltageratioinput import VoltageRatioInputPhidget
        runtime = registry_for(self).get(int(dev_id))
        if not isinstance(runtime, VoltageRatioInputPhidget):
            raise ValueError("Save this device first, then reopen configuration to calibrate")
        if signature(values) != signature(runtime.indigoDevice.pluginProps):
            raise ValueError("Save the channel and bridge gain first, then reopen configuration")
        if not saved_bool(values.get("bridgeEnabled", True)):
            raise ValueError("Enable the bridge and save before calibrating")
        return runtime.readBridgeRatio()

    def _bridgeOperation(self, values, dev_id, operation):
        try:
            if operation == "keep":
                if not saved_bool(values.get("bridgeCalibrated", False)):
                    raise ValueError("There is no saved calibration to keep")
                previous = json.loads(values.get("bridgeCalibrationSignature", ""))
                if not isinstance(previous, list) or len(previous) != 5:
                    raise ValueError("Previous calibration connection is invalid; recalibrate")
                if previous[4] != int(values.get("bridgeGain", 128)):
                    raise ValueError("Bridge gain changed; restore the calibrated gain or recalibrate")
                proposed = dict(values)
                proposed["bridgeCalibrationSignature"] = signature(values)
                errors = validate(proposed)
                if errors:
                    raise ValueError("; ".join(errors.values()))
                values["bridgeCalibrationSignature"] = proposed["bridgeCalibrationSignature"]
                values["bridgeZeroSignature"] = ""
                values["bridgeCalibrationStatus"] = (
                    "Existing calibration and tare retained for the moved scale. Click Save to apply.")
                return values
            if operation == "clear":
                switch_trigger(values, values.get("bridgeTriggerMode", "ratio"), "ratio")
                values["bridgeCalibrated"] = False
                values["bridgeCalibrationSignature"] = ""
                values["bridgeZeroSignature"] = ""
                values["bridgeCalibrationStatus"] = "Calibration cleared; click Save to apply."
                return values
            ratio = self._bridgeReading(values, dev_id)
            if operation == "zero":
                values["bridgeZeroRatio"] = repr(ratio)
                values["bridgeZeroSignature"] = signature(values)
                values["bridgeCalibrationStatus"] = "Zero captured. Apply a known weight, let it settle, enter its value, then click Calibrate."
            elif operation == "calibrate":
                if values.get("bridgeZeroSignature") != signature(values):
                    raise ValueError("Capture the unloaded zero for this channel and gain first")
                scale, offset = calibration(values.get("bridgeZeroRatio"), ratio,
                                            values.get("bridgeKnownWeight"))
                proposed = dict(values)
                proposed["bridgeScale"] = repr(scale)
                proposed["bridgeCalibrated"] = True
                if not saved_bool(values.get("bridgeCalibrated", False)):
                    switch_trigger(proposed, "ratio", "weight")
                else:
                    ratio_trigger(proposed)  # Revalidate against the new scale before staging.
                for key in ("bridgeTriggerMode", "bridgeTriggerPreviousMode", "bridgeWeightChangeTrigger"):
                    if key in proposed:
                        values[key] = proposed[key]
                values["bridgeScale"] = repr(scale)
                values["bridgeOffset"] = repr(offset)
                values["bridgeCalibrationUnits"] = values.get("bridgeUnits", "kg")
                values["bridgeCalibrated"] = True
                values["bridgeCalibrationSignature"] = signature(values)
                values["bridgeCalibrationStatus"] = "Calibration ready. Click Save to apply; Cancel discards these changes."
            elif operation == "tare":
                errors = validate(values)
                if not saved_bool(values.get("bridgeCalibrated", False)) or errors:
                    raise ValueError("Calibrate this channel before taring")
                values["bridgeOffset"] = repr(-ratio)
                values["bridgeCalibrationStatus"] = "Tare ready. Click Save to apply; Cancel discards it."
        except Exception as error:
            message = str(error).replace("\n", " ")
            values["bridgeCalibrationStatus"] = message
            self.logger.error("Bridge %s failed for device %s: %s", operation, dev_id, message)
        return values

    def bridgeCaptureZero(self, valuesDict, typeId, devId):
        return self._bridgeOperation(valuesDict, devId, "zero")

    def bridgeCalibrate(self, valuesDict, typeId, devId):
        return self._bridgeOperation(valuesDict, devId, "calibrate")

    def bridgeTare(self, valuesDict, typeId, devId):
        return self._bridgeOperation(valuesDict, devId, "tare")

    def bridgeClearCalibration(self, valuesDict, typeId, devId):
        return self._bridgeOperation(valuesDict, devId, "clear")

    def bridgeKeepCalibration(self, valuesDict, typeId, devId):
        return self._bridgeOperation(valuesDict, devId, "keep")
