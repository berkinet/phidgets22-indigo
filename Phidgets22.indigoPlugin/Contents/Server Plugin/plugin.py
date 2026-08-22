# -*- coding: utf-8 -*-

# Originally created by Eric Perlman (@perlman):
# https://github.com/perlman/phidgets-indigo

import indigo
import logging
import threading
import time
import traceback

# Phidget libraries
from Phidget22.Devices.Log import Log
from Phidget22.Net import Net, PhidgetServerType
from Phidget22.Phidget import Phidget
from Phidget22.PhidgetException import PhidgetException
from PhidgetInfo import PhidgetInfo
from discovery import (CHANNEL_CLASSES_BY_DEVICE_TYPE, DiscoveryInventory,
                       device_token, format_channel, format_network_diagram,
                       server_token, target_token)

# Classes to describe network & channel search info
from phidget import ChannelInfo, NetInfo

# Our wrappers around phidget objects
from voltageinput import VoltageInputPhidget
from voltageratioinput import VoltageRatioInputPhidget
from digitaloutput import DigitalOutputPhidget
from temperaturesensor import TemperatureSensorPhidget
from digitalinput import DigitalInputPhidget
from frequencycounter import FrequencyCounterPhidget
from humiditysensor import HumiditySensorPhidget
from version_check import start_version_check

