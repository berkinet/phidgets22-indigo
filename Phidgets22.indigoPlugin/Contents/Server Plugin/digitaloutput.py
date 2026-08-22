# -*- coding: utf-8 -*-
import traceback

import indigo

from Phidget22.Devices.DigitalOutput import DigitalOutput
from Phidget22.ErrorCode import ErrorCode

from phidget import PhidgetBase

class DigitalOutputPhidget(PhidgetBase):
    def __init__(self, *args, **kwargs):
        super(DigitalOutputPhidget, self).__init__(phidget=DigitalOutput(), *args, **kwargs)

    def updateIndigoStatus(self):
        try:
            brightnessLevel = int(100 * self.phidget.getDutyCycle())
            onOffState = bool(self.phidget.getState())
            self.indigoDevice.updateStateOnServer("brightnessLevel", value=brightnessLevel, uiValue="%d" % brightnessLevel)
            self.indigoDevice.updateStateOnServer("onOffState", value=onOffState, uiValue="on" if onOffState else "off")
        except Exception as e:
            self.logger.error('%s: %s' % (self.indigoDevice.name, traceback.format_exc()))

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)

    def onAttachHandler(self, ph):
        super(DigitalOutputPhidget, self).onAttachHandler(ph)

    def getDeviceStateList(self):
        # Currently support the minimal states used by all phidget DigitalOutput devices
        newStatesList = indigo.List()
        # onOffState and brightnessLevel are automatically inherited from an Indigo relay class
        # newStatesList.append(self.indigo_plugin.getDeviceStateDictForBoolOnOffType("onOffState", "onOffState", "onOffState"))
        # newStatesList.append(self.indigo_plugin.getDeviceStateDictForNumberType("dutyCycle", "dutyCycle", "dutyCycle"))
        return newStatesList

    def getDeviceDisplayStateId(self):
        return "onOffState"

    def actionControlDevice(self, action):
        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            self.phidget.setState_async(True, self.asyncSetResult)
        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self.phidget.setState_async(False, self.asyncSetResult)
        elif action.deviceAction == indigo.kDeviceAction.Toggle:
            onOffState = bool(self.phidget.getState())
            self.phidget.setState_async(not onOffState, self.asyncSetResult)
        elif action.deviceAction == indigo.kDeviceAction.SetBrightness:
            # Brightness value will be 0-100; phidgets expects 0.0-1.0
            self.phidget.setDutyCycle_async(action.actionValue / 100.0, self.asyncSetResult)
        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.updateIndigoStatus()
        else:
            self.logger.error("Unexpected action: %s" % action.deviceAction)

    def asyncSetResult(self, ch, res, details):
        if res != ErrorCode.EPHIDGET_OK:
            self.logger.error("Async failure: %i : %s" % (res, details))
        self.updateIndigoStatus()
