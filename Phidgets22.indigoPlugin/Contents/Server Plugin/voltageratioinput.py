# -*- coding: utf-8 -*-
import traceback

import indigo

from Phidget22.Devices.VoltageRatioInput import VoltageRatioInput
from Phidget22.VoltageRatioSensorType import VoltageRatioSensorType

from phidget import PhidgetBase

import sensortypes

class VoltageRatioInputPhidget(PhidgetBase):
    def __init__(self, sensorType, dataInterval, voltageRatioChangeTrigger, sensorValueChangeTrigger, customState, customFormula, *args, **kwargs):
        super(VoltageRatioInputPhidget, self).__init__(phidget=VoltageRatioInput(), *args, **kwargs)
        self.sensorType = sensorType
        self.dataInterval = dataInterval
        self.voltageRatioChangeTrigger = voltageRatioChangeTrigger
        self.sensorValueChangeTrigger = sensorValueChangeTrigger
        self.customState = customState
        self.customFormula = customFormula

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
        if self.sensorType == VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO and self.customState and self.customFormula:
            try:
                formula = lambda x: eval(self.customFormula)
                customValue = formula(float(voltageRatio))
                self.indigoDevice.updateStateOnServer(self.customState, value=customValue, decimalPlaces=self.decimalPlaces)
            except Exception as e:
                self.logger.error('onVoltageRatioChangeHandler: %s received for device: %s' %  (traceback.format_exc(), self.indigoDevice.name))

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
            newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType(self.customState, self.customState, self.customState))
        return newStatesList

    def getDeviceDisplayStateId(self):
        if self.sensorType != VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO:
            return self.sensorStateName
        elif self.customState and self.customFormula:
            return self.customState
        else:
            return "voltageRatio"