class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.plugin_file_handler.setLevel(logging.INFO)  # Master Logging Level for Plugin Log file
        self.indigo_log_handler.setLevel(logging.INFO)   # Logging level for Indigo Event Log

        self.activePhidgets = {} # Map between Indigio ID and current instance of phidget

        self.phidgetInfo = PhidgetInfo(phidgetInfoFile='../Resources/phidgets.json')

        self.logger.setLevel(logging.DEBUG)

        self.trigger_dict = {}

        self.discoveryInventory = None
        self.networkMonitor = None
        self._outageLock = threading.RLock()
        self._detachBatches = {}
        self._recoveryBatches = {}
        self._batchTimers = {}
        self._serverOutages = {}


    def startup(self):
        # Setup logging in the phidgets library
        if self.pluginPrefs.get('phidgetApiLogging', False):
            self.phidgetApiLogLevel = int(self.pluginPrefs['phidgetApiLogLevel'])
            self.phidgetApiLogfile = self.pluginPrefs['phidgetApiLogfile']
            Log.enable(self.phidgetApiLogLevel, self.phidgetApiLogfile)
        else:
            Log.disable()
            self.phidgetApiLogLevel = 0

        loglevel = int(self.pluginPrefs.get('phidgetPluginLoggingLevel', '0'))
        if loglevel:
            self.plugin_file_handler.setLevel(loglevel)  # Master Logging Level for Plugin Log file
            self.indigo_log_handler.setLevel(loglevel)   # Logging level for Indigo Event Log
            self.logger.debug("Setting log level to %s" % logging.getLevelName(loglevel))

        library_version = Phidget.getLibraryVersion()
        self.logger.debug("Using %s" % library_version)
        start_version_check(library_version, self.logger)

        # Should this be configurable?
        Net.enableServerDiscovery(PhidgetServerType.PHIDGETSERVER_DEVICEREMOTE)
        try:
            self.networkMonitor = Net()
            self.networkMonitor.setOnServerAddedHandler(self._serverAdded)
            self.networkMonitor.setOnServerRemovedHandler(self._serverRemoved)
        except Exception:
            self.networkMonitor = None
            self.logger.warning("Unable to monitor Phidget network servers:\n%s",
                                traceback.format_exc())

        # Maintain a read-only inventory for diagnostics and future UI design.
        # Discovery failure must not prevent existing configured devices from starting.
        try:
            self.discoveryInventory = DiscoveryInventory(logger=self.logger)
            self.discoveryInventory.start()
        except Exception:
            self.discoveryInventory = None
            self.logger.warning("Unable to start Phidget discovery inventory:\n%s", traceback.format_exc())

    #
    # Methods for working with interactive Indigo UI
    #

    def validatePrefsConfigUi(self, valuesDict):
        try:
            attach_timeout = int(valuesDict.get('attachTimeout', '5'))
            if attach_timeout <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors = indigo.Dict()
            errors['attachTimeout'] = "Enter a whole number greater than zero."
            return False, valuesDict, errors

        valuesDict['attachTimeout'] = str(attach_timeout)
        return True

    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        """Initialize, safely migrate, and collapse discovery selections."""
        values = indigo.Dict(pluginProps)
        values['configurationMigrated'] = False
        values['observedConnection'] = self._observedConnectionForDevice(devId)
        defaults = {
            'discoveredServer': 'manual',
            'discoveredDevice': 'selectServer',
            'discoveredPort': 'selectDevice',
            'discoveredTarget': 'selectPort',
            'discoveredChannel': 'selectTarget',
        }
        for key, value in defaults.items():
            if values.get(key, None) is None:
                values[key] = value

        # Older devices have a complete native address but no discovery tokens.
        # Reconstruct the dialog hierarchy only when one live channel matches;
        # this changes no stored configuration unless the user later saves.
        selected_channel = values.get('discoveredChannel', '')
        resolved_channel = (self.discoveryInventory.resolve_channel(selected_channel)
                            if self.discoveryInventory is not None else None)
        if self.discoveryInventory is not None and resolved_channel is None:
            recovered = self.discoveryInventory.selection_for_saved_address(typeId, values)
            if recovered is not None:
                for key, value in recovered.items():
                    values[key] = value
                values['configurationMigrated'] = True
        return (self.menuChanged(values, typeId, devId), indigo.Dict())

    def _observedConnectionForDevice(self, devId):
        if devId:
            try:
                device_states = indigo.devices[devId].states
                return (device_states.get('connectionPath') or
                        device_states.get('connection') or
                        'Not yet observed')
            except Exception:
                pass
        return 'Not yet observed'

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        # Indigo renders enabled text fields in normal black text. Treat this
        # display-only value as immutable by restoring it before every save.
        valuesDict['observedConnection'] = self._observedConnectionForDevice(devId)
        selected_channel = valuesDict.get('discoveredChannel', '')
        if selected_channel and selected_channel not in ('manual', 'selectDevice', 'selectChannel'):
            description = (self.discoveryInventory.resolve_channel(selected_channel)
                           if self.discoveryInventory is not None else None)
            expected_class = CHANNEL_CLASSES_BY_DEVICE_TYPE.get(typeId)
            if (description is None or description.get('channelClassName') != expected_class or
                    device_token(description) != valuesDict.get('discoveredDevice', '') or
                    (description is not None and description.get('deviceClass') == 21 and
                     target_token(description) != valuesDict.get('discoveredTarget', '')) or
                    (valuesDict.get('discoveredServer', '') and
                     server_token(description) != valuesDict.get('discoveredServer', ''))):
                errors = indigo.Dict()
                errors['discoveredChannel'] = "Select an available channel for the chosen Phidget."
                errors['showAlertText'] = "The discovered channel is no longer available or is not compatible."
                return (False, valuesDict, errors)

            valuesDict['serialNumber'] = str(description.get('serialNumber'))
            valuesDict['channel'] = str(description.get('channel'))
            valuesDict['serverName'] = description.get('serverName') or description.get('serverUniqueName') or ''
            is_vint = description.get('deviceClass') == 21
            valuesDict['isVintHub'] = is_vint
            valuesDict['isVintDevice'] = bool(is_vint and not description.get('isHubPortDevice'))
            valuesDict['hubPort'] = str(description.get('hubPort')) if is_vint else ''

        # Look to see if there ia a label for the serial number
        addrIndex = str(valuesDict['serialNumber'])
        varName = "p22_" + addrIndex
        if varName in indigo.variables:
            phLabel = str(indigo.variables[varName].value)
            if phLabel != "":  # If we got a non-null value, use it
                addrIndex = phLabel

        # Set an address here
        # TODO: dynamic address updating would require replacing the device and using didDeviceCommPropertyChange to prevent respawn
        if bool(valuesDict['isVintHub']) and not bool(valuesDict['isVintDevice']):
            valuesDict['address'] = addrIndex + "|p" + valuesDict['hubPort']
        elif not bool(valuesDict['isVintHub']) and not bool(valuesDict['isVintDevice']):   # an interfaceKit
            if typeId == 'digitalInput':
                valuesDict['address'] = addrIndex + "|di-" + valuesDict['channel']
            elif typeId == 'digitalOutput':
                valuesDict['address'] = addrIndex + "|do-" + valuesDict['channel']
            elif typeId == 'voltageRatioInput':
                valuesDict['address'] = addrIndex + "|vr-" + valuesDict['channel']
            elif typeId == 'voltageInput':
                valuesDict['address'] = addrIndex + "|av-" + valuesDict['channel']
            else:
                valuesDict['address'] = addrIndex + "|p-" + valuesDict['channel']
        elif 'hubPort' in valuesDict and len(valuesDict['hubPort']) > 0 and 'channel' in valuesDict and len(valuesDict['channel']) > 0:
            valuesDict[u'address'] = addrIndex + "|p" + valuesDict['hubPort'] + "-c" + valuesDict['channel']
        elif 'hubPort' in valuesDict and len(valuesDict['hubPort']):
            valuesDict[u'address'] = addrIndex + "|p" + valuesDict['hubPort']
        elif 'channel' in valuesDict and len(valuesDict['channel']) > 0:
            valuesDict[u'address'] = addrIndex + "|c" + valuesDict['channel']
        else:
            valuesDict[u'address'] = addrIndex

        # The migration notice is session-only. Saving the reconstructed
        # discovery tokens completes the migration and dismisses the notice.
        valuesDict['configurationMigrated'] = False
        return (True, valuesDict)

    def getPhidgetTypeMenu(self, filter="", valuesDict=None, typeId="", targetId=0):
        classes = filter.split(',')
        return self.phidgetInfo.getPhidgetTypeMenu(classes)

    def getDiscoveredDeviceMenu(self, filter="", valuesDict=None, typeId="", targetId=0):
        if self.discoveryInventory is None:
            return [("manual", "Discovery unavailable — use manual settings below")]
        selected_server = valuesDict.get('discoveredServer', '') if valuesDict is not None else ''
        if not selected_server or selected_server == 'manual':
            return [("selectServer", "")]
        choices = self.discoveryInventory.device_choices_for_server(typeId, selected_server)
        return [("selectDevice", "Select a Phidget")] + choices

    def getDiscoveredServerMenu(self, filter="", valuesDict=None, typeId="", targetId=0):
        if self.discoveryInventory is None:
            return [("manual", "Discovery unavailable — use manual settings below")]
        return [("manual", "Select a server")] + self.discoveryInventory.server_choices(typeId)

    def getDiscoveredChannelMenu(self, filter="", valuesDict=None, typeId="", targetId=0):
        selected_device = valuesDict.get('discoveredDevice', '') if valuesDict is not None else ''
        if self.discoveryInventory is None or not selected_device or selected_device in ('manual', 'selectServer', 'selectDevice'):
            return [("selectDevice", "")]
        selected_target = valuesDict.get('discoveredTarget', '') if valuesDict is not None else ''
        if self.discoveryInventory.is_vint_device(selected_device) and selected_target in ('', 'selectPort', 'selectTarget'):
            return [("selectTarget", "")]
        choices = self.discoveryInventory.channel_choices(typeId, selected_device, selected_target)
        return [("selectChannel", "Select a channel")] + choices

    def getDiscoveredPortMenu(self, filter="", valuesDict=None, typeId="", targetId=0):
        selected_device = valuesDict.get('discoveredDevice', '') if valuesDict is not None else ''
        if self.discoveryInventory is None or not self.discoveryInventory.is_vint_device(selected_device):
            return [("selectDevice", "")]
        return [("selectPort", "Select a port")] + self.discoveryInventory.port_choices(typeId, selected_device)

    def getDiscoveredTargetMenu(self, filter="", valuesDict=None, typeId="", targetId=0):
        selected_port = valuesDict.get('discoveredPort', '') if valuesDict is not None else ''
        if self.discoveryInventory is None or selected_port in ('', 'selectDevice', 'selectPort'):
            return [("selectPort", "")]
        return [("selectTarget", "Select a device or function")] + self.discoveryInventory.target_choices(typeId, selected_port)

    def menuChanged(self, valuesDict, typeId, devId):
        """Refresh dependent menus and auto-select every unambiguous level."""
        inventory = self.discoveryInventory
        if inventory is None:
            return valuesDict

        valid_servers = inventory.server_choices(typeId)
        selected_server = valuesDict.get('discoveredServer', '')
        if selected_server not in [choice[0] for choice in valid_servers] and len(valid_servers) == 1:
            selected_server = valid_servers[0][0]
            valuesDict['discoveredServer'] = selected_server
        server_selected = selected_server in [choice[0] for choice in valid_servers]
        valuesDict['serverSelected'] = server_selected

        selected_device = valuesDict.get('discoveredDevice', '')
        valid_devices = inventory.device_choices_for_server(typeId, selected_server) if server_selected else []
        if selected_device not in [choice[0] for choice in valid_devices] and len(valid_devices) == 1:
            selected_device = valid_devices[0][0]
            valuesDict['discoveredDevice'] = selected_device
        device_selected = selected_device in [choice[0] for choice in valid_devices]
        valuesDict['deviceSelected'] = device_selected

        vint_selected = bool(device_selected and inventory.is_vint_device(selected_device))
        valuesDict['vintSelected'] = vint_selected
        selected_device_description = inventory.resolve_device(selected_device) if device_selected else None
        if selected_device_description is not None and not vint_selected:
            valuesDict['serialNumber'] = str(selected_device_description.get('serialNumber'))
            valuesDict['serverName'] = (selected_device_description.get('serverName') or
                                        selected_device_description.get('serverUniqueName') or '')
            valuesDict['isVintHub'] = False
            valuesDict['isVintDevice'] = False
            valuesDict['hubPort'] = ''
        selected_port = valuesDict.get('discoveredPort', '')
        valid_ports = inventory.port_choices(typeId, selected_device) if vint_selected else []
        if selected_port not in [choice[0] for choice in valid_ports] and len(valid_ports) == 1:
            selected_port = valid_ports[0][0]
            valuesDict['discoveredPort'] = selected_port
        port_selected = selected_port in [choice[0] for choice in valid_ports]
        valuesDict['portSelected'] = port_selected
        selected_target = valuesDict.get('discoveredTarget', '')
        valid_targets = inventory.target_choices(typeId, selected_port) if port_selected else []
        if selected_target not in [choice[0] for choice in valid_targets] and len(valid_targets) == 1:
            selected_target = valid_targets[0][0]
            valuesDict['discoveredTarget'] = selected_target
        target_selected = selected_target in [choice[0] for choice in valid_targets]
        valuesDict['targetSelected'] = target_selected
        channel_parent_selected = bool(device_selected and (not vint_selected or target_selected))
        valuesDict['channelParentSelected'] = channel_parent_selected

        compatible_channels = (inventory.channel_choices(
            typeId, selected_device, selected_target if vint_selected else None)
            if channel_parent_selected else [])
        valuesDict['channelChoiceRequired'] = len(compatible_channels) > 1
        if len(compatible_channels) == 1:
            valuesDict['discoveredChannel'] = compatible_channels[0][0]
        elif valuesDict.get('discoveredChannel', '') not in [choice[0] for choice in compatible_channels]:
            valuesDict['discoveredChannel'] = 'selectChannel'

        selected_channel = valuesDict.get('discoveredChannel', '')
        description = inventory.resolve_channel(selected_channel) if device_selected else None
        resolved_selection = bool(
            description is not None and device_token(description) == selected_device and
            (not vint_selected or target_token(description) == selected_target))
        valuesDict['derivedFieldsEnabled'] = not resolved_selection
        if resolved_selection:
            valuesDict['serialNumber'] = str(description.get('serialNumber'))
            valuesDict['channel'] = str(description.get('channel'))
            valuesDict['serverName'] = description.get('serverName') or description.get('serverUniqueName') or ''
            is_vint = description.get('deviceClass') == 21
            valuesDict['isVintHub'] = is_vint
            valuesDict['isVintDevice'] = bool(is_vint and not description.get('isHubPortDevice'))
            valuesDict['hubPort'] = str(description.get('hubPort')) if is_vint else ''
        return valuesDict

    def logDiscoveryInventory(self):
        """Log the currently observed channels without modifying Indigo devices."""
        if self.discoveryInventory is None:
            self.logger.warning("Phidget discovery inventory is unavailable")
            return

        channels = self.discoveryInventory.snapshot()
        self.logger.info("Discovered Phidget inventory: %d channel(s)", len(channels))
        for channel in channels:
            self.logger.info("  %s", format_channel(channel))

    def printPhidgetsNetworkDiagram(self):
        """Print the live discovery inventory as a server/device/port tree."""
        if self.discoveryInventory is None:
            self.logger.warning("Phidget discovery inventory is unavailable")
            return
        for line in format_network_diagram(self.discoveryInventory.snapshot()):
            self.logger.info("%s", line)

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
        server_key = phidget.serverKey()
        with self._outageLock:
            self._detachBatches.setdefault(server_key, set()).add(phidget)
        self._scheduleBatch("detach", server_key, self._flushDetachBatch)

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
                "Phidget server '%s' disconnected; %d configured channels across %d physical "
                "Phidgets are unavailable and awaiting automatic reattach",
                affected[0].serverDisplayName(), len(affected), len(serials))
            return

        for phidget in pending:
            if phidget._state == "detached" and phidget._detach_announced:
                detached_for = time.monotonic() - phidget._detached_at
                self.logger.warning(
                    "Phidget remains detached after %.1f seconds; awaiting automatic reattach: %s",
                    detached_for, phidget._identity())

    def phidgetAttachCompleted(self, phidget, detached_for, attach_count, detach_announced):
        if not detach_announced:
            self.logger.debug("Phidget %s in %.1f seconds (attach #%d): %s",
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
            if configured and all(phidget._state == "attached" for phidget in configured):
                duration = time.monotonic() - outage["detachedAt"]
                self.logger.info(
                    "Phidget server '%s' recovered after %.1f seconds; all %d configured channels "
                    "across %d physical Phidgets reattached",
                    outage["displayName"], duration, outage["channelCount"],
                    outage["serialCount"])
                with self._outageLock:
                    self._serverOutages.pop(server_key, None)
            return

        for phidget, detached_for in pending.items():
            self.logger.info("Phidget reattached in %.1f seconds (attach #%d): %s",
                             detached_for,
                             phidget._attach_count, phidget._identity())

    #
    # Interact with the phidgets
    #

    def getDeviceStateList(self, device):
        if device.id in self.activePhidgets:
            states = self.activePhidgets[device.id].getDeviceStateList()
        else:
            states = indigo.List()
        for state_id, label in (
                ('connectionType', 'Connection type'),
                ('serverName', 'Server name'),
                ('serverUniqueName', 'Server unique name'),
                ('serverHost', 'Server host'),
                ('serverPeer', 'Server peer'),
                ('connection', 'Connection'),
                ('connectionPath', 'Connection path')):
            states.append(self.getDeviceStateDictForStringType(state_id, label, state_id))
        return states

    def getDeviceDisplayStateId(self, device):
        if device.id in self.activePhidgets:
            return self.activePhidgets[device.id].getDeviceDisplayStateId()
        else:
            return None

    def actionControlDevice(self, action, device):
        if device.id in self.activePhidgets:
            return self.activePhidgets[device.id].actionControlDevice(action)
        else:
            raise Exception("Unexpected device: %s" % device.id)

    def actionControlSensor(self, action, device):
        if device.id in self.activePhidgets:
            return self.activePhidgets[device.id].actionControlSensor(action)
        else:
            raise Exception("Unexpected device: %s" % device.id)

    def deviceStartComm(self, device):
        # Phidget device type (device.deviceTypeId) are defined in devices.xml
        # TODO: Clean this up by refactoring into factory methods for each Phidget type

        try:
            # Common properties for _all_ phidgets
            serialNumber = device.pluginProps.get("serialNumber", None)
            serialNumber = int(serialNumber) if serialNumber else -1

            channel = device.pluginProps.get("channel", None)
            channel = int(channel) if channel else -1

            # isHubPortDevice is true only when non-VINT devices are attached to a VINT hub
            isVintHub = device.pluginProps.get("isVintHub", None)
            isVintHub = bool(isVintHub) if isVintHub else 0
            isVintDevice = device.pluginProps.get("isVintDevice", None)
            isVintDevice = bool(isVintDevice) if isVintDevice else 0
            isHubPortDevice = int(isVintHub and not isVintDevice)

            hubPort = device.pluginProps.get("hubPort", -1)
            hubPort = int(hubPort) if hubPort else -1

            networkPhidgets = self.pluginPrefs.get("networkPhidgets", False)
            enableServerDiscovery = self.pluginPrefs.get("enableServerDiscovery", False)
            serverName = device.pluginProps.get("serverName", None)

            channelInfo = ChannelInfo(
                serialNumber=serialNumber,
                channel=channel,
                isHubPortDevice=isHubPortDevice,
                hubPort=hubPort,
                netInfo=NetInfo(isRemote=networkPhidgets, serverDiscovery=enableServerDiscovery,
                                serverName=serverName)
            )

            # Data interval is used by many types. See if it is set
            dataInterval = device.pluginProps.get("dataInterval", None)
            dataInterval = int(dataInterval) if dataInterval else None
            decimalPlaces = int(device.pluginProps.get("decimalPlaces", 3)) # Sane default 3 decimal places?

            if device.deviceTypeId == "voltageInput" or device.deviceTypeId == "voltageRatioInput":
                # Custom formula fields
                if device.pluginProps.get("useCustomFormula", False):
                    customState = device.pluginProps.get("customState", None)
                    customFormula = device.pluginProps.get("customFormula", None)
                else:
                    customState = None
                    customFormula = None

            # TODO: Use better default sensor types... this might error if not populated
            if device.deviceTypeId == "voltageInput":
                sensorType = int(device.pluginProps.get("voltageSensorType", 0))
                voltageChangeTrigger = float(device.pluginProps.get("voltageChangeTrigger", 0))
                sensorValueChangeTrigger = float(device.pluginProps.get("sensorValueChangeTrigger", 0))
                newPhidget = VoltageInputPhidget(indigo_plugin=self, channelInfo=channelInfo, indigoDevice=device, decimalPlaces=decimalPlaces, logger=self.logger, sensorType=sensorType, dataInterval=dataInterval, voltageChangeTrigger=voltageChangeTrigger, sensorValueChangeTrigger=sensorValueChangeTrigger, customState=customState, customFormula=customFormula)
            elif device.deviceTypeId == "voltageRatioInput":
                voltageRatioChangeTrigger = float(device.pluginProps.get("voltageRatioChangeTrigger", 0))
                sensorValueChangeTrigger = float(device.pluginProps.get("sensorValueChangeTrigger", 0))
                sensorType = int(device.pluginProps.get("voltageRatioSensorType", 0))
                newPhidget = VoltageRatioInputPhidget(indigo_plugin=self, channelInfo=channelInfo, indigoDevice=device, decimalPlaces=decimalPlaces, logger=self.logger, sensorType=sensorType, dataInterval=dataInterval, voltageRatioChangeTrigger=voltageRatioChangeTrigger, sensorValueChangeTrigger=sensorValueChangeTrigger, customState=customState, customFormula=customFormula)
            elif device.deviceTypeId == "digitalOutput":
                newPhidget = DigitalOutputPhidget(indigo_plugin=self, channelInfo=channelInfo, indigoDevice=device, logger=self.logger)
            elif device.deviceTypeId == "digitalInput":
                onStateIcon = str(device.pluginProps.get("onStateIcon", "SensorOn"))
                offStateIcon = str(device.pluginProps.get("offStateIcon", "SensorOff"))
                isAlarm = bool(device.pluginProps.get("isAlarm", False))
                newPhidget = DigitalInputPhidget(indigo_plugin=self, channelInfo=channelInfo, indigoDevice=device, logger=self.logger, isAlarm=isAlarm, onStateIcon=onStateIcon, offStateIcon=offStateIcon)
            elif device.deviceTypeId == "temperatureSensor":
                temperatureChangeTrigger = float(device.pluginProps.get("temperatureChangeTrigger", 0))
                displayTempUnit = device.pluginProps.get("displayTempUnit", "C")
                if device.pluginProps.get("useThermoCouple", False):
                    thermocoupleType = int(device.pluginProps.get("thermocoupleType", None))
                else:
                    thermocoupleType = None
                newPhidget = TemperatureSensorPhidget(indigo_plugin=self, channelInfo=channelInfo, indigoDevice=device, logger=self.logger, decimalPlaces=decimalPlaces, displayTempUnit=displayTempUnit, thermocoupleType=thermocoupleType, dataInterval=dataInterval, temperatureChangeTrigger=temperatureChangeTrigger)
            elif device.deviceTypeId == "frequencyCounter":
                filterType = int(device.pluginProps.get("filterType", 0))
                displayStateName = device.pluginProps.get("displayStateName", None)
                frequencyCutoff = float(device.pluginProps.get("frequencyCutoff", 1))
                isDAQ1400 = bool(device.pluginProps.get("isDAQ1400", False))
                inputType = int(device.pluginProps.get("inputType", 0))
                powerSupply = int(device.pluginProps.get("powerSupply", 0))
                newPhidget = FrequencyCounterPhidget(indigo_plugin=self, channelInfo=channelInfo, indigoDevice=device, logger=self.logger, decimalPlaces=decimalPlaces, filterType=filterType, dataInterval=dataInterval, displayStateName=displayStateName, frequencyCutoff=frequencyCutoff, isDAQ1400=isDAQ1400, inputType=inputType, powerSupply=powerSupply)
            elif device.deviceTypeId == "humiditySensor":
                humidityChangeTrigger = float(device.pluginProps.get("humidityChangeTrigger", 0))
                newPhidget = HumiditySensorPhidget(indigo_plugin=self, channelInfo=channelInfo, indigoDevice=device, logger=self.logger, decimalPlaces=decimalPlaces, humidityChangeTrigger=humidityChangeTrigger, dataInterval=dataInterval)
            else:
                raise Exception("Unexpected device type: %s" % device.deviceTypeId)
            newPhidget.start()
            self.activePhidgets[device.id] = newPhidget
            device.stateListOrDisplayStateIdChanged()
        except PhidgetException as e:
            self.activePhidgets.pop(device.id, None)
            device.setErrorStateOnServer("Unable to start")
            self.logger.error("Unable to start Phidget device='%s' id=%s model=%s: %d: %s\n%s",
                              device.name, device.id, device.deviceTypeId, e.code, e.details,
                              traceback.format_exc())
        except Exception:
            self.activePhidgets.pop(device.id, None)
            device.setErrorStateOnServer("Unable to start")
            self.logger.error("Unable to start Phidget device='%s' id=%s model=%s:\n%s",
                              device.name, device.id, device.deviceTypeId, traceback.format_exc())
        
    # Event and action methods
     ########################################
    def getAttachCapableList(self, filter="", valuesDict=None, typeId="", targetId=0):
        # if self.logLevel > 1:
        #    indigo.server.log(u"Entering getIfKitStandaloneList", type=self.pluginDisplayName)

        myArray = []

        for device in indigo.devices:
            if device.pluginId == 'com.yikes.eric.phidgets-indigo':
            # if self.logLevel > 1: indigo.server.log(u'device list found: %s - %s' % (device.name, device.deviceTypeId), type=self.pluginDisplayName, isError=False)
                myArray.append((device.id, device.name))

        return myArray
    
    # Indigo Triggers

    def triggerStartProcessing(self, trigger):
        # indigo.server.log("triggerStartProcessing: received  trigger:\n%s\n " % (trigger), type=self.pluginDisplayName)

        phDevId = int(trigger.pluginProps["indigoDevice"])
        self.trigger_dict[trigger.id] = {'devid' : phDevId, 'event' : trigger.pluginTypeId}

        # indigo.server.log("triggerStartProcessing: added to trigger_dict:\n%s\n " % (self.trigger_dict), type=self.pluginDisplayName)

    def triggerStopProcessing(self, trigger):
        # indigo.server.log("triggerStopProcessing: entered for trigger %s(%s)" % (trigger.name, trigger.id), type=self.pluginDisplayName)

        if trigger.id in self.trigger_dict:
            # indigo.server.log("triggerStartProcessing: trgger found", type=self.pluginDisplayName)
            del self.trigger_dict[trigger.id]
        # indigo.server.log("triggerStopProcessing: ended processing for trigger %s(%s)" % (trigger.name, trigger.id), type=self.pluginDisplayName)


    def triggerEvent(self, device, event):
        # indigo.server.log(f"trigger event from phidget {device.indigoDevice.id}:{event}")
        for trigger_id, trigger in self.trigger_dict.items():
            if trigger['devid'] == device.indigoDevice.id and trigger['event'] == event:
                # indigo.server.log(f"Sending trigger {trigger_id} ({trigger})")
                indigo.trigger.execute(trigger_id)


    #
    # Methods related to shutdown
    #

    def deviceStopComm(self, device):
        myPhidget = self.activePhidgets.pop(device.id, None)
        if myPhidget is None:
            self.logger.debug("Stop requested for inactive Phidget device='%s' id=%s",
                              device.name, device.id)
            return
        try:
            myPhidget.stop()
        except Exception:
            self.logger.error("Unable to stop Phidget device='%s' id=%s:\n%s",
                              device.name, device.id, traceback.format_exc())

    def shutdown(self):
        with self._outageLock:
            timers = list(self._batchTimers.values())
            self._batchTimers.clear()
            self._detachBatches.clear()
            self._recoveryBatches.clear()
            self._serverOutages.clear()
        for timer in timers:
            timer.cancel()
        if self.networkMonitor is not None:
            try:
                self.networkMonitor.setOnServerAddedHandler(None)
                self.networkMonitor.setOnServerRemovedHandler(None)
            except Exception:
                self.logger.debug("Unable to stop Phidget server monitoring:\n%s",
                                  traceback.format_exc())
            self.networkMonitor = None
        for device_id, phidget in list(self.activePhidgets.items()):
            try:
                phidget.stop()
            except Exception:
                self.logger.warning("Unable to stop active Phidget id=%s during shutdown:\n%s",
                                    device_id, traceback.format_exc())
        self.activePhidgets.clear()
        if self.discoveryInventory is not None:
            try:
                self.discoveryInventory.stop()
            except Exception:
                self.logger.warning("Unable to stop Phidget discovery inventory:\n%s", traceback.format_exc())
            self.discoveryInventory = None
        try:
            Phidget.finalize(0)
        except Exception:
            self.logger.warning("Unable to finalize Phidget library:\n%s", traceback.format_exc())

    def __del__(self):
        indigo.PluginBase.__del__(self)
