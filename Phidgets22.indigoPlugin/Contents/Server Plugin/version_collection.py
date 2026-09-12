# -*- coding: utf-8 -*-

"""Asynchronous, read-only collection of server and device versions."""

import datetime
import os
import re
import threading
import traceback


DEFAULT_INTERVAL_SECONDS = 86400
INITIAL_DELAY_SECONDS = 10
ATTACH_DELAY_SECONDS = 2
FIRMWARE_CATALOG_VERSION = "1.26.20260828"
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "firmware_catalog.txt")
YES_NO_STATES = frozenset((
    "firmwareUpdateAvailable", "firmwareMajorUpdateAvailable"))

_USB_FIRMWARE = re.compile(r"^(.+)v(\d+)\.bin\.rc4$")
_VINT_FIRMWARE = re.compile(
    r"^([^_]+)(?:_[^_]+)?_0x([0-9a-fA-F]+)_v(\d+)\.bin\.obf$")


def _timestamp():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _publish(device, values, logger):
    """Publish independently so one stale state list cannot abort a pass."""
    for key, value in values.items():
        try:
            if key in YES_NO_STATES:
                device.updateStateOnServer(
                    key, value=value, uiValue="Yes" if value else "No")
            else:
                device.updateStateOnServer(key, value=value)
        except Exception:
            logger.debug(
                "Unable to update version state %s for device='%s' id=%s:\n%s",
                key, getattr(device, "name", "unknown"),
                getattr(device, "id", "unknown"), traceback.format_exc())


class FirmwareCatalog(object):
    """Index phidget22admin firmware filenames without loading firmware."""

    def __init__(self, filenames):
        self.usb = {}
        self.vint = {}
        for filename in filenames:
            filename = filename.strip()
            if not filename or filename.startswith("#"):
                continue
            match = _USB_FIRMWARE.match(filename)
            if match:
                self.usb.setdefault(match.group(1), set()).add(
                    int(match.group(2)))
                continue
            match = _VINT_FIRMWARE.match(filename)
            if match:
                key = (match.group(1), int(match.group(2), 16))
                self.vint.setdefault(key, set()).add(int(match.group(3)))

    @classmethod
    def loaded(cls, path):
        with open(path, "r", encoding="utf-8") as catalog:
            return cls(catalog)

    def versions(self, identifier, vint_id=None):
        if vint_id is None:
            return self.usb.get(identifier, set())
        return self.vint.get((identifier, vint_id), set())


