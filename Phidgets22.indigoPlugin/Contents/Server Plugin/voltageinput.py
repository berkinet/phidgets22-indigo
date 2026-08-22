# -*- coding: utf-8 -*-
import traceback
import indigo

from Phidget22.Devices.VoltageInput import VoltageInput
from Phidget22.VoltageSensorType import VoltageSensorType

from phidget import PhidgetBase

import sensortypes


# TODO: How do we figure out which VoltageInput devices support sensors and which do not?
#       We need to add the sensor features for certain devices (e.g. interface kits)
#       but not others (e.g. temperature sensor used in voltage mode.)

class VoltageInputPhidget(PhidgetBase):
    def __init__(self, sensorType, dataInterval, voltageChangeTrigger, sensorValueChangeTrigger, customState, customFormula, *args, **kwargs):
        super(VoltageInputPhidget, self).__init__(phidget=VoltageInput(), *args, **kwargs)
        self.sensorType = sensorType
        self.dataInterval = dataInterval
        self.voltageChangeTrigger = voltageChangeTrigger
        self.sensorValueChangeTrigger = sensorValueChangeTrigger
        self.customState = customState
        self.customFormula = customFormula

        self.sensorUnit = sensortypes.getVoltageSensorUnit(sensorType)
        (self.sensorStateName, self.sensorSymbol) = sensortypes.getNameAndSymbol(self.sensorUnit)

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)
        self.phidget.setOnVoltageChangeHandler(self.onVoltageChangeHandler)
        self.phidget.setOnSensorChangeHandler(self.onSensorChangeHandler)

    def configureAttachedPhidget(self, ph):
        newDataInterval = self.checkValueRange("dataInterval", value=self.dataInterval, minValue=self.phidget.getMinDataInterval(),  maxValue=self.phidget.getMaxDataInterval())
        if newDataInterval is None:
            self.phidget.setDataInterval(PhidgetBase.PHIDGET_DEFAULT_DATA_INTERVAL)
        else:
            self.phidget.setDataInterval(newDataInterval)

        self.phidget.setSensorType(self.sensorType)

        newVoltageChangeTrigger = self.checkValueRange(
            fieldname="voltageChangeTrigger", value=self.voltageChangeTrigger,
                minValue=self.phidget.getMinVoltageChangeTrigger(),
            maxValue=self.phidget.getMaxVoltageChangeTrigger())
        if newVoltageChangeTrigger is not None:
            self.phidget.setVoltageChangeTrigger(newVoltageChangeTrigger)

        self.phidget.setSensorValueChangeTrigger(self.sensorValueChangeTrigger)


    def onVoltageChangeHandler(self, ph, voltage):
        self.indigoDevice.updateStateOnServer("voltage_in", value=voltage, decimalPlaces=self.decimalPlaces)
        if self.sensorType == VoltageSensorType.SENSOR_TYPE_VOLTAGE and self.customState and self.customFormula:
            try:
                formula = lambda x: eval(self.customFormula)
                customValue = formula(float(voltage))
                self.indigoDevice.updateStateOnServer(self.customState, value=customValue, decimalPlaces=self.decimalPlaces)
            except Exception as e:
                self.logger.error('onVoltageChangeHandler: %s received for device: %s' %  (traceback.format_exc(), self.indigoDevice.name))

    def onSensorChangeHandler(self, ph, sensorValue, sensorUnit):
        self.indigoDevice.updateStateOnServer(self.sensorStateName , value=sensorValue, decimalPlaces=self.decimalPlaces)
        if self.sensorStateName == "tempC":
            self.indigoDevice.updateStateOnServer("tempF", value=(9.0/5.0 * sensorValue + 32), decimalPlaces=self.decimalPlaces)

        if self.sensorStateName == "lux":
            self.indigoDevice.updateStateImageOnServer(indigo.kStateImageSel.EnergyMeterOn)

    def getDeviceStateList(self):
        newStatesList = indigo.List()
        newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType("voltage_in", "voltage_in", "voltage_in"))
        if self.sensorType != VoltageSensorType.SENSOR_TYPE_VOLTAGE:
            newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType(self.sensorStateName, self.sensorStateName, self.sensorStateName))
            if self.sensorStateName == "tempC":
                newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType("tempF", "tempF", "tempF"))
        elif self.customState and self.customFormula:
            newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType(self.customState, self.customState, self.customState))
        return newStatesList

    def getDeviceDisplayStateId(self):
        if self.sensorType != VoltageSensorType.SENSOR_TYPE_VOLTAGE:
            return self.sensorStateName
        elif self.customState and self.customFormula:
            return self.customState
        else:
            return "voltage_in"
