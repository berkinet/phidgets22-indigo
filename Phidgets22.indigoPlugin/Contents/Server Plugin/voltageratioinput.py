# -*- coding: utf-8 -*-
import indigo

from Phidget22.Devices.VoltageRatioInput import VoltageRatioInput
from Phidget22.VoltageRatioSensorType import VoltageRatioSensorType

from phidget import PhidgetBase
from formula import Formula

import sensortypes

class VoltageRatioInputPhidget(PhidgetBase):
    def __init__(self, sensorType, dataInterval, voltageRatioChangeTrigger, sensorValueChangeTrigger, customState, customFormula, *args, **kwargs):
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

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)
        self.phidget.setOnVoltageRatioChangeHandler(self.setOnVoltageRatioChangeHandler)
        self.phidget.setOnSensorChangeHandler(self.onSensorChangeHandler)

    def configureAttachedPhidget(self, ph):
        newDataInterval = self.checkValueRange("dataInterval", value=self.dataInterval, minValue=self.phidget.getMinDataInterval(),  maxValue=self.phidget.getMaxDataInterval())
        if newDataInterval is None:
            self.phidget.setDataInterval(PhidgetBase.PHIDGET_DEFAULT_DATA_INTERVAL)
        else:
            self.phidget.setDataInterval(newDataInterval)

        self.phidget.setSensorType(self.sensorType)

        newVoltageRatioChangeTrigger = self.checkValueRange(
            fieldname="voltageRatioChangeTrigger", value=self.voltageRatioChangeTrigger,
                minValue=self.phidget.getMinVoltageRatioChangeTrigger(),
            maxValue=self.phidget.getMaxVoltageRatioChangeTrigger())
        if newVoltageRatioChangeTrigger is not None:
            self.phidget.setVoltageRatioChangeTrigger(newVoltageRatioChangeTrigger)

        self.phidget.setSensorValueChangeTrigger(self.sensorValueChangeTrigger)


    def setOnVoltageRatioChangeHandler(self, ph, voltageRatio):
        self.indigoDevice.updateStateOnServer("voltageRatio", value=voltageRatio, decimalPlaces=self.decimalPlaces)
        if (self.sensorType == VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO and
                self.customState and self.formula is not None):
            try:
                customValue = self.formula.evaluate(
                    voltageRatio, self.customOutputType)
                arguments = {"value": customValue}
                if self.customOutputType == "number":
                    arguments["decimalPlaces"] = self.decimalPlaces
                self.indigoDevice.updateStateOnServer(
                    self.customState, **arguments)
            except (ArithmeticError, TypeError, ValueError) as error:
                self.logger.error(
                    "Custom voltage-ratio formula failed: device='%s' "
                    "formula=%r input=%s: %s", self.indigoDevice.name,
                    self.customFormula, voltageRatio, error)

    def onSensorChangeHandler(self, ph, sensorValue, sensorUnit):
        self.indigoDevice.updateStateOnServer(self.sensorStateName , value=sensorValue, decimalPlaces=self.decimalPlaces)
        if self.sensorStateName == "tempC":
            self.indigoDevice.updateStateOnServer("tempF", value=(9.0/5.0 * sensorValue + 32), decimalPlaces=self.decimalPlaces)
            self.indigoDevice.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensorOn)

        if self.sensorStateName == "percent":
            self.indigoDevice.updateStateImageOnServer(indigo.kStateImageSel.HumiditySensorOn)

        if self.sensorStateName == "lux":
            self.indigoDevice.updateStateImageOnServer(indigo.kStateImageSel.EnergyMeterOn)


    def getDeviceStateList(self):
        newStatesList = indigo.List()
        newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType("voltageRatio", "voltageRatio", "voltageRatio"))
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
        if self.sensorType != VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO:
            return self.sensorStateName
        elif self.customState and self.customFormula:
            return self.customState
        else:
            return "voltageRatio"
