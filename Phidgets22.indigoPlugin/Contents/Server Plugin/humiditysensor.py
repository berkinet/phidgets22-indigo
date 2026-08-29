# -*- coding: utf-8 -*-
import indigo

from Phidget22.Devices.HumiditySensor import HumiditySensor

from phidget import PhidgetBase

class HumiditySensorPhidget(PhidgetBase):
    def __init__(self, dataInterval, humidityChangeTrigger, *args, **kwargs):
        super(HumiditySensorPhidget, self).__init__(phidget=HumiditySensor(), *args, **kwargs)
        self.dataInterval = dataInterval
        self.humidityChangeTrigger = humidityChangeTrigger

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)
        self.phidget.setOnHumidityChangeHandler(self.onHumidityChangeHandler)

    def configureAttachedPhidget(self, ph):
        newDataInterval = self.checkValueRange("dataInterval", value=self.dataInterval, minValue=self.phidget.getMinDataInterval(),  maxValue=self.phidget.getMaxDataInterval())
        if newDataInterval is None:
            self.phidget.setDataInterval(PhidgetBase.PHIDGET_DEFAULT_DATA_INTERVAL)
        else:
            self.phidget.setDataInterval(newDataInterval)

        newHumidityChangeTrigger = self.checkValueRange(
            fieldname="humidityChangeTrigger", value=self.humidityChangeTrigger,
            minValue=self.phidget.getMinHumidityChangeTrigger(),
            maxValue=self.phidget.getMaxHumidityChangeTrigger())
        if newHumidityChangeTrigger is not None:
            self.phidget.setHumidityChangeTrigger(newHumidityChangeTrigger)

    def onHumidityChangeHandler(self, ph, humidity):
        self.indigoDevice.updateStateOnServer("humidity", value=humidity, decimalPlaces=self.decimalPlaces)
        self.indigoDevice.updateStateImageOnServer(indigo.kStateImageSel.HumiditySensorOn)

    def getDeviceStateList(self):
        return self.stateList(("number", "humidity", "humidity"))

    def getDeviceDisplayStateId(self):
        return "humidity"
