from error_reporting import runtime_boundary
from error_reporting import log_error, clear_faults
# -*- coding: utf-8 -*-

from contextlib import nullcontext

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
            self.updateStateOnServer("brightnessLevel", value=brightnessLevel, uiValue="%d" % brightnessLevel)
            self.updateStateOnServer("onOffState", value=onOffState, uiValue="on" if onOffState else "off")
        except Exception as e:
            log_error(self, 'Digital output status read failed: %s; %s', self._identity(), str(e))

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)

    @runtime_boundary("onAttachHandler")
    def onAttachHandler(self, ph):
        super(DigitalOutputPhidget, self).onAttachHandler(ph)
        if self._state == "attached":
            self._clear_detached_write_failures()
            self.updateIndigoStatus()

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
            self.phidget.setState_async(True, self._result_callback("Turn On", True))
        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self.phidget.setState_async(False, self._result_callback("Turn Off", False))
        elif action.deviceAction == indigo.kDeviceAction.Toggle:
            onOffState = bool(self.phidget.getState())
            self.phidget.setState_async(not onOffState, self._result_callback("Toggle", not onOffState))
        elif action.deviceAction == indigo.kDeviceAction.SetBrightness:
            # Brightness value will be 0-100; phidgets expects 0.0-1.0
            self.phidget.setDutyCycle_async(action.actionValue / 100.0, self._result_callback("Set brightness", action.actionValue))
        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.updateIndigoStatus()
        else:
            log_error(self, "Unexpected action: %s" % action.deviceAction)

    def _result_callback(self, operation, requested):
        # Capture each request separately; completion order may differ from submission.
        identity = self._identity()
        epoch = getattr(self, "_lifecycle_epoch", 0)
        def completed(ch, res, details):
            with getattr(self, "_lifecycle_lock", nullcontext()):
                if (epoch != getattr(self, "_lifecycle_epoch", 0) or
                        getattr(self, "_state", None) in ("stopping", "stopped")):
                    return
                self.asyncSetResult(ch, res, details, operation, requested, identity)
        return completed

    def _clear_detached_write_failures(self):
        with getattr(self, "_lifecycle_lock", nullcontext()):
            self._detached_write_failures = set()
            clear_faults(self)

    def _first_detached_write_failure(self, operation, requested):
        with getattr(self, "_lifecycle_lock", nullcontext()):
            failures = getattr(self, "_detached_write_failures", None)
            if failures is None:
                failures = self._detached_write_failures = set()
            key = (operation, repr(requested))
            if key in failures:
                return False
            failures.add(key)
            return True

    @runtime_boundary("asyncSetResult")
    def asyncSetResult(self, ch, res, details, operation="unspecified write", requested=None, identity=None):
        if res != ErrorCode.EPHIDGET_OK:
            detached = res == ErrorCode.EPHIDGET_NOTATTACHED
            if detached and not self._first_detached_write_failure(operation, requested):
                return
            if identity is None:
                try:
                    identity = self._identity()
                except Exception:
                    identity = "device identity unavailable"
            message = "Async failure: %s : %s; %s; operation=%s requested=%s"
            if detached:
                message += ("; repeated failures for this request are suppressed until recovery. "
                            "Command was not applied or queued; automatic attachment remains active.")
            log_error(self, message,
                              res, details, identity, operation, requested)
            return
        self._clear_detached_write_failures()
        self.updateIndigoStatus()
