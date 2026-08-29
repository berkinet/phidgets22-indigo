# -*- coding: utf-8 -*-
import indigo

from Phidget22.Devices.FrequencyCounter import FrequencyCounter

from phidget import PhidgetBase

class FrequencyCounterPhidget(PhidgetBase):
    def __init__(self, filterType, dataInterval, displayStateName, frequencyCutoff, isDAQ1400, inputType, powerSupply, *args, **kwargs):
        super(FrequencyCounterPhidget, self).__init__(phidget=FrequencyCounter(), *args, **kwargs)
        self.filterType = filterType
        self.dataInterval = dataInterval
        self.displayStateName = displayStateName
        self.frequencyCutoff = frequencyCutoff
        self.inputType = inputType
        self.powerSupply = powerSupply
        self.isDAQ1400 = isDAQ1400

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)
        self.phidget.setOnFrequencyChangeHandler(self.onFrequencyChangeHandler)
        self.phidget.setOnCountChangeHandler(self.onCountChangeHandler)

    def configureAttachedPhidget(self, ph):
        newDataInterval = self.checkValueRange("dataInterval", value=self.dataInterval, minValue=self.phidget.getMinDataInterval(),  maxValue=self.phidget.getMaxDataInterval())
        if newDataInterval is None:
            self.phidget.setDataInterval(PhidgetBase.PHIDGET_DEFAULT_DATA_INTERVAL)
        else:
            self.phidget.setDataInterval(newDataInterval)

        # setFrequencyCutoff() - The frequency at which zero hertz is assumed.
        newFrequencyCutoff = self.checkValueRange('frequencyCutoff', value=self.frequencyCutoff, minValue=0, maxValue=100, zero_ok=True)
        if newFrequencyCutoff is None:
            self.phidget.setFrequencyCutoff(1.0)
        else:
            self.phidget.setFrequencyCutoff(float(newFrequencyCutoff))

        if not self.phidget.getEnabled():
            # Enable if not already enabled. DAQ1400 is always enabled.
            self.phidget.setEnabled(True)

        if self.isDAQ1400:
            self.phidget.setInputMode(self.inputType)
            self.phidget.setPowerSupply(self.powerSupply)
        else:
            # FilterType can not be set for DAQ1400.
            self.phidget.setFilterType(self.filterType)


    def onFrequencyChangeHandler(self, ph, frequency):
        self.indigoDevice.updateStateOnServer("frequency", value=frequency,  decimalPlaces=self.decimalPlaces)

    def onCountChangeHandler(self, ph, count, timeChange):
        self.indigoDevice.updateStateOnServer("count", value=ph.getCount())
        self.indigoDevice.updateStateOnServer("timeChange", value=timeChange,  decimalPlaces=self.decimalPlaces)

    def getDeviceStateList(self):
        return self.stateList(
            ("number", "frequency", "frequency"),
            ("number", "count", "count"),
            ("number", "timeChange", "timeChange"))

    def getDeviceDisplayStateId(self):
        if self.displayStateName in ["frequency", "count", "timeChange"]:
            return self.displayStateName
        else:
            return "frequency"