class VersionCollector(object):
    """Schedule version reads without blocking Indigo's lifecycle thread."""

    def __init__(self, plugin, logger, timer_factory=threading.Timer,
                 thread_factory=threading.Thread, firmware_catalog=None):
        self.plugin = plugin
        self.logger = logger
        self._timer_factory = timer_factory
        self._thread_factory = thread_factory
        self._lock = threading.RLock()
        self._collection_lock = threading.Lock()
        self._timer = None
        self._generation = 0
        self._stopped = True
        if firmware_catalog is None:
            try:
                firmware_catalog = FirmwareCatalog.loaded(CATALOG_PATH)
            except Exception:
                logger.warning("Unable to load firmware catalog:\n%s",
                               traceback.format_exc())
                firmware_catalog = FirmwareCatalog(())
        self.firmware_catalog = firmware_catalog

    @property
    def interval(self):
        try:
            return max(0, int(self.plugin.pluginPrefs.get(
                "versionCollectionInterval", DEFAULT_INTERVAL_SECONDS)))
        except (TypeError, ValueError):
            return DEFAULT_INTERVAL_SECONDS

    def start(self):
        with self._lock:
            self._stopped = False
        if self.interval:
            self._schedule(INITIAL_DELAY_SECONDS)

    def stop(self):
        with self._lock:
            self._stopped = True
            self._generation += 1
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def request_collection(self, delay=0):
        if not self.interval and delay:
            return
        if delay:
            self._schedule(delay)
        else:
            self._start_worker()

    def _schedule(self, delay):
        with self._lock:
            if self._stopped:
                return
            self._generation += 1
            generation = self._generation
            old_timer = self._timer
            timer = self._timer_factory(delay, self._timer_fired, (generation,))
            timer.daemon = True
            self._timer = timer
        if old_timer is not None:
            old_timer.cancel()
        timer.start()

    def _timer_fired(self, generation):
        with self._lock:
            if self._stopped or generation != self._generation:
                return
            self._timer = None
        self._start_worker()

    def _start_worker(self):
        with self._lock:
            if self._stopped:
                return
        worker = self._thread_factory(
            target=self._collect_and_reschedule,
            name="Phidget version collection")
        worker.daemon = True
        worker.start()

    def _collect_and_reschedule(self):
        if not self._collection_lock.acquire(False):
            return
        try:
            self.collect()
        finally:
            self._collection_lock.release()
        if self.interval:
            self._schedule(self.interval)

    def collect(self):
        checked_at = _timestamp()
        with getattr(self.plugin, "_activePhidgetsLock", self._lock):
            wrappers = list(self.plugin.activePhidgets.values())
        for wrapper in wrappers:
            if getattr(
                    getattr(wrapper, "indigoDevice", None),
                    "deviceTypeId", None) == "networkServer":
                continue
            self._collect_device(wrapper, checked_at)
        with getattr(self.plugin, "_networkServerLock", self._lock):
            monitors = list(self.plugin._networkServerDevices)
        for monitor in monitors:
            self._collect_server(monitor, wrappers, checked_at)

    def _collect_device(self, wrapper, checked_at):
        device = wrapper.indigoDevice
        phidget = getattr(wrapper, "phidget", None)
        getter = getattr(phidget, "getDeviceVersion", None)
        if bool(getattr(
                getattr(wrapper, "channelInfo", None),
                "isHubPortDevice", False)):
            _publish(device, {
                "hasFirmware": False,
                "firmwareVersion": "",
                "firmwareUpgradeable": False,
                "firmwareUpgradeabilityStatus": "Not applicable",
                "latestFirmwareVersion": "",
                "firmwareUpdateAvailable": False,
                "firmwareMajorUpdateAvailable": False,
                "firmwareUpdateStatus": "Not applicable",
                "firmwareCatalogVersion": FIRMWARE_CATALOG_VERSION,
                "firmwareVersionStatus": "No firmware",
                "lastVersionCheck": checked_at,
                "versionCheckError": "",
            }, self.logger)
            return
        if getter is None:
            _publish(device, {
                "hasFirmware": False,
                "firmwareVersion": "",
                "firmwareUpgradeable": False,
                "firmwareUpgradeabilityStatus": "Not supported",
                "latestFirmwareVersion": "",
                "firmwareUpdateAvailable": False,
                "firmwareMajorUpdateAvailable": False,
                "firmwareUpdateStatus": "Not applicable",
                "firmwareCatalogVersion": FIRMWARE_CATALOG_VERSION,
                "firmwareVersionStatus": "No firmware",
                "lastVersionCheck": checked_at,
                "versionCheckError": "",
            }, self.logger)
            return
        if getattr(wrapper, "_state", None) != "attached":
            _publish(device, {
                "firmwareVersionStatus": "Unavailable",
                "firmwareCatalogVersion": FIRMWARE_CATALOG_VERSION,
                "lastVersionCheck": checked_at,
                "versionCheckError": "Device is not attached",
            }, self.logger)
            return
        try:
            version = int(getter())
            has_firmware = version > 0
            upgradeable = False
            upgradeability_status = "Not supported"
            upgradeability_error = ""
            latest_version = 0
            update_available = False
            major_update_available = False
            update_status = "Not applicable"
            if has_firmware:
                upgrade_identifier = getattr(
                    phidget, "_getDeviceFirmwareUpgradeString", None)
                if upgrade_identifier is not None:
                    try:
                        identifier = str(upgrade_identifier() or "").strip()
                        if not identifier:
                            update_status = "Not supported"
                            versions = set()
                        else:
                            vint_id = None
                            channel_info = getattr(wrapper, "channelInfo", None)
                            if int(getattr(channel_info, "hubPort", -1)) >= 0:
                                vint_getter = getattr(
                                    phidget, "_getDeviceVINTID", None)
                                if vint_getter is not None:
                                    vint_id = int(vint_getter())
                            versions = self.firmware_catalog.versions(
                                identifier, vint_id)
                        latest_version = max(versions) if versions else 0
                        upgradeable = bool(versions)
                        if identifier:
                            upgradeability_status = (
                                "Supported" if upgradeable else
                                "No compatible firmware in catalog")
                        update_available = latest_version > version
                        major_update_available = (
                            update_available and
                            latest_version // 100 != version // 100)
                        if major_update_available:
                            update_status = "Major update available"
                        elif update_available:
                            update_status = "Update available"
                        elif upgradeable:
                            update_status = "Up to date"
                        elif identifier:
                            update_status = "No compatible firmware"
                    except Exception as error:
                        upgradeability_status = "Unknown"
                        update_status = "Unknown"
                        upgradeability_error = str(error)
            _publish(device, {
                "hasFirmware": has_firmware,
                "firmwareVersion": str(version) if has_firmware else "",
                "firmwareUpgradeable": upgradeable,
                "firmwareUpgradeabilityStatus": upgradeability_status,
                "latestFirmwareVersion": (
                    str(latest_version) if latest_version else ""),
                "firmwareUpdateAvailable": update_available,
                "firmwareMajorUpdateAvailable": major_update_available,
                "firmwareUpdateStatus": update_status,
                "firmwareCatalogVersion": FIRMWARE_CATALOG_VERSION,
                "firmwareVersionStatus": (
                    "Collected" if has_firmware else "No firmware"),
                "lastVersionCheck": checked_at,
                "versionCheckError": upgradeability_error,
            }, self.logger)
        except Exception as error:
            _publish(device, {
                "firmwareVersionStatus": "Check failed",
                "firmwareCatalogVersion": FIRMWARE_CATALOG_VERSION,
                "lastVersionCheck": checked_at,
                "versionCheckError": str(error),
            }, self.logger)

    @staticmethod
    def _server_matches(monitor, wrapper):
        if not bool(getattr(
                getattr(wrapper, "channelInfo", None), "netInfo", None) and
                wrapper.channelInfo.netInfo.isRemote):
            return False
        names = {
            str(getattr(wrapper, name, "") or "").strip()
            for name in ("runtimeServerName", "runtimeServerUniqueName",
                         "runtimeServerHostname")
        }
        configured = str(getattr(
            wrapper.channelInfo.netInfo, "serverName", "") or "").strip()
        names.add(configured)
        return monitor.serverName in names

    def _collect_server(self, monitor, wrappers, checked_at):
        candidates = [wrapper for wrapper in wrappers
                      if self._server_matches(monitor, wrapper) and
                      getattr(wrapper, "_state", None) == "attached"]
        for wrapper in candidates:
            getter = getattr(getattr(wrapper, "phidget", None),
                             "_getServerVersion", None)
            if getter is None:
                continue
            try:
                major, minor = getter()
                _publish(monitor.indigoDevice, {
                    "serverVersion": "%d.%d" % (major, minor),
                    "serverVersionStatus": "Collected",
                    "lastVersionCheck": checked_at,
                    "versionCheckError": "",
                }, self.logger)
                return
            except Exception as error:
                _publish(monitor.indigoDevice, {
                    "serverVersionStatus": "Check failed",
                    "lastVersionCheck": checked_at,
                    "versionCheckError": str(error),
                }, self.logger)
                return
        _publish(monitor.indigoDevice, {
            "serverVersion": "",
            "serverVersionStatus": "Unavailable",
            "lastVersionCheck": checked_at,
            "versionCheckError": "No attached plugin device on this server",
        }, self.logger)
