# -*- coding: utf-8 -*-

# Originally created by Eric Perlman (@perlman):
# https://github.com/perlman/phidgets-indigo

import logging
import threading
import time
import traceback
from contextlib import nullcontext

import indigo

from Phidget22.Devices.Log import Log
from Phidget22.Net import Net, PhidgetServerType
from Phidget22.Phidget import Phidget
from Phidget22.PhidgetException import PhidgetException

from PhidgetInfo import PhidgetInfo
from actions import ActionsMixin
from device_factory import create_phidget
from discovery import DiscoveryInventory
from discovery_ui import DiscoveryUiMixin
from version_check import start_version_check
from phidget import PeripheralUnavailableError


class Plugin(ActionsMixin, DiscoveryUiMixin, indigo.PluginBase):
    """Indigo lifecycle coordinator for the Phidgets 22 plugin."""

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(
            pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.plugin_file_handler.setLevel(logging.INFO)
        self.indigo_log_handler.setLevel(logging.INFO)
        self.activePhidgets = {}
        self._activePhidgetsLock = threading.RLock()
        self.phidgetInfo = PhidgetInfo(phidgetInfoFile="../Resources/phidgets.json")
        self.logger.setLevel(logging.DEBUG)
        self.trigger_dict = {}

        self.discoveryInventory = None
        self.networkMonitor = None
        self._outageLock = threading.RLock()
        self._detachBatches = {}
        self._recoveryBatches = {}
        self._startupContentionBatches = {}
        self._batchTimers = {}
        self._serverOutages = {}

    def startup(self):
        if self.pluginPrefs.get("phidgetApiLogging", False):
            self.phidgetApiLogLevel = int(self.pluginPrefs["phidgetApiLogLevel"])
            self.phidgetApiLogfile = self.pluginPrefs["phidgetApiLogfile"]
            Log.enable(self.phidgetApiLogLevel, self.phidgetApiLogfile)
        else:
            Log.disable()
            self.phidgetApiLogLevel = 0

        loglevel = int(self.pluginPrefs.get("phidgetPluginLoggingLevel", "0"))
        if loglevel:
            self.plugin_file_handler.setLevel(loglevel)
            self.indigo_log_handler.setLevel(loglevel)
            self.logger.debug(
                "Setting log level to %s" % logging.getLevelName(loglevel))

        library_version = Phidget.getLibraryVersion()
        self.logger.debug("Using %s" % library_version)
        start_version_check(library_version, self.logger)

        Net.enableServerDiscovery(PhidgetServerType.PHIDGETSERVER_DEVICEREMOTE)
        try:
            self.networkMonitor = Net()
            self.networkMonitor.setOnServerAddedHandler(self._serverAdded)
            self.networkMonitor.setOnServerRemovedHandler(self._serverRemoved)
        except Exception:
            self.networkMonitor = None
            self.logger.warning(
                "Unable to monitor Phidget network servers:\n%s",
                traceback.format_exc())

        try:
            self.discoveryInventory = DiscoveryInventory(logger=self.logger)
            self.discoveryInventory.start()
        except Exception:
            self.discoveryInventory = None
            self.logger.warning(
                "Unable to start Phidget discovery inventory:\n%s",
                traceback.format_exc())

    def _serverAdded(self, net, server, kv):
        self.logger.debug("Phidget network server available: %s", server)

    def _serverRemoved(self, net, server):
        self.logger.debug("Phidget network server unavailable: %s", server)

    def _channelsForServer(self, server_key):
        return [phidget for phidget in list(self.activePhidgets.values())
                if phidget.channelInfo.netInfo.isRemote and
                phidget.serverKey() == server_key]

    def _scheduleBatch(self, kind, server_key, callback):
        timer_key = (kind, server_key)
        with self._outageLock:
            old_timer = self._batchTimers.pop(timer_key, None)
            timer = threading.Timer(0.3, callback, args=(server_key,))
            timer.daemon = True
            self._batchTimers[timer_key] = timer
        if old_timer is not None:
            old_timer.cancel()
        timer.start()

    def phidgetDetachAnnounced(self, phidget, detached_for):
        supports = getattr(phidget, "supportsFunction", None)
        if supports is not None:
            adapter_id = phidget.indigoDevice.id
            for dependent in list(self.activePhidgets.values()):
                if (dependent is phidget or
                        getattr(dependent, "adapterDeviceId", None) != adapter_id):
                    continue
                callback = getattr(dependent, "providerStopping", None)
                if callback is not None:
                    callback()
        server_key = phidget.serverKey()
        with self._outageLock:
            self._detachBatches.setdefault(server_key, set()).add(phidget)
        self._scheduleBatch("detach", server_key, self._flushDetachBatch)

    def phidgetStartupContentionExpired(self, phidget, detached_for):
        physical_key = (
            phidget.serverKey(), phidget.channelInfo.serialNumber,
            phidget.channelInfo.hubPort)
        with self._outageLock:
            self._startupContentionBatches.setdefault(
                physical_key, {})[phidget] = detached_for
        self._scheduleBatch(
            "startup-contention", physical_key,
            self._flushStartupContentionBatch)

    def _flushStartupContentionBatch(self, physical_key):
        with self._outageLock:
            self._batchTimers.pop(
                ("startup-contention", physical_key), None)
            pending = self._startupContentionBatches.pop(physical_key, {})
        affected = [
            (phidget, detached_for)
            for phidget, detached_for in pending.items()
            if (phidget._state != "attached" and
                phidget._startup_contention_message)
        ]
        if not affected:
            return
        names = ", ".join(sorted(
            "'%s' (channel %s)" % (
                phidget.indigoDevice.name, phidget.channelInfo.channel)
            for phidget, _ in affected))
        longest = max(detached_for for _, detached_for in affected)
        first = affected[0][0]
        self.logger.error(
            "Phidget channels remained in use for %.1f seconds on server '%s', "
            "serial %s, hub port %s: %s. Check for another Indigo plugin "
            "instance, Phidget Control Panel, or another program using them.",
            longest, first.serverDisplayName(),
            first.channelInfo.serialNumber, first.channelInfo.hubPort, names)

    def _flushDetachBatch(self, server_key):
        with self._outageLock:
            self._batchTimers.pop(("detach", server_key), None)
            pending = self._detachBatches.pop(server_key, set())
        affected = [phidget for phidget in self._channelsForServer(server_key)
                    if phidget._state == "detached" and phidget._detach_announced]
        configured = self._channelsForServer(server_key)
        if len(configured) > 1 and len(affected) == len(configured):
            detached_at = min(phidget._detached_at for phidget in affected)
            serials = {phidget.channelInfo.serialNumber for phidget in affected}
            with self._outageLock:
                self._serverOutages[server_key] = {
                    "detachedAt": detached_at,
                    "channelCount": len(affected),
                    "serialCount": len(serials),
                    "displayName": affected[0].serverDisplayName(),
                }
            self.logger.warning(
                "Phidget server '%s' disconnected; %d configured channels across %d "
                "physical Phidgets are unavailable and awaiting automatic reattach",
                affected[0].serverDisplayName(), len(affected), len(serials))
            return

        for phidget in pending:
            if phidget._state == "detached" and phidget._detach_announced:
                detached_for = time.monotonic() - phidget._detached_at
                self.logger.warning(
                    "Phidget remains detached after %.1f seconds; awaiting automatic "
                    "reattach: %s", detached_for, phidget._identity())

    def phidgetAttachCompleted(self, phidget, detached_for, attach_count,
                               detach_announced):
        supports = getattr(phidget, "supportsFunction", None)
        if supports is not None:
            adapter_id = phidget.indigoDevice.id
            adapter_properties = {
                "lcd": "lcdAdapterDeviceId",
                "bme280": "bmeAdapterDeviceId",
                "sgp41": "sgpAdapterDeviceId",
            }
            for device in indigo.devices:
                property_name = adapter_properties.get(
                    getattr(device, "deviceTypeId", None))
                if (getattr(device, "pluginId", None) != self.pluginId or
                        property_name is None or
                        not getattr(device, "enabled", True)):
                    continue
                try:
                    selected_adapter = int(device.pluginProps.get(
                        property_name, 0))
                except (TypeError, ValueError):
                    continue
                if selected_adapter != adapter_id:
                    continue
                dependent = self.activePhidgets.get(device.id)
                if dependent is None:
                    self.deviceStartComm(device)
                elif (getattr(dependent, "_state", None) != "attached" or
                      attach_count > 1):
                    callback = getattr(dependent, "providerReattached", None)
                    if callback is not None:
                        try:
                            callback()
                        except PeripheralUnavailableError as error:
                            dependent.indigoDevice.setErrorStateOnServer(
                                "Initialization failed")
                            self.logger.error(
                                "Configured peripheral unavailable: "
                                "device='%s': %s",
                                dependent.indigoDevice.name, error)
                        except Exception:
                            dependent.indigoDevice.setErrorStateOnServer(
                                "Initialization failed")
                            self.logger.error(
                                "Unable to reinitialize I2C peripheral "
                                "device='%s':\n%s",
                                dependent.indigoDevice.name,
                                traceback.format_exc())
        if not detach_announced:
            self.logger.debug(
                "Phidget %s in %.1f seconds (attach #%d): %s",
                "reattached" if attach_count > 1 else "attached",
                detached_for, attach_count, phidget._identity())
            return
        server_key = phidget.serverKey()
        with self._outageLock:
            self._recoveryBatches.setdefault(server_key, {})[phidget] = detached_for
        self._scheduleBatch("recovery", server_key, self._flushRecoveryBatch)

    def _flushRecoveryBatch(self, server_key):
        with self._outageLock:
            self._batchTimers.pop(("recovery", server_key), None)
            pending = self._recoveryBatches.pop(server_key, {})
            outage = self._serverOutages.get(server_key)
        configured = self._channelsForServer(server_key)
        if outage is not None:
            if configured and all(
                    phidget._state == "attached" for phidget in configured):
                duration = time.monotonic() - outage["detachedAt"]
                self.logger.info(
                    "Phidget server '%s' recovered after %.1f seconds; all %d "
                    "configured channels across %d physical Phidgets reattached",
                    outage["displayName"], duration, outage["channelCount"],
                    outage["serialCount"])
                with self._outageLock:
                    self._serverOutages.pop(server_key, None)
            return

        for phidget, detached_for in pending.items():
            self.logger.info(
                "Phidget reattached in %.1f seconds (attach #%d): %s",
                detached_for, phidget._attach_count, phidget._identity())

    def getDeviceStateList(self, device):
        if device.id in self.activePhidgets:
            states = self.activePhidgets[device.id].getDeviceStateList()
        else:
            states = indigo.List()
        for state_id, label in (
                ("connectionType", "Connection type"),
                ("serverName", "Server name"),
                ("serverUniqueName", "Server unique name"),
                ("serverHost", "Server host"),
                ("serverPeer", "Server peer"),
                ("connection", "Connection"),
                ("connectionPath", "Connection path")):
            states.append(self.getDeviceStateDictForStringType(
                state_id, label, state_id))
        return states

    def getDeviceDisplayStateId(self, device):
        if device.id in self.activePhidgets:
            return self.activePhidgets[device.id].getDeviceDisplayStateId()
        return None

    def deviceStartComm(self, device):
        try:
            new_phidget = create_phidget(self, device)
            with getattr(self, "_activePhidgetsLock", nullcontext()):
                self.activePhidgets[device.id] = new_phidget
            new_phidget.start()
            device.stateListOrDisplayStateIdChanged()
        except PeripheralUnavailableError as error:
            with getattr(self, "_activePhidgetsLock", nullcontext()):
                self.activePhidgets.pop(device.id, None)
            device.setErrorStateOnServer("Initialization failed")
            self.logger.error(
                "Configured peripheral unavailable: device='%s' id=%s "
                "model=%s: %s", device.name, device.id,
                device.deviceTypeId, error)
        except PhidgetException as error:
            with getattr(self, "_activePhidgetsLock", nullcontext()):
                self.activePhidgets.pop(device.id, None)
            device.setErrorStateOnServer("Unable to start")
            self.logger.error(
                "Unable to start Phidget device='%s' id=%s model=%s: %d: %s\n%s",
                device.name, device.id, device.deviceTypeId,
                error.code, error.details, traceback.format_exc())
        except Exception:
            with getattr(self, "_activePhidgetsLock", nullcontext()):
                self.activePhidgets.pop(device.id, None)
            device.setErrorStateOnServer("Unable to start")
            self.logger.error(
                "Unable to start Phidget device='%s' id=%s model=%s:\n%s",
                device.name, device.id, device.deviceTypeId,
                traceback.format_exc())

    def triggerStartProcessing(self, trigger):
        phidget_device_id = int(trigger.pluginProps["indigoDevice"])
        self.trigger_dict[trigger.id] = {
            "devid": phidget_device_id,
            "event": trigger.pluginTypeId,
        }

    def triggerStopProcessing(self, trigger):
        if trigger.id in self.trigger_dict:
            del self.trigger_dict[trigger.id]

    def triggerEvent(self, device, event):
        for trigger_id, trigger in self.trigger_dict.items():
            if (trigger["devid"] == device.indigoDevice.id and
                    trigger["event"] == event):
                indigo.trigger.execute(trigger_id)

    def deviceStopComm(self, device):
        phidget = self.activePhidgets.get(device.id)
        if phidget is None:
            self.logger.debug(
                "Stop requested for inactive Phidget device='%s' id=%s",
                device.name, device.id)
            return
        supports = getattr(phidget, "supportsFunction", None)
        if supports is not None:
            # Indigo may stop a shared DataAdapter before its logical LCD.
            # Quiesce dependent timers while the provider is still attached so
            # an in-flight frame finishes before the bus is closed.
            for dependent in list(self.activePhidgets.values()):
                if (dependent is phidget or
                        getattr(dependent, "adapterDeviceId", None) != device.id):
                    continue
                callback = getattr(dependent, "providerStopping", None)
                if callback is not None:
                    callback()
        with getattr(self, "_activePhidgetsLock", nullcontext()):
            self.activePhidgets.pop(device.id, None)
        try:
            phidget.stop()
        except Exception:
            self.logger.error(
                "Unable to stop Phidget device='%s' id=%s:\n%s",
                device.name, device.id, traceback.format_exc())

    def shutdown(self):
        with self._outageLock:
            timers = list(self._batchTimers.values())
            self._batchTimers.clear()
            self._detachBatches.clear()
            self._recoveryBatches.clear()
            self._startupContentionBatches.clear()
            self._serverOutages.clear()
        for timer in timers:
            timer.cancel()

        if self.networkMonitor is not None:
            try:
                self.networkMonitor.setOnServerAddedHandler(None)
                self.networkMonitor.setOnServerRemovedHandler(None)
            except Exception:
                self.logger.debug(
                    "Unable to stop Phidget server monitoring:\n%s",
                    traceback.format_exc())
            self.networkMonitor = None

        with getattr(self, "_activePhidgetsLock", nullcontext()):
            active = list(self.activePhidgets.items())
        # Quiesce all logical children before any shared provider can close.
        for _, provider in active:
            if getattr(provider, "supportsFunction", None) is None:
                continue
            provider_id = provider.indigoDevice.id
            for _, dependent in active:
                if getattr(dependent, "adapterDeviceId", None) != provider_id:
                    continue
                callback = getattr(dependent, "providerStopping", None)
                if callback is not None:
                    try:
                        callback()
                    except Exception:
                        self.logger.warning(
                            "Unable to quiesce I2C dependent during shutdown:\n%s",
                            traceback.format_exc())
        # Stop providers last, after dependent timers and transactions settle.
        active.sort(key=lambda item: bool(
            getattr(item[1], "supportsFunction", None)))
        for device_id, phidget in active:
            try:
                phidget.stop()
            except Exception:
                self.logger.warning(
                    "Unable to stop active Phidget id=%s during shutdown:\n%s",
                    device_id, traceback.format_exc())
        with getattr(self, "_activePhidgetsLock", nullcontext()):
            self.activePhidgets.clear()

        if self.discoveryInventory is not None:
            try:
                self.discoveryInventory.stop()
            except Exception:
                self.logger.warning(
                    "Unable to stop Phidget discovery inventory:\n%s",
                    traceback.format_exc())
            self.discoveryInventory = None

        try:
            Phidget.finalize(0)
        except Exception:
            self.logger.warning(
                "Unable to finalize Phidget library:\n%s",
                traceback.format_exc())

    def __del__(self):
        indigo.PluginBase.__del__(self)
