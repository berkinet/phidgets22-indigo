# -*- coding: utf-8 -*-
#
# Bulk of the code for actually interacting with the phidget devices.
#

import threading
import time
import traceback

import phidget_util
from config_util import saved_bool


class PeripheralUnavailableError(RuntimeError):
    """Expected failure when configured external hardware does not respond."""

    pass

class NetInfo():
    def __init__(self, isRemote=None, serverDiscovery=None, hostname=None, port=None, password=None, serverName=None):
        self.isRemote = isRemote
        self.serverDiscovery = serverDiscovery
        self.hostname = hostname
        self.port = port
        self.password = password
        self.serverName = serverName

class ChannelInfo():
    def __init__(self, serialNumber=-1, hubPort=-1, isHubPortDevice=0,
                 channel=-1, netInfo=None):
        self.serialNumber = serialNumber
        self.hubPort = hubPort
        self.isHubPortDevice = isHubPortDevice
        self.channel = channel
        self.netInfo = netInfo if netInfo is not None else NetInfo()


class PhidgetBase(object):
    """
    Base class for phidget devices living in Indigo.
    This will be extended for the various types of devices.
    """
    PHIDGET_DEFAULT_DATA_INTERVAL = 1000  # ms
    DETACH_GRACE_SECONDS = 2.0

    def __init__(self, phidget, indigo_plugin, channelInfo=None,
                 indigoDevice=None, logger=None, decimalPlaces=-1):
        self.phidget = phidget      # PhidgetAPI object for this phidget
        self.phidget.parent = self  # Reference back to this object from the PhidgetAPI
        self.logger = logger        # Where do we log?
        self.channelInfo = channelInfo if channelInfo is not None else ChannelInfo()
        self.indigoDevice = indigoDevice
        self.indigo_plugin = indigo_plugin
        self.decimalPlaces = decimalPlaces # Number of decimal places for Indigo do display for numbers. -1 means default (likely 5)
        self.pluginSuppressErrors = saved_bool(
            self.indigo_plugin.pluginPrefs.get('suppressErrors', False))

        self.initial_connection_timeout = int(indigo_plugin.pluginPrefs.get('attachTimeout', '5'))

        self.timer = None
        self._detach_grace_timer = None
        self._lifecycle_lock = threading.RLock()
        self._timer_generation = 0
        self._detach_generation = 0
        self._state = "stopped"
        self._detached_at = None
        self._detach_announced = False
        self._attach_count = 0
        self._started_at = None
        self._startup_contention_message = None
        self._startup_contention_expired = False
        self.runtimeServerName = None
        self.runtimeServerUniqueName = None
        self.runtimeServerHostname = None
        self.runtimeServerPeerName = None
        self.runtimeDeviceName = None
        self.runtimeDeviceSKU = None
        self.runtimeChannelName = None

    def _identity(self):
        net_info = self.channelInfo.netInfo
        return ("device='%s' id=%s type=%s server=%s serial=%s hubPort=%s "
                "channel=%s remote=%s" % (
                    self.indigoDevice.name, self.indigoDevice.id,
                    self.__class__.__name__, self.serverDisplayName(),
                    self.channelInfo.serialNumber, self.channelInfo.hubPort,
                    self.channelInfo.channel, net_info.isRemote))

    def serverKey(self):
        return (self.runtimeServerUniqueName or self.runtimeServerName or
                self.channelInfo.netInfo.serverName or "local")

    def serverDisplayName(self):
        return (self.runtimeServerName or self.runtimeServerHostname or
                self.runtimeServerUniqueName or self.channelInfo.netInfo.serverName or "any")

    def _cache_runtime_server(self, ph):
        if self.channelInfo.netInfo.isRemote:
            for attribute, method_name in (
                    ("runtimeServerName", "getServerName"),
                    ("runtimeServerUniqueName", "getServerUniqueName"),
                    ("runtimeServerHostname", "getServerHostname"),
                    ("runtimeServerPeerName", "getServerPeerName")):
                try:
                    setattr(self, attribute, getattr(ph, method_name)())
                except Exception:
                    pass
        for attribute, method_name in (
                ("runtimeDeviceName", "getDeviceName"),
                ("runtimeDeviceSKU", "getDeviceSKU"),
                ("runtimeChannelName", "getChannelName")):
            try:
                setattr(self, attribute, getattr(ph, method_name)())
            except Exception:
                pass

    def connectionType(self):
        return "remote" if self.channelInfo.netInfo.isRemote else "local"

    def connectionSummary(self):
        if not self.channelInfo.netInfo.isRemote:
            return "Local USB"
        details = []
        if self.runtimeServerHostname and self.runtimeServerHostname != self.serverDisplayName():
            details.append(self.runtimeServerHostname)
        if self.runtimeServerPeerName:
            details.append(self.runtimeServerPeerName)
        suffix = " (%s)" % ", ".join(details) if details else ""
        return "Remote via %s%s" % (self.serverDisplayName(), suffix)

    def connectionPath(self):
        parts = [self.serverDisplayName() if self.channelInfo.netInfo.isRemote else "Local USB"]
        model = self.runtimeDeviceName or self.runtimeDeviceSKU
        if model:
            if model.startswith("Phidget"):
                model = model[len("Phidget"):].strip()
            if model.endswith(" Phidget"):
                model = model[:-len(" Phidget")].strip()
            parts.append(model)
        else:
            parts.append("serial %s" % self.channelInfo.serialNumber)
        if self.channelInfo.hubPort >= 0:
            parts.append("Port %s" % self.channelInfo.hubPort)
        endpoint = self.runtimeChannelName
        if endpoint:
            parts.append(endpoint)
        elif self.channelInfo.channel >= 0:
            parts.append("channel %s" % self.channelInfo.channel)
        return "→".join(str(part) for part in parts)

    def _update_connection_states(self):
        states = {
            "connectionType": self.connectionType(),
            "serverName": self.runtimeServerName or "",
            "serverUniqueName": self.runtimeServerUniqueName or "",
            "serverHost": self.runtimeServerHostname or "",
            "serverPeer": self.runtimeServerPeerName or "",
            "connection": self.connectionSummary(),
            "connectionPath": self.connectionPath(),
        }
        for key, value in states.items():
            try:
                self.indigoDevice.updateStateOnServer(key, value=value)
            except Exception:
                self.logger.debug("Unable to update connection state %s for %s:\n%s",
                                  key, self._identity(), traceback.format_exc())

    def _cancel_attach_timer(self):
        with self._lifecycle_lock:
            self._timer_generation += 1
            timer = self.timer
            self.timer = None
        if timer is not None:
            timer.cancel()

    def _schedule_attach_timer(self):
        self._cancel_attach_timer()
        with self._lifecycle_lock:
            generation = self._timer_generation
            timer = threading.Timer(
                self.initial_connection_timeout,
                self.connectionTimeoutHandler,
                args=(generation,))
            timer.daemon = True
            self.timer = timer
        timer.start()

    def _cancel_detach_grace_timer(self):
        with self._lifecycle_lock:
            self._detach_generation += 1
            timer = self._detach_grace_timer
            self._detach_grace_timer = None
        if timer is not None:
            timer.cancel()

    def _schedule_detach_grace_timer(self):
        self._cancel_detach_grace_timer()
        with self._lifecycle_lock:
            generation = self._detach_generation
            timer = threading.Timer(
                self.DETACH_GRACE_SECONDS,
                self.detachGraceHandler,
                args=(generation,))
            timer.daemon = True
            self._detach_grace_timer = timer
        timer.start()

    def detachGraceHandler(self, generation):
        """Publish a detach only when it survives the transient grace period."""
        with self._lifecycle_lock:
            if generation != self._detach_generation or self._state != "detached":
                return
            self._detach_grace_timer = None
            if self._startup_contention_message:
                return
            self._detach_announced = True
            detached_for = time.monotonic() - self._detached_at
        try:
            self.indigoDevice.setErrorStateOnServer('Detached')
            coordinator = getattr(self.indigo_plugin, "phidgetDetachAnnounced", None)
            if coordinator is not None:
                coordinator(self, detached_for)
            else:
                self.logger.warning(
                    "Phidget remains detached after %.1f seconds; awaiting automatic reattach: %s",
                    detached_for, self._identity())
            self.indigo_plugin.triggerEvent(self, "deviceDetached")
        except Exception:
            self.logger.error("Detach grace handler failed: %s\n%s",
                              self._identity(), traceback.format_exc())

    def start(self):
        with self._lifecycle_lock:
            self._state = "starting"
            self._detached_at = time.monotonic()
            self._started_at = self._detached_at
            self._startup_contention_message = None
            self._startup_contention_expired = False
        self.logger.debug("Starting Phidget: %s", self._identity())

        try:
            self.phidget.setDeviceSerialNumber(self.channelInfo.serialNumber)
            self.phidget.setChannel(self.channelInfo.channel)
            self.phidget.setIsRemote(self.channelInfo.netInfo.isRemote)
            if self.channelInfo.netInfo.serverName:
                self.phidget.setServerName(self.channelInfo.netInfo.serverName)
            self.phidget.setIsHubPortDevice(self.channelInfo.isHubPortDevice)
            self.phidget.setHubPort(self.channelInfo.hubPort)
            self.addPhidgetHandlers()
            self._schedule_attach_timer()
            # The open handle remains open so the Phidget library can reattach it.
            self.phidget.open()
        except Exception:
            self._cancel_attach_timer()
            with self._lifecycle_lock:
                self._state = "stopped"
            try:
                self.phidget.close()
            except Exception:
                self.logger.debug("Cleanup close failed after start error: %s\n%s",
                                  self._identity(), traceback.format_exc())
            raise

    def connectionTimeoutHandler(self, generation):
        with self._lifecycle_lock:
            if generation != self._timer_generation or self._state not in ("starting", "detached"):
                return
            state = self._state
            detached_for = time.monotonic() - self._detached_at if self._detached_at else 0
            self.timer = None
        try:
            if self._startup_contention_message:
                with self._lifecycle_lock:
                    self._startup_contention_expired = True
                self.indigoDevice.setErrorStateOnServer('Channel in use')
                coordinator = getattr(
                    self.indigo_plugin, "phidgetStartupContentionExpired", None)
                if coordinator is not None:
                    coordinator(self, detached_for)
                else:
                    self.logger.error(
                        "Phidget channel remained in use for %.1f seconds. Check "
                        "for another Indigo plugin instance, Phidget Control Panel, "
                        "or another program using it: %s",
                        detached_for, self._identity())
            else:
                self.indigoDevice.setErrorStateOnServer('Detached')
                self.logger.error("Phidget remains detached after %.1f seconds (%s): %s",
                                  detached_for, state, self._identity())
        except Exception:
            self.logger.error("Attach-timeout handler failed: %s\n%s",
                              self._identity(), traceback.format_exc())

    def onErrorHandler(self, ph, errorCode, errorString):
        try:
            with self._lifecycle_lock:
                startup_elapsed = (time.monotonic() - self._started_at
                                   if self._started_at is not None else None)
                startup_contention = (
                    int(errorCode) == 2 and
                    "device is in use" in str(errorString).lower() and
                    self._state in ("starting", "detached") and
                    startup_elapsed is not None and
                    startup_elapsed <= self.initial_connection_timeout)
                if startup_contention:
                    self._startup_contention_message = str(errorString)
            if startup_contention:
                self.logger.debug(
                    "Deferring transient startup contention for up to %d seconds: %s",
                    self.initial_connection_timeout, self._identity())
                return
            deviceSuppressErrors = saved_bool(
                self.indigoDevice.pluginProps.get("suppressErrors", False))
            suppressed = ((deviceSuppressErrors and errorCode == 4103) or
                          (self.pluginSuppressErrors and errorCode in (4098, 4099)))
            log = self.logger.debug if suppressed else self.logger.error
            log("Phidget error%s code=%s message=%s: %s",
                " (suppressed)" if suppressed else "", errorCode, errorString,
                self._identity())
        except Exception:
            self.logger.error("Phidget error handler failed: %s\n%s",
                              self._identity(), traceback.format_exc())
    
    def onDetachHandler(self, ph):
        try:
            with self._lifecycle_lock:
                if self._state in ("stopping", "stopped"):
                    return
                self._state = "detached"
                self._detached_at = time.monotonic()
                self._detach_announced = False
            self._schedule_detach_grace_timer()
            self._schedule_attach_timer()
            try:
                phidget_util.logPhidgetEvent(ph, self.logger.debug, "Detached '" + self.indigoDevice.name + "'")
            except Exception:
                self.logger.debug("Unable to format detach diagnostics: %s\n%s",
                                  self._identity(), traceback.format_exc())
        except Exception:
            self.logger.error("Detach handler failed: %s\n%s",
                              self._identity(), traceback.format_exc())

    def onAttachHandler(self, ph):
        try:
            with self._lifecycle_lock:
                if self._state in ("stopping", "stopped"):
                    return
                detached_for = time.monotonic() - self._detached_at if self._detached_at else 0
                detach_announced = self._detach_announced
            self.configureAttachedPhidget(ph)
            self._cache_runtime_server(ph)
            self._update_connection_states()
        except PeripheralUnavailableError as error:
            with self._lifecycle_lock:
                self._state = "detached"
                if self._detached_at is None:
                    self._detached_at = time.monotonic()
            try:
                self.indigoDevice.setErrorStateOnServer("Initialization failed")
            except Exception:
                pass
            self.logger.error(
                "Configured peripheral unavailable: %s: %s",
                self._identity(), error)
            return
        except Exception:
            with self._lifecycle_lock:
                self._state = "detached"
                if self._detached_at is None:
                    self._detached_at = time.monotonic()
            try:
                self.indigoDevice.setErrorStateOnServer('Initialization failed')
            except Exception:
                pass
            self.logger.error("Phidget attached but initialization failed: %s\n%s",
                              self._identity(), traceback.format_exc())
            return

        try:
            self._cancel_detach_grace_timer()
            self._cancel_attach_timer()
            with self._lifecycle_lock:
                self._state = "attached"
                self._detached_at = None
                self._detach_announced = False
                startup_contention_recovered = bool(
                    self._startup_contention_message)
                startup_contention_expired = self._startup_contention_expired
                self._startup_contention_message = None
                self._startup_contention_expired = False
                self._attach_count += 1
                attach_count = self._attach_count
            if startup_contention_recovered:
                self.logger.debug(
                    "Transient startup contention cleared automatically: %s",
                    self._identity())
            attachment_announced = detach_announced or startup_contention_expired
            if attach_count == 1 or attachment_announced:
                self.indigoDevice.setErrorStateOnServer(None)
            coordinator = getattr(self.indigo_plugin, "phidgetAttachCompleted", None)
            if coordinator is not None:
                coordinator(self, detached_for, attach_count, attachment_announced)
            else:
                log = self.logger.info if detach_announced else self.logger.debug
                log("Phidget %s in %.1f seconds (attach #%d): %s",
                    "reattached" if attach_count > 1 else "attached",
                    detached_for, attach_count, self._identity())
            if attach_count == 1 or attachment_announced:
                self.indigo_plugin.triggerEvent(self, "deviceAttached")
            try:
                phidget_util.logPhidgetEvent(ph, self.logger.debug, "Attached '" + self.indigoDevice.name + "'")
            except Exception:
                self.logger.debug("Unable to format attach diagnostics: %s\n%s",
                                  self._identity(), traceback.format_exc())
        except Exception:
            self.logger.error("Attach completion handler failed: %s\n%s",
                              self._identity(), traceback.format_exc())

    def configureAttachedPhidget(self, ph):
        """Apply model-specific settings before declaring the channel healthy."""
        pass


    def stop(self):
        with self._lifecycle_lock:
            if self._state == "stopped":
                return
            self._state = "stopping"
        self._cancel_attach_timer()
        self._cancel_detach_grace_timer()
        self.logger.debug("Stopping Phidget: %s", self._identity())
        try:
            self.phidget.close()
        finally:
            with self._lifecycle_lock:
                self._state = "stopped"

    #
    # Methods to be implemented by subclasses
    #

    def addPhidgetHandlers(self):
        raise Exception("addPhidgetHandlers() must be handled by subclass")

    def getDeviceDisplayStateId(self):
        raise Exception("getDeviceDisplayStateId() must be handled by subclass")

    def getDeviceStateList(self):
        raise Exception("getDeviceStateList() must be handled by subclass")

    def stateList(self, *specifications):
        """Build simple Indigo state lists without repeating SDK boilerplate.

        Each specification is ``(kind, state_id, label)`` where kind is one of
        ``number``, ``string``, or ``bool``.
        """
        import indigo
        states = indigo.List()
        factories = {
            "number": self.indigo_plugin.getDeviceStateDictForNumberType,
            "string": self.indigo_plugin.getDeviceStateDictForStringType,
            "bool": self.indigo_plugin.getDeviceStateDictForBoolOnOffType,
        }
        for kind, state_id, label in specifications:
            states.append(factories[kind](state_id, label, state_id))
        return states

    def actionControlDevice(self, action):
        raise Exception("actionControlDevice() may be handled by subclass")

    def actionControlSensor(self, action):
        raise Exception("actionControlSensor() may be handled by subclass")


    #
    # Utility functions to help with checking setting ranges
    #

    def outOfRangeError(self, field, minValue, maxValue, value):
        self.logger.error(
            "Out of range %s for Indigo device '%s' (%d): %s "
            "(valid range: [%s-%s])",
            field, self.indigoDevice.name, self.indigoDevice.id,
            value, minValue, maxValue)

    def checkValueRange(self, fieldname, value, minValue, maxValue, zero_ok=False):
        """Helper utility to check that a value is in a range (or, optionally zero)"""
        if zero_ok and value == 0:
            return 0
        elif value < minValue or value > maxValue:
            self.outOfRangeError(field=fieldname, minValue=minValue, maxValue=maxValue, value=value)
            return None
        else:
            return value
