# -*- coding: utf-8 -*-
"""RFID presence sensing with optional per-reader tag policy."""
import datetime
import threading
from types import SimpleNamespace

import rfid_tags
from rfid_presence import RFIDPresence
from rfid_outputs import RFIDOutputs, OUTPUTS

from Phidget22.Devices.RFID import RFID
from phidget import PhidgetBase, PeripheralUnavailableError


class RFIDPhidget(PhidgetBase):
    def __init__(self, antennaEnabled=True, **kwargs):
        super(RFIDPhidget, self).__init__(phidget=RFID(), **kwargs)
        self.antennaEnabled = antennaEnabled
        self.outputs = RFIDOutputs(self)
        self._tag_lock = threading.RLock()
        self._present_tag = None
        self.rfidPolicyProps = dict(self.indigoDevice.pluginProps)

    def _presence_for(self, reset=False):
        presence = getattr(self, "_presence", None)
        if presence is None:
            self._presence = presence = RFIDPresence(self)
        elif reset:
            presence.reset()
        return presence

    def start(self):
        with self._tag_lock:
            self._present_tag = None
            self._presence_for(reset=True)
        super(RFIDPhidget, self).start()

    def stop(self):
        with self._tag_lock:
            self._state = "stopping"
            try:
                self._presence_for().stop()
            except Exception as error:
                self._report("presence stop", error)
        if getattr(self, "outputs", None) is not None:
            self.outputs.stop()
        super(RFIDPhidget, self).stop()

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

    def _publish_tag(self, present, tag=None, protocol=None, notify=False, updatePresence=True):
        previous = self._present_tag
        current = (str(tag), protocol) if present else None
        presence = self._presence_for()
        permission_event = None
        qualifying = presence.qualifying_tag_present if present else False
        if present and previous != current:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                rfid_tags.remember(self.indigo_plugin, self.indigoDevice.id, str(tag), protocol, timestamp)
            except Exception as error:
                self.logger.error("RFID history update failed for '%s': %s", self.indigoDevice.name,
                                  str(error).replace("\n", " "))
            try:
                allowed, reason = rfid_tags.evaluate_with_reason(
                    getattr(self, "rfidPolicyProps", {}), str(tag))
                policy_error = ""
                status = "Allowed" if allowed else "Denied"
                permission_event = "rfidAllowedTagDetected" if allowed else "rfidDeniedTagDetected"
                if not allowed:
                    self.logger.warning(
                        "RFID tag denied: reader=%r id=%s tag=%r protocol=%s: %s",
                        self.indigoDevice.name, self.indigoDevice.id, str(tag),
                        rfid_tags.PROTOCOLS.get(protocol, str(protocol)), reason)
            except Exception as error:
                allowed, status = False, "Error"
                policy_error = str(error).replace("\n", " ")
                self.logger.error(
                    "RFID list check failed: reader=%r id=%s tag=%r protocol=%s: %s",
                    self.indigoDevice.name, self.indigoDevice.id, str(tag),
                    rfid_tags.PROTOCOLS.get(protocol, str(protocol)), policy_error)
            qualifying = allowed
            self.updateStateOnServer("lastTagAllowed", allowed)
            self.updateStateOnServer("tagPolicyResult", status)
            self.updateStateOnServer("tagPolicyError", policy_error)
        if tag is not None:
            self.updateStateOnServer("lastTag", str(tag))
            label = rfid_tags.PROTOCOLS.get(
                protocol, "Unknown (%s)" % protocol)
            self.updateStateOnServer("protocol", label)
        self.updateStateOnServer("tagPresent", bool(present))
        self.updateStateOnServer("lastUpdate", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self._present_tag = current
        if updatePresence:
            presence.update(qualifying)
        if notify and previous != current:
            events = ["rfidTagDetected" if present else "rfidTagLost"]
            if permission_event:
                events.append(permission_event)
            for event in events:
                try:
                    self.indigo_plugin.triggerEvent(self, event)
                except Exception as error:
                    self._report(event, error)

    def configureAttachedPhidget(self, ph):
        try:
            with self._tag_lock:
                if getattr(self, "outputs", None) is not None:
                    self.outputs.start(ph)
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

    def setOutput(self, channel, enabled):
        self.outputs.set(channel, enabled)

    def getDeviceStateList(self):
        return self.stateList(
            ("bool", "tagPresent", "Tag present"),
            ("bool", "presenceActive", "Presence active"),
            ("string", "lastTag", "Last tag ID"),
            ("string", "protocol", "Last tag protocol"),
            ("bool", "lastTagAllowed", "Last tag allowed"),
            ("string", "tagPolicyResult", "Last tag policy result"),
            ("string", "tagPolicyError", "Tag policy error"),
            ("bool", "antennaEnabled", "Antenna enabled"),
            ("string", "lastUpdate", "Last update"),
            *[("bool", key, label) for key, label in OUTPUTS],
            *[("bool", key + "Available", label + " available") for key, label in OUTPUTS])

    def getDeviceDisplayStateId(self):
        return "tagPresent"


class SimulatedRFIDPhidget(RFIDPhidget):
    """Hardware-free reader using the same state and event publication path."""

    def __init__(self, antennaEnabled=True, **kwargs):
        # Do not construct or open native handles.
        PhidgetBase.__init__(self, phidget=SimpleNamespace(), **kwargs)
        self.antennaEnabled = antennaEnabled
        self.outputs = RFIDOutputs(self, simulated=True)
        self._tag_lock = threading.RLock()
        self._present_tag = None
        self.rfidPolicyProps = dict(self.indigoDevice.pluginProps)

    def start(self):
        try:
            with self._tag_lock:
                self._present_tag = None
                self._presence_for(reset=True)
                self._state = "attached"
                self.outputs.start()
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
                self.outputs.stop()
                self._presence_for().stop()
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
                        self._publish_tag(False, notify=True, updatePresence=False)
                    self._publish_tag(True, tag, protocol, notify=True)
                else:
                    self._publish_tag(False, notify=True)
                self.indigoDevice.setErrorStateOnServer(None)
        except Exception as error:
            self._report("simulated tag scan", error)
