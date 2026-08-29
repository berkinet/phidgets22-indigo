# -*- coding: utf-8 -*-
import indigo

from Phidget22.Devices.TemperatureSensor import TemperatureSensor

from phidget import PhidgetBase

class TemperatureSensorPhidget(PhidgetBase):
    def __init__(self, thermocoupleType, dataInterval, temperatureChangeTrigger, displayTempUnit, *args, **kwargs):
        super(TemperatureSensorPhidget, self).__init__(phidget=TemperatureSensor(), *args, **kwargs)
        self.thermocoupleType = thermocoupleType
        self.dataInterval = dataInterval
        self.displayTempUnit = displayTempUnit

        if self.displayTempUnit.upper() == "F":
            self.temperatureChangeTrigger = 9.0/5.0 * temperatureChangeTrigger
        else: # C
            self.temperatureChangeTrigger = temperatureChangeTrigger

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)
        self.phidget.setOnTemperatureChangeHandler(self.onTemperatureChangeHandler)

    def configureAttachedPhidget(self, ph):
        newDataInterval = self.checkValueRange("dataInterval", value=self.dataInterval, minValue=self.phidget.getMinDataInterval(),  maxValue=self.phidget.getMaxDataInterval())
        if newDataInterval is None:
            self.phidget.setDataInterval(PhidgetBase.PHIDGET_DEFAULT_DATA_INTERVAL)
        else:
            self.phidget.setDataInterval(newDataInterval)

        if self.thermocoupleType:
            ph.setThermocoupleType(self.thermocoupleType)

        newTemperatureChangeTrigger = self.checkValueRange(
            fieldname="temperatureChangeTrigger", value=self.temperatureChangeTrigger,
                minValue=self.phidget.getMinTemperatureChangeTrigger(),
            maxValue=self.phidget.getMaxTemperatureChangeTrigger())
        if newTemperatureChangeTrigger is not None:
            self.phidget.setTemperatureChangeTrigger(newTemperatureChangeTrigger)


    def onTemperatureChangeHandler(self, ph, temperature):
        self.indigoDevice.updateStateOnServer("tempC", value=temperature, decimalPlaces=self.decimalPlaces)
        self.indigoDevice.updateStateOnServer("tempF", value=(9.0/5.0 * temperature + 32), decimalPlaces=self.decimalPlaces)
        self.indigoDevice.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensorOn)

    def getDeviceStateList(self):
        return self.stateList(
            ("number", "tempF", "tempF"),
            ("number", "tempC", "tempC"))

    def getDeviceDisplayStateId(self):
        if self.displayTempUnit.upper() == "F":
            return "tempF"
        else:
            return "tempC"
