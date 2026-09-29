# -*- coding: utf-8 -*-
"""RFID presence sensing; every compatible tag is accepted without enrolment."""
import datetime
import threading
from types import SimpleNamespace

from Phidget22.Devices.RFID import RFID
from phidget import PhidgetBase, PeripheralUnavailableError


class RFIDPhidget(PhidgetBase):
    def __init__(self, antennaEnabled=True, **kwargs):
        super(RFIDPhidget, self).__init__(phidget=RFID(), **kwargs)
        self.antennaEnabled = antennaEnabled
        self._tag_lock = threading.RLock()
        self._present_tag = None

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)
        self.phidget.setOnTagHandler(self.onTagHandler)
        self.phidget.setOnTagLostHandler(self.onTagLostHandler)

    def _report(self, operation, error):
        self.logger.error("RFID %s failed for '%s': %s", operation,
                          self.indigoDevice.name, str(error).replace("\n", " "))
        try:
            self.indigoDevice.setErrorStateOnServer("RFID %s failed" % operation)
        except Exception as state_error:
            self.logger.error("Unable to report RFID error for '%s': %s",
                              self.indigoDevice.name, str(state_error).replace("\n", " "))

    def _publish_tag(self, present, tag=None, protocol=None, notify=False):
        previous = self._present_tag
        current = (str(tag), protocol) if present else None
        if tag is not None:
            self.updateStateOnServer("lastTag", str(tag))
            label = {1: "EM4100", 2: "ISO11785 FDX-B", 3: "PhidgetTAG",
                     4: "HID Generic", 5: "HID H10301"}.get(
                protocol, "Unknown (%s)" % protocol)
            self.updateStateOnServer("protocol", label)
        self.updateStateOnServer("tagPresent", bool(present))
        self.updateStateOnServer("lastUpdate", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self._present_tag = current
        if notify and previous != current:
            self.indigo_plugin.triggerEvent(
                self, "rfidTagDetected" if present else "rfidTagLost")

    def configureAttachedPhidget(self, ph):
        try:
            with self._tag_lock:
                ph.setAntennaEnabled(self.antennaEnabled)
                self.updateStateOnServer("antennaEnabled", ph.getAntennaEnabled())
                if ph.getTagPresent():
                    tag, protocol = ph.getLastTag()
                    self._publish_tag(True, tag, protocol, notify=True)
                else:
                    self._publish_tag(False)
        except Exception as error:
            raise PeripheralUnavailableError("RFID initialization: %s" % str(error).replace("\n", " ")) from None

    def onTagHandler(self, ph, tag, protocol):
        try:
            with self._tag_lock:
                if self._state in ("stopping", "stopped", "detached"):
                    return
                self._publish_tag(True, tag, protocol, notify=True)
        except Exception as error:
            self._report("tag detection", error)

    def onTagLostHandler(self, ph, tag, protocol):
        try:
            with self._tag_lock:
                if self._state in ("stopping", "stopped", "detached"):
                    return
                if self._present_tag == (str(tag), protocol):
                    self._publish_tag(False, tag, protocol, notify=True)
        except Exception as error:
            self._report("tag loss", error)

    def onDetachHandler(self, ph):
        try:
            with self._tag_lock:
                if self._state in ("stopping", "stopped"):
                    return
                super(RFIDPhidget, self).onDetachHandler(ph)
                self._publish_tag(False)
                self.updateStateOnServer("antennaEnabled", False)
        except Exception as error:
            self._report("disconnect state", error)

    def setAntennaEnabled(self, enabled):
        try:
            with self._tag_lock:
                self.phidget.setAntennaEnabled(enabled)
                self.antennaEnabled = enabled
                self.updateStateOnServer("antennaEnabled", self.phidget.getAntennaEnabled())
                if not enabled:
                    self._publish_tag(False, notify=True)
        except Exception as error:
            self._report("antenna control", error)

    def getDeviceStateList(self):
        return self.stateList(
            ("bool", "tagPresent", "Tag present"),
            ("string", "lastTag", "Last tag ID"),
            ("string", "protocol", "Last tag protocol"),
            ("bool", "antennaEnabled", "Antenna enabled"),
            ("string", "lastUpdate", "Last update"))

    def getDeviceDisplayStateId(self):
        return "tagPresent"


class SimulatedRFIDPhidget(RFIDPhidget):
    """Hardware-free reader using the same state and event publication path."""

    def __init__(self, antennaEnabled=True, **kwargs):
        # Do not construct or open a native RFID handle.
        PhidgetBase.__init__(self, phidget=SimpleNamespace(), **kwargs)
        self.antennaEnabled = antennaEnabled
        self._tag_lock = threading.RLock()
        self._present_tag = None

    def start(self):
        try:
            with self._tag_lock:
                self._state = "attached"
                self._publish_tag(False)
                self.updateStateOnServer("antennaEnabled", self.antennaEnabled)
                for key in ("serverName", "serverUniqueName", "serverHost", "serverPeer"):
                    self.updateStateOnServer(key, "")
                for key in ("connectionType", "connection", "connectionPath"):
                    self.updateStateOnServer(key, "Simulated RFID reader")
                self.indigoDevice.setErrorStateOnServer(None)
        except Exception as error:
            self._state = "stopped"
            self._report("simulation startup", error)

    def stop(self):
        try:
            with self._tag_lock:
                self._state = "stopped"
                self._publish_tag(False)
                self.updateStateOnServer("antennaEnabled", False)
        except Exception as error:
            self._report("simulation stop", error)

    def setAntennaEnabled(self, enabled):
        try:
            with self._tag_lock:
                if self._state != "attached":
                    raise ValueError("simulated reader is not running")
                self.antennaEnabled = bool(enabled)
                self.updateStateOnServer("antennaEnabled", self.antennaEnabled)
                if not enabled:
                    self._publish_tag(False, notify=True)
                self.indigoDevice.setErrorStateOnServer(None)
        except Exception as error:
            self._report("simulated antenna control", error)

    def simulateTag(self, tag=None, protocol=1):
        try:
            with self._tag_lock:
                if self._state != "attached":
                    raise ValueError("simulated reader is not running")
                if tag is not None:
                    tag = str(tag).strip()
                    if not tag or protocol not in (1, 2, 3, 4, 5):
                        raise ValueError("enter a tag ID and select a supported protocol")
                    if not self.antennaEnabled:
                        raise ValueError("enable the simulated antenna before scanning a tag")
                    if self._present_tag is not None and self._present_tag != (tag, protocol):
                        self._publish_tag(False, notify=True)
                    self._publish_tag(True, tag, protocol, notify=True)
                else:
                    self._publish_tag(False, notify=True)
                self.indigoDevice.setErrorStateOnServer(None)
        except Exception as error:
            self._report("simulated tag scan", error)
