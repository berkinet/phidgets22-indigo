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
        errors["bridgeCalibrated"] = "Load-cell calibration requires a DAQ1500."
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
    if values.get("bridgeUnits", "kg") not in ("kg", "g", "lb", "N"):
        errors["bridgeUnits"] = "Select kg, g, lb, or N."
    if values.get("bridgeCalibrationSignature") != signature(values):
        errors["bridgeCalibrated"] = "Channel or bridge gain changed. Recalibrate or clear calibration."
    return errors


class BridgeUiMixin:
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
            if operation == "clear":
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
