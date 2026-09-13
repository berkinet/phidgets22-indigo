# -*- coding: utf-8 -*-

# Originally created by Eric Perlman (@perlman):
# https://github.com/perlman/phidgets-indigo

import logging
import threading
import traceback

import indigo

from Phidget22.Devices.Log import Log
from Phidget22.LogLevel import LogLevel
from Phidget22.Net import Net, PhidgetServerType
from Phidget22.Phidget import Phidget
from Phidget22.PhidgetException import PhidgetException

from PhidgetInfo import PhidgetInfo
from actions import ActionsMixin
from config_util import saved_bool
from connection_identity import PhysicalDeviceIdentity, ServerIdentity
from device_factory import create_phidget
from discovery import DiscoveryInventory
from discovery_ui import DiscoveryUiMixin
from event_coordinator import EventCoordinator
from outage_coordinator import OutageCoordinator
from version_check import start_version_check
from version_collection import ATTACH_DELAY_SECONDS, VersionCollector
from phidget import PeripheralUnavailableError
from runtime_registry import RuntimeDeviceRegistry, registry_for


class Plugin(ActionsMixin, DiscoveryUiMixin, indigo.PluginBase):
    """Indigo lifecycle coordinator for the Phidgets 22 plugin."""

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(
            pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.plugin_file_handler.setLevel(logging.INFO)
        self.indigo_log_handler.setLevel(logging.INFO)
        self.runtimeRegistry = RuntimeDeviceRegistry()
        self._networkServerLock = threading.RLock()
        self.phidgetInfo = PhidgetInfo()
        self.logger.setLevel(logging.DEBUG)
        self.eventCoordinator = EventCoordinator()
        self.trigger_dict = self.eventCoordinator.triggers

        self.discoveryInventory = None
        self.networkMonitor = None
        self._discoveredServers = {}
        self.outageCoordinator = OutageCoordinator(
            self.logger, self.runtimeRegistry.snapshot)
        self.versionCollector = VersionCollector(self, self.logger)

    def startup(self):
        if saved_bool(self.pluginPrefs.get("phidgetApiLogging", False)):
            self.phidgetApiLogLevel = int(self.pluginPrefs["phidgetApiLogLevel"])
            self.phidgetApiLogfile = self.pluginPrefs["phidgetApiLogfile"]
            Log.enable(self.phidgetApiLogLevel, self.phidgetApiLogfile)
            level_names = {
                LogLevel.PHIDGET_LOG_CRITICAL: "Critical",
                LogLevel.PHIDGET_LOG_ERROR: "Error",
                LogLevel.PHIDGET_LOG_WARNING: "Warning",
                LogLevel.PHIDGET_LOG_DEBUG: "Debug",
                LogLevel.PHIDGET_LOG_INFO: "Info",
                LogLevel.PHIDGET_LOG_VERBOSE: "Verbose",
            }
            self.logger.warning(
                "Low-level Phidgets API logging is enabled at %s (%s); "
                "SDK messages are being written to %s",
                level_names.get(self.phidgetApiLogLevel, "unknown"),
                self.phidgetApiLogLevel, self.phidgetApiLogfile)
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

        try:
            self.networkMonitor = Net()
            self.networkMonitor.setOnServerAddedHandler(self._serverAdded)
            self.networkMonitor.setOnServerRemovedHandler(self._serverRemoved)
            Net.enableServerDiscovery(
                PhidgetServerType.PHIDGETSERVER_DEVICEREMOTE)
        except Exception as error:
            self.networkMonitor = None
            self.logger.warning(
                "Unable to start Phidget network server discovery: %s", error)

        try:
            self.discoveryInventory = DiscoveryInventory(logger=self.logger)
            self.discoveryInventory.start()
        except Exception:
            self.discoveryInventory = None
            self.logger.warning(
                "Unable to start Phidget discovery inventory:\n%s",
                traceback.format_exc())

        self.versionCollector.start()

    def _runtime_registry(self):
        return registry_for(self)

    def _serverAdded(self, net, server, kv):
        name = str(getattr(server, "name", "") or "").strip()
        if not name:
            return
        with self._networkServerLock:
            self._discoveredServers[name] = server
            monitors = [monitor for monitor in self._runtime_registry().network_servers_snapshot()
                        if monitor.serverName == name]
        self.logger.debug("Phidget network server available: %s", server)
        for monitor in monitors:
            try:
                monitor.serverAvailable(server)
            except Exception as error:
                self.logger.error(
                    "Unable to update Phidget network server device='%s': %s",
                    monitor.indigoDevice.name, error)

    def _serverRemoved(self, net, server):
        name = str(getattr(server, "name", "") or "").strip()
        if not name:
            return
        with self._networkServerLock:
            self._discoveredServers.pop(name, None)
            monitors = [monitor for monitor in self._runtime_registry().network_servers_snapshot()
                        if monitor.serverName == name]
        self.logger.debug("Phidget network server unavailable: %s", server)
        for monitor in monitors:
            try:
                monitor.serverUnavailable()
            except Exception as error:
                self.logger.error(
                    "Unable to update Phidget network server device='%s': %s",
                    monitor.indigoDevice.name, error)

    def registerNetworkServerDevice(self, monitor):
        with self._networkServerLock:
            self._runtime_registry().register_network_server(monitor)
            server = self._discoveredServers.get(monitor.serverName)
        if server is not None:
            monitor.serverAvailable(server)
        else:
            monitor.serverInitiallyUnavailable()

    def unregisterNetworkServerDevice(self, monitor):
        self._runtime_registry().remove_network_server(monitor)

    def networkServerHasChannels(self, server_name):
        """Return whether Manager discovery currently sees this server."""
        inventory = self.discoveryInventory
        if inventory is None:
            return False
        expected = str(server_name or "").strip()
        for channel in inventory.snapshot():
            if ServerIdentity.from_description(channel).matches(expected):
                return True
        return False

    def phidgetDetachAnnounced(self, phidget, detached_for):
        self.phidgetDetachStarted(phidget)
        self.outageCoordinator.detach_announced(phidget)

    def phidgetDetachStarted(self, phidget):
        """Immediately quiesce logical children of a detached provider."""
        supports = getattr(phidget, "supportsFunction", None)
        if supports is not None:
            adapter_id = phidget.indigoDevice.id
            for dependent in self._runtime_registry().dependents_of(adapter_id):
                if (dependent is phidget or
                        getattr(dependent, "adapterDeviceId", None) != adapter_id):
                    continue
                callback = getattr(dependent, "providerStopping", None)
                if callback is not None:
                    callback()

    def phidgetStartupContentionExpired(self, phidget, detached_for):
        self.outageCoordinator.startup_contention(phidget, detached_for)

    def phidgetStartupUnavailableExpired(self, phidget, detached_for, state):
        """Batch simultaneous startup timeouts by physical serial number."""
        self.outageCoordinator.startup_unavailable(
            phidget, detached_for, state)

    def phidgetStartupOpenFailureExpired(self, phidget, detached_for, message):
        """Batch repeated SDK open failures by remote server and hardware."""
        self.outageCoordinator.startup_open_failure(
            phidget, detached_for, message)

    def phidgetAttachCompleted(self, phidget, detached_for, attach_count,
                               detach_announced):
        collector = getattr(self, "versionCollector", None)
        if collector is not None:
            collector.request_collection(ATTACH_DELAY_SECONDS)
        server_key_method = getattr(phidget, "serverKey", None)
        channel_info = getattr(phidget, "channelInfo", None)
        if (server_key_method is not None and channel_info is not None and
                hasattr(channel_info, "serialNumber")):
            physical_key = PhysicalDeviceIdentity.from_wrapper(phidget)
            physical_channels = [
                configured for configured in self._runtime_registry().snapshot()
                if (getattr(configured, "channelInfo", None) is not None and
                    PhysicalDeviceIdentity.from_wrapper(configured) ==
                    physical_key)]
            if physical_channels and all(
                    configured._state == "attached"
                    for configured in physical_channels):
                self.outageCoordinator.clear_open_failure(physical_key)
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
                dependent = self._runtime_registry().get(device.id)
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
        self.outageCoordinator.attach_completed(phidget, detached_for)

    def getDeviceStateList(self, device):
        runtime_device = self._runtime_registry().get(device.id)
        if runtime_device is not None:
            states = runtime_device.getDeviceStateList()
        else:
            states = indigo.List()
        if device.deviceTypeId == "networkServer":
            return states
        for state_id, label in (
                ("connectionType", "Connection type"),
                ("serverName", "Server name"),
                ("serverUniqueName", "Server unique name"),
                ("serverHost", "Server host"),
                ("serverPeer", "Server peer"),
                ("connection", "Connection"),
                ("connectionPath", "Connection path"),
                ("firmwareVersion", "Firmware version"),
                ("firmwareVersionStatus", "Firmware version status"),
                ("firmwareUpgradeabilityStatus", "Firmware upgradeability"),
                ("latestFirmwareVersion", "Latest compatible firmware"),
                ("firmwareUpdateStatus", "Firmware update status"),
                ("firmwareCatalogVersion", "Firmware catalog version"),
                ("lastVersionCheck", "Last version check"),
                ("versionCheckError", "Version check error")):
            states.append(self.getDeviceStateDictForStringType(
                state_id, label, state_id))
        for state_id, label in (
                ("hasFirmware", "Has firmware"),
                ("firmwareUpgradeable", "Firmware upgrade supported"),
                ("firmwareUpdateAvailable", "Firmware update available"),
                ("firmwareMajorUpdateAvailable", "Major firmware update available")):
            states.append(self.getDeviceStateDictForBoolOnOffType(
                state_id, label, state_id))
        return states

    def getDeviceDisplayStateId(self, device):
        runtime_device = self._runtime_registry().get(device.id)
        if runtime_device is not None:
            return runtime_device.getDeviceDisplayStateId()
        return None

    def deviceStartComm(self, device):
        try:
            new_phidget = create_phidget(self, device)
            self._runtime_registry().register(device.id, new_phidget)
            new_phidget.start()
            device.stateListOrDisplayStateIdChanged()
        except PeripheralUnavailableError as error:
            self._runtime_registry().remove(device.id)
            device.setErrorStateOnServer("Initialization failed")
            self.logger.error(
                "Configured peripheral unavailable: device='%s' id=%s "
                "model=%s: %s", device.name, device.id,
                device.deviceTypeId, error)
        except PhidgetException as error:
            self._runtime_registry().remove(device.id)
            device.setErrorStateOnServer("Unable to start")
            self.logger.error(
                "Unable to start Phidget device='%s' id=%s model=%s: %d: %s\n%s",
                device.name, device.id, device.deviceTypeId,
                error.code, error.details, traceback.format_exc())
        except Exception:
            self._runtime_registry().remove(device.id)
            device.setErrorStateOnServer("Unable to start")
            self.logger.error(
                "Unable to start Phidget device='%s' id=%s model=%s:\n%s",
                device.name, device.id, device.deviceTypeId,
                traceback.format_exc())

    def triggerStartProcessing(self, trigger):
        self.eventCoordinator.start_processing(trigger)

    def triggerStopProcessing(self, trigger):
        self.eventCoordinator.stop_processing(trigger)

    def validateEventConfigUi(self, valuesDict, typeId, eventId):
        if typeId != "deviceDetached":
            return (True, valuesDict)
        try:
            delay = float(valuesDict.get("detachDelay", "0") or 0)
            if delay < 0 or delay > 86400:
                raise ValueError
        except (TypeError, ValueError):
            errors = indigo.Dict()
            errors["detachDelay"] = (
                "Enter a delay from 0 through 86400 seconds.")
            return (False, valuesDict, errors)
        valuesDict["detachDelay"] = "%g" % delay
        return (True, valuesDict)

    def triggerEvent(self, device, event):
        self.eventCoordinator.trigger_event(device, event)

    def deviceStopComm(self, device):
        phidget = self._runtime_registry().get(device.id)
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
            for dependent in self._runtime_registry().dependents_of(device.id):
                if (dependent is phidget or
                        getattr(dependent, "adapterDeviceId", None) != device.id):
                    continue
                callback = getattr(dependent, "providerStopping", None)
                if callback is not None:
                    callback()
        self._runtime_registry().remove(device.id)
        try:
            phidget.stop()
        except Exception:
            self.logger.error(
                "Unable to stop Phidget device='%s' id=%s:\n%s",
                device.name, device.id, traceback.format_exc())

    def shutdown(self):
        collector = getattr(self, "versionCollector", None)
        if collector is not None:
            collector.stop()
        self.eventCoordinator.stop()
        self.outageCoordinator.stop()

        if self.networkMonitor is not None:
            try:
                self.networkMonitor.setOnServerAddedHandler(None)
                self.networkMonitor.setOnServerRemovedHandler(None)
            except Exception:
                self.logger.debug(
                    "Unable to stop Phidget server monitoring:\n%s",
                    traceback.format_exc())
            self.networkMonitor = None

        active = self._runtime_registry().items_snapshot()
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
        self._runtime_registry().clear()

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

    def collectVersionsNow(self):
        self.logger.info("Starting requested read-only Phidget version collection")
        self.versionCollector.request_collection()

    def __del__(self):
        indigo.PluginBase.__del__(self)
