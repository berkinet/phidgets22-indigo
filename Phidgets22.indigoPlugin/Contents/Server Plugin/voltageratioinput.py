# -*- coding: utf-8 -*-
import indigo

from Phidget22.Devices.VoltageRatioInput import VoltageRatioInput
from Phidget22.DeviceID import DeviceID
from Phidget22.BridgeGain import BridgeGain
from Phidget22.VoltageRatioSensorType import VoltageRatioSensorType

from phidget import PhidgetBase, PeripheralUnavailableError
from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException
from formula import Formula
from config_util import saved_bool
from bridge import finite, validate as validate_bridge

import sensortypes

class VoltageRatioInputPhidget(PhidgetBase):
    NUMERIC_DISPLAY = True
    def __init__(self, sensorType, dataInterval, voltageRatioChangeTrigger, sensorValueChangeTrigger, customState, customFormula, *args, **kwargs):
        self.bridgeSettings = kwargs.pop("bridgeSettings", {})
        self.bridgeEnabled = saved_bool(self.bridgeSettings.get("bridgeEnabled", True))
        self.bridgeCalibrated = saved_bool(self.bridgeSettings.get("bridgeCalibrated", False))
        if self.bridgeCalibrated:
            errors = validate_bridge(self.bridgeSettings)
            if errors:
                raise ValueError("Invalid bridge calibration: " + "; ".join(errors.values()))
        self.bridgeScale = finite(self.bridgeSettings.get("bridgeScale", 1)) if self.bridgeCalibrated else 1
        self.bridgeOffset = finite(self.bridgeSettings.get("bridgeOffset", 0)) if self.bridgeCalibrated else 0
        self.bridgeUnits = self.bridgeSettings.get("bridgeUnits", "kg")
        self._isBridge = False
        self._bridgeConfigured = False
        self._bridgeReadingError = "Waiting for a fresh bridge reading"
        self.bridgeGain = int(kwargs.pop("bridgeGain", 128))
        self.customOutputType = kwargs.pop("customOutputType", "number")
        super(VoltageRatioInputPhidget, self).__init__(phidget=VoltageRatioInput(), *args, **kwargs)
        self.sensorType = sensorType
        self.dataInterval = dataInterval
        self.voltageRatioChangeTrigger = voltageRatioChangeTrigger
        self.sensorValueChangeTrigger = sensorValueChangeTrigger
        self.customState = customState
        self.customFormula = customFormula
        self.formula = (Formula(customFormula)
                        if customState and customFormula else None)
        if self.formula is not None:
            self.formula.validateOutputType(self.customOutputType)

        self.sensorUnit = sensortypes.getVoltageRatioSensorUnit(sensorType)
        (self.sensorStateName, self.sensorSymbol) = sensortypes.getNameAndSymbol(self.sensorUnit)

    def suppressSaturationErrors(self):
        return (self.sensorType == VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO and
                saved_bool(self.indigoDevice.pluginProps.get(
                    "suppressSaturationErrors", False)))

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)
        self.phidget.setOnVoltageRatioChangeHandler(self.setOnVoltageRatioChangeHandler)
        self.phidget.setOnSensorChangeHandler(self.onSensorChangeHandler)

    def onErrorHandler(self, ph, errorCode, errorString):
        if getattr(self, "_isBridge", False):
            self._bridgeReadingError = str(errorString).replace("\n", " ")
        super().onErrorHandler(ph, errorCode, errorString)

    def configureAttachedPhidget(self, ph):
        self._bridgeConfigured = False
        is_bridge = ph.getDeviceID() == DeviceID.PHIDID_DAQ1500
        self._isBridge = is_bridge
        if self.bridgeCalibrated and not is_bridge:
            raise ValueError("Load-cell calibration requires a DAQ1500")
        def setup(method, *args):
            try:
                return getattr(ph, method)(*args)
            except Exception as error:
                if not is_bridge or (isinstance(error, PhidgetException) and
                                     error.code == ErrorCode.EPHIDGET_NOTATTACHED):
                    raise
                raise PeripheralUnavailableError("DAQ1500 %s failed: %s" %
                    (method, str(error).replace("\n", " "))) from None

        if is_bridge:
            self._bridgeReadingError = "Waiting for a fresh bridge reading"
            if self.sensorType != VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO:
                raise ValueError("DAQ1500 requires the generic Voltage Ratio sensor type")
            gains = {1: BridgeGain.BRIDGE_GAIN_1, 2: BridgeGain.BRIDGE_GAIN_2,
                     64: BridgeGain.BRIDGE_GAIN_64, 128: BridgeGain.BRIDGE_GAIN_128}
            if self.bridgeGain not in gains:
                raise ValueError("DAQ1500 bridge gain must be 1, 2, 64, or 128")
            setup("setBridgeGain", gains[self.bridgeGain])

        newDataInterval = self.checkValueRange("dataInterval", value=self.dataInterval, minValue=setup("getMinDataInterval"), maxValue=setup("getMaxDataInterval"))
        if newDataInterval is None:
            setup("setDataInterval", PhidgetBase.PHIDGET_DEFAULT_DATA_INTERVAL)
        else:
            setup("setDataInterval", newDataInterval)

        if not is_bridge:
            self.phidget.setSensorType(self.sensorType)

        newVoltageRatioChangeTrigger = self.checkValueRange(
            fieldname="voltageRatioChangeTrigger", value=self.voltageRatioChangeTrigger,
                minValue=setup("getMinVoltageRatioChangeTrigger"),
            maxValue=setup("getMaxVoltageRatioChangeTrigger"))
        if newVoltageRatioChangeTrigger is not None:
            setup("setVoltageRatioChangeTrigger", newVoltageRatioChangeTrigger)

        if not is_bridge:
            self.phidget.setSensorValueChangeTrigger(self.sensorValueChangeTrigger)
        else:
            setup("setBridgeEnabled", self.bridgeEnabled)
            self._bridgeConfigured = True


    def readBridgeRatio(self):
        if self._state != "attached" or not self._isBridge or not self._bridgeConfigured:
            raise ValueError("The DAQ1500 must be attached before calibrating")
        if not self.bridgeEnabled or not self.phidget.getBridgeEnabled():
            raise ValueError("Enable the bridge before calibrating")
        if self._bridgeReadingError:
            raise ValueError(self._bridgeReadingError + "; wait for a valid reading (use change trigger 0)")
        expected = {1: BridgeGain.BRIDGE_GAIN_1, 2: BridgeGain.BRIDGE_GAIN_2,
                    64: BridgeGain.BRIDGE_GAIN_64, 128: BridgeGain.BRIDGE_GAIN_128}[self.bridgeGain]
        if self.phidget.getBridgeGain() != expected:
            raise ValueError("Hardware gain changed; restart this device before calibrating")
        return finite(self.phidget.getVoltageRatio())

    def setOnVoltageRatioChangeHandler(self, ph, voltageRatio):
        try:
            if self._isBridge and (not self.bridgeEnabled or not self._bridgeConfigured):
                return
            voltageRatio = finite(voltageRatio)
            self._bridgeReadingError = None
            self.updateStateOnServer("voltageRatio", value=voltageRatio, decimalPlaces=self.decimalPlaces)
            if self._isBridge and self.bridgeCalibrated:
                weight = finite((voltageRatio + self.bridgeOffset) * self.bridgeScale)
                self.updateStateOnServer("weight", value=weight, decimalPlaces=self.decimalPlaces)
            elif (self.sensorType == VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO and
                    self.customState and self.formula is not None):
                customValue = self.formula.evaluate(voltageRatio, self.customOutputType)
                arguments = {"value": customValue}
                if self.customOutputType == "number":
                    arguments["decimalPlaces"] = self.decimalPlaces
                self.updateStateOnServer(self.customState, **arguments)
        except Exception as error:
            self.logger.error("Voltage-ratio update failed: device='%s' input=%r: %s",
                              self.indigoDevice.name, voltageRatio,
                              str(error).replace("\n", " "))

    def onSensorChangeHandler(self, ph, sensorValue, sensorUnit):
        self.updateStateOnServer(self.sensorStateName , value=sensorValue, decimalPlaces=self.decimalPlaces)
        if self.sensorStateName == "tempC":
            self.updateStateOnServer("tempF", value=(9.0/5.0 * sensorValue + 32), decimalPlaces=self.decimalPlaces)
            self.indigoDevice.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensorOn)

        if self.sensorStateName == "percent":
            self.indigoDevice.updateStateImageOnServer(indigo.kStateImageSel.HumiditySensorOn)

        if self.sensorStateName == "lux":
            self.indigoDevice.updateStateImageOnServer(indigo.kStateImageSel.EnergyMeterOn)


    def getDeviceStateList(self):
        newStatesList = indigo.List()
        newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType("voltageRatio", "voltageRatio", "voltageRatio"))
        if self.bridgeCalibrated:
            newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType(
                "weight", "Weight (%s)" % self.bridgeUnits, "weight"))
        if self.sensorType != VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO:
            newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType(self.sensorStateName, self.sensorStateName, self.sensorStateName))
            if self.sensorStateName == "tempC":
                newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType("tempF", "tempF", "tempF"))
        elif self.customState and self.customFormula:
            factory_name = {
                "number": "getDeviceStateDictForNumberType",
                "text": "getDeviceStateDictForStringType",
                "boolean": "getDeviceStateDictForBoolOnOffType",
            }[self.customOutputType]
            newStatesList.append(getattr(self.indigo_plugin, factory_name)(
                self.customState, self.customState, self.customState))
        return newStatesList

    def getDeviceDisplayStateId(self):
        if self.bridgeCalibrated:
            return "weight"
        if self.sensorType != VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO:
            return self.sensorStateName
        elif self.customState and self.customFormula:
            return self.customState
        else:
            return "voltageRatio"
