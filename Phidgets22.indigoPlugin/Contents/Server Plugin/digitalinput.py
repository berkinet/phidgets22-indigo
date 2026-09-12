# -*- coding: utf-8 -*-
import datetime

import indigo

from Phidget22.Devices.DigitalInput import DigitalInput
from Phidget22.Devices.Log import Log
from Phidget22.LogLevel import LogLevel
from phidget import PhidgetBase

class DigitalInputPhidget(PhidgetBase):
    def __init__(self, isAlarm, onStateIcon, offStateIcon,
                 logRawStateChanges=False, *args, **kwargs):
        super(DigitalInputPhidget, self).__init__(phidget=DigitalInput(), *args, **kwargs)
        self.isAlarm = isAlarm
        self.onStateIcon = onStateIcon
        self.offStateIcon = offStateIcon
        self.logRawStateChanges = logRawStateChanges
        self._rawStateChangeSequence = 0

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)
        self.phidget.setOnStateChangeHandler(self.onStateChangeHandler)

    def updateIndigoStatus(self, state):
        # Common code between onStateChangeHandler & indigo.kSensorAction.RequestStatus
        stateImage =  getattr(indigo.kStateImageSel, "Auto")
        if state:
            setState = 'on'
            stateImage =  getattr(indigo.kStateImageSel, self.onStateIcon)
        else:
            setState = 'off'
            stateImage =  getattr(indigo.kStateImageSel, str(self.offStateIcon))

        self.updateStateOnServer("onOffState", value=setState)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.updateStateOnServer(key="lastUpdate", value=now)
        self.indigoDevice.updateStateImageOnServer(stateImage)

    def onStateChangeHandler(self, ph, state):
        if self.logRawStateChanges:
            self._rawStateChangeSequence += 1
            Log.log(
                LogLevel.PHIDGET_LOG_INFO,
                "DigitalInput raw callback: device='%s' id=%s serial=%s "
                "hubPort=%s channel=%s sequence=%s state=%s" % (
                    self.indigoDevice.name, self.indigoDevice.id,
                    self.channelInfo.serialNumber, self.channelInfo.hubPort,
                    self.channelInfo.channel, self._rawStateChangeSequence,
                    bool(state)))
        self.updateIndigoStatus(state)

    def actionControlSensor(self, action):
        if action.sensorAction == indigo.kSensorAction.RequestStatus:
            state = self.phidget.getState()
            self.updateIndigoStatus(state)
        else:
            self.logger.error("Unexpected action: %s" % action.deviceAction)

    def getDeviceStateList(self):
        return self.stateList(
            ("bool", "onOffState", "onOffState"),
            ("string", "lastUpdate", "lastUpdate"))

    def getDeviceDisplayStateId(self):
        return "onOffState"
