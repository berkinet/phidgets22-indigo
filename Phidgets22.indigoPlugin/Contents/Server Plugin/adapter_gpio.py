# -*- coding: utf-8 -*-

"""GPIO channels exposed by an ADP0001 selected through an Indigo adapter."""

import threading

import indigo

from Phidget22.ErrorCode import ErrorCode
from Phidget22.InputMode import InputMode

from digitalinput import DigitalInputPhidget
from digitaloutput import DigitalOutputPhidget


class AdapterGPIOInputPhidget(DigitalInputPhidget):
    def __init__(self, adapterDeviceId, inputMode="pullup", inverted=False,
                 debounceMilliseconds=50, *args, **kwargs):
        super(AdapterGPIOInputPhidget, self).__init__(*args, **kwargs)
        self.adapterDeviceId = int(adapterDeviceId)
        self.inputMode = str(inputMode)
        self.inverted = bool(inverted)
        self.debounceMilliseconds = int(debounceMilliseconds)
        self._debounce_lock = threading.RLock()
        self._debounce_timer = None
        self._pending_state = None

    def configureAttachedPhidget(self, ph):
        modes = {
            "floating": InputMode.INPUT_MODE_FLOATING,
            "pullup": InputMode.INPUT_MODE_PULLUP,
        }
        ph.setInputMode(modes[self.inputMode])

    def _publishPendingState(self):
        with self._debounce_lock:
            state = self._pending_state
            self._debounce_timer = None
        if self._state == "attached" and state is not None:
            self.updateIndigoStatus(bool(state) != self.inverted)

    def onStateChangeHandler(self, ph, state):
        if self.debounceMilliseconds <= 0:
            self.updateIndigoStatus(bool(state) != self.inverted)
            return
        with self._debounce_lock:
            self._pending_state = bool(state)
            old_timer = self._debounce_timer
            timer = threading.Timer(
                self.debounceMilliseconds / 1000.0,
                self._publishPendingState)
            timer.daemon = True
            self._debounce_timer = timer
        if old_timer is not None:
            old_timer.cancel()
        timer.start()

    def onAttachHandler(self, ph):
        super(AdapterGPIOInputPhidget, self).onAttachHandler(ph)
        if self._state == "attached":
            self.updateIndigoStatus(bool(ph.getState()) != self.inverted)

    def actionControlSensor(self, action):
        # The base implementation reads the raw state, so apply inversion here.
        if action.sensorAction == indigo.kSensorAction.RequestStatus:
            self.updateIndigoStatus(
                bool(self.phidget.getState()) != self.inverted)
            return
        super(AdapterGPIOInputPhidget, self).actionControlSensor(action)

    def stop(self):
        with self._debounce_lock:
            timer = self._debounce_timer
            self._debounce_timer = None
        if timer is not None:
            timer.cancel()
        super(AdapterGPIOInputPhidget, self).stop()


class AdapterGPIOOutputPhidget(DigitalOutputPhidget):
    def __init__(self, adapterDeviceId, *args, **kwargs):
        super(AdapterGPIOOutputPhidget, self).__init__(*args, **kwargs)
        self.adapterDeviceId = int(adapterDeviceId)

    def updateIndigoStatus(self):
        state = bool(self.phidget.getState())
        self.indigoDevice.updateStateOnServer(
            "onOffState", value=state, uiValue="on" if state else "off")

    def actionControlDevice(self, action):
        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            state = True
        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            state = False
        elif action.deviceAction == indigo.kDeviceAction.Toggle:
            state = not bool(self.phidget.getState())
        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.updateIndigoStatus()
            return
        else:
            self.logger.error("Unexpected GPIO output action: %s",
                              action.deviceAction)
            return
        self.phidget.setState_async(state, self.asyncSetResult)

    def asyncSetResult(self, ch, res, details):
        if res != ErrorCode.EPHIDGET_OK:
            self.logger.error("GPIO output failure: %i: %s", res, details)
        self.updateIndigoStatus()
