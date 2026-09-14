# -*- coding: utf-8 -*-

"""Asynchronous, read-only collection of server and device versions."""

import datetime
import io
import json
import os
import re
import tarfile
import threading
import traceback
from urllib.request import Request, urlopen

import indigo

from connection_identity import ServerIdentity
from state_publisher import update_indigo_states
from runtime_registry import registry_for


DEFAULT_INTERVAL_SECONDS = 86400
INITIAL_DELAY_SECONDS = 10
ATTACH_DELAY_SECONDS = 2
FIRMWARE_CATALOG_VERSION = "1.26.20260828"
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "firmware_catalog.txt")
CACHE_FILENAME = "Phidgets 22 Firmware Catalog.json"
ADMIN_ARCHIVE_INDEX = "https://www.phidgets.com/downloads/phidget22/tools/linux/phidget22admin/"
ADMIN_ARCHIVE_NAME = re.compile(r"phidget22admin-(\d+\.\d+\.\d{8})\.tar\.gz")
MAX_INDEX_BYTES = 256 * 1024
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
YES_NO_STATES = frozenset((
    "firmwareUpdateAvailable", "firmwareMajorUpdateAvailable"))
UPDATE_VARIABLE_NAME = "Phidgets22_FirmwareUpdatesAvailable"

_USB_FIRMWARE = re.compile(r"^(.+)v(\d+)\.bin\.rc4$")
_VINT_FIRMWARE = re.compile(
    r"^([^_]+)(?:_[^_]+)?_0x([0-9a-fA-F]+)_v(\d+)\.bin\.obf$")


def _timestamp():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _publish(owner, values, logger):
    update_indigo_states(
        owner, values, logger,
        ui_values={key: lambda value: "Yes" if value else "No"
                   for key in YES_NO_STATES})


class FirmwareCatalog(object):
    """Index phidget22admin firmware filenames without loading firmware."""

    def __init__(self, filenames):
        self.usb = {}
        self.vint = {}
        self.filenames = []
        for filename in filenames:
            filename = filename.strip()
            if not filename or filename.startswith("#"):
                continue
            match = _USB_FIRMWARE.match(filename)
            if match:
                self.filenames.append(filename)
                self.usb.setdefault(match.group(1), set()).add(
                    int(match.group(2)))
                continue
            match = _VINT_FIRMWARE.match(filename)
            if match:
                self.filenames.append(filename)
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


def _read_bounded(response, limit):
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("Phidgets catalog response exceeds %s bytes" % limit)
    return payload


def fetch_firmware_catalog(current_version=FIRMWARE_CATALOG_VERSION, opener=urlopen):
    """Read firmware filenames from the latest official admin source archive."""
    request = Request(ADMIN_ARCHIVE_INDEX,
                      headers={"User-Agent": "Phidgets-Indigo-Firmware-Catalog/1"})
    with opener(request, timeout=5) as response:
        listing = _read_bounded(response, MAX_INDEX_BYTES).decode("utf-8")
    versions = ADMIN_ARCHIVE_NAME.findall(listing)
    if not versions:
        raise ValueError("No phidget22admin archive found in Phidgets index")
    version = max(versions, key=lambda value: tuple(map(int, value.split("."))))
    if tuple(map(int, version.split("."))) <= tuple(
            map(int, current_version.split("."))):
        return None
    archive_url = ADMIN_ARCHIVE_INDEX + "phidget22admin-%s.tar.gz" % version
    with opener(Request(archive_url, headers={
            "User-Agent": "Phidgets-Indigo-Firmware-Catalog/1"}),
            timeout=10) as response:
        payload = _read_bounded(response, MAX_ARCHIVE_BYTES)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        filenames = [os.path.basename(member.name) for member in archive
                     if member.isfile() and "/firmware/" in member.name]
    catalog = FirmwareCatalog(filenames)
    if not catalog.usb and not catalog.vint:
        raise ValueError("Phidgets admin archive has no recognized firmware")
    return version, catalog


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
        self._test_override = None
        self._remote_catalog_enabled = firmware_catalog is None
        self.catalog_version = FIRMWARE_CATALOG_VERSION
        if firmware_catalog is None:
            try:
                firmware_catalog = FirmwareCatalog.loaded(CATALOG_PATH)
            except Exception:
                logger.warning("Unable to load firmware catalog:\n%s",
                               traceback.format_exc())
                firmware_catalog = FirmwareCatalog(())
        self.firmware_catalog = firmware_catalog
        if self._remote_catalog_enabled:
            self._load_cached_catalog()

    def _cache_path(self):
        log_path = getattr(getattr(self.plugin, "plugin_file_handler", None),
                           "baseFilename", "")
        return (os.path.join(os.path.dirname(log_path), CACHE_FILENAME)
                if log_path else None)

    def _load_cached_catalog(self):
        path = self._cache_path()
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as cached:
                data = json.load(cached)
            version = data["version"]
            if not isinstance(version, str) or not re.fullmatch(
                    r"\d+\.\d+\.\d{8}", version):
                raise ValueError("Invalid cached catalog version")
            catalog = FirmwareCatalog(data["filenames"])
            if not catalog.usb and not catalog.vint:
                raise ValueError("Cached catalog has no firmware entries")
            if tuple(map(int, version.split("."))) > tuple(
                    map(int, self.catalog_version.split("."))):
                self.firmware_catalog = catalog
                self.catalog_version = version
        except Exception as error:
            self.logger.warning("Unable to load cached firmware catalog: %s", error)

    def _save_cached_catalog(self):
        path = self._cache_path()
        if not path:
            return
        temporary_path = path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as output:
                json.dump({"version": self.catalog_version,
                           "filenames": self.firmware_catalog.filenames}, output)
            os.replace(temporary_path, path)
        except Exception as error:
            self.logger.warning("Unable to cache firmware catalog: %s", error)

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
            self._test_override = None
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
        except Exception:
            self.logger.error("Version collection failed; next check remains scheduled:\n%s",
                              traceback.format_exc())
        finally:
            self._collection_lock.release()
            if self.interval:
                self._schedule(self.interval)

    def _refresh_catalog(self):
        if not self._remote_catalog_enabled:
            return
        try:
            refreshed = fetch_firmware_catalog(self.catalog_version)
            if refreshed is not None:
                version, catalog = refreshed
                self.firmware_catalog = catalog
                self.catalog_version = version
                self._save_cached_catalog()
                self.logger.info("Firmware catalog refreshed from Phidgets admin %s",
                                 version)
        except Exception as error:
            self.logger.warning("Unable to refresh Phidgets firmware catalog; "
                                "using %s: %s", self.catalog_version, error)

    def collect(self):
        self._refresh_catalog()
        checked_at = _timestamp()
        registry = registry_for(self.plugin)
        wrappers = registry.snapshot()
        for wrapper in wrappers:
            if getattr(
                    getattr(wrapper, "indigoDevice", None),
                    "deviceTypeId", None) == "networkServer":
                continue
            self._collect_device(wrapper, checked_at)
        monitors = registry.network_servers_snapshot()
        for monitor in monitors:
            self._collect_server(monitor, wrappers, checked_at)
        self._publish_update_list(wrappers)

    def set_test_override(self, device_id, reported_version):
        """Temporarily substitute one older reported installed version."""
        device_id = int(device_id)
        runtime = registry_for(self.plugin).get(device_id)
        if runtime is None or getattr(runtime, "_state", None) != "attached":
            raise ValueError("Selected Indigo Phidget device is not attached")
        device = runtime.indigoDevice
        if (device.pluginId != self.plugin.pluginId or
                device.deviceTypeId == "networkServer" or
                getattr(runtime.channelInfo, "isHubPortDevice", False)):
            raise ValueError("Selected device has no independent firmware")
        phidget = runtime.phidget
        real_version = int(phidget.getDeviceVersion())
        identifier = str(phidget._getDeviceFirmwareUpgradeString() or "").strip()
        if not identifier:
            raise ValueError("Device has no firmware upgrade identifier")
        vint_id = None
        if int(getattr(runtime.channelInfo, "hubPort", -1)) >= 0:
            vint_getter = getattr(phidget, "_getDeviceVINTID", None)
            if vint_getter is not None:
                vint_id = int(vint_getter())
        versions = self.firmware_catalog.versions(identifier, vint_id)
        reported_version = int(reported_version)
        latest_version = max(versions) if versions else 0
        if (reported_version <= 0 or
                reported_version >= real_version or
                latest_version <= reported_version or
                latest_version > real_version):
            raise ValueError(
                "Choose a positive test version below both installed "
                "firmware %s and latest catalog version %s; this device "
                "must currently be up to date" %
                (real_version, latest_version))
        with self._collection_lock:
            with self._lock:
                self._test_override = (device_id, reported_version)
        self.logger.warning(
            "TEST ONLY: reporting firmware %s instead of SDK version %s "
            "for device='%s' id=%s until test override is cleared",
            reported_version, real_version, device.name, device_id)
        self.request_collection()

    def clear_test_override(self, device_id):
        with self._collection_lock:
            with self._lock:
                if self._test_override is None:
                    return False
                if self._test_override[0] != int(device_id):
                    raise ValueError("Test override belongs to Indigo device %s" %
                                     self._test_override[0])
                self._test_override = None
        self.logger.info("Firmware version test override cleared for id=%s",
                         device_id)
        self.request_collection()
        return True

    def _test_version_for(self, device_id):
        with self._lock:
            override = self._test_override
        return override[1] if override is not None and override[0] == device_id else None

    def _publish_update_list(self, wrappers):
        """Keep one user-facing variable synchronized after the entire pass."""
        try:
            devices = indigo.devices
        except AttributeError:
            devices = [wrapper.indigoDevice for wrapper in wrappers]
        eligible = []
        for device in devices:
            if (getattr(device, "pluginId", None) != self.plugin.pluginId or
                    not getattr(device, "enabled", True) or
                    getattr(device, "deviceTypeId", None) == "networkServer"):
                continue
            states = getattr(device, "states", {})
            if states.get("firmwareUpdateAvailable") is True:
                eligible.append(device)
        eligible.sort(key=lambda device: (device.name.lower(), device.id))
        lines = ["%s (Indigo ID %s): firmware %s; latest %s%s" % (
            device.name, device.id,
            device.states.get("firmwareVersion", "unknown"),
            device.states.get("latestFirmwareVersion", "unknown"),
            ("; major update" if device.states.get(
                "firmwareMajorUpdateAvailable") else "") +
            (" [TEST OVERRIDE]" if self._test_version_for(device.id)
             is not None else ""))
            for device in eligible]
        value = "\n".join(lines)
        try:
            variable = (indigo.variables[UPDATE_VARIABLE_NAME]
                        if UPDATE_VARIABLE_NAME in indigo.variables else None)
            if variable is None:
                indigo.variable.create(UPDATE_VARIABLE_NAME, value=value)
                changed = bool(value)
            else:
                changed = str(variable.value) != value
                if changed:
                    indigo.variable.updateValue(variable.id, value=value)
        except Exception as error:
            self.logger.warning(
                "Unable to publish firmware update variable %s: %s",
                UPDATE_VARIABLE_NAME, error)
            return
        if changed and value:
            coordinator = getattr(self.plugin, "eventCoordinator", None)
            if coordinator is not None:
                coordinator.trigger_global_event("firmwareUpdateAvailable")

    def _collect_device(self, wrapper, checked_at):
        device = wrapper.indigoDevice
        previous_update = device.states.get("firmwareUpdateAvailable") is True
        phidget = getattr(wrapper, "phidget", None)
        getter = getattr(phidget, "getDeviceVersion", None)
        if bool(getattr(
                getattr(wrapper, "channelInfo", None),
                "isHubPortDevice", False)):
            _publish(wrapper, {
                "hasFirmware": False,
                "firmwareVersion": "",
                "firmwareUpgradeable": False,
                "firmwareUpgradeabilityStatus": "Not applicable",
                "latestFirmwareVersion": "",
                "firmwareUpdateAvailable": False,
                "firmwareMajorUpdateAvailable": False,
                "firmwareUpdateStatus": "Not applicable",
                "firmwareCatalogVersion": self.catalog_version,
                "firmwareVersionStatus": "No firmware",
                "lastVersionCheck": checked_at,
                "versionCheckError": "",
            }, self.logger)
            return
        if getter is None:
            _publish(wrapper, {
                "hasFirmware": False,
                "firmwareVersion": "",
                "firmwareUpgradeable": False,
                "firmwareUpgradeabilityStatus": "Not supported",
                "latestFirmwareVersion": "",
                "firmwareUpdateAvailable": False,
                "firmwareMajorUpdateAvailable": False,
                "firmwareUpdateStatus": "Not applicable",
                "firmwareCatalogVersion": self.catalog_version,
                "firmwareVersionStatus": "No firmware",
                "lastVersionCheck": checked_at,
                "versionCheckError": "",
            }, self.logger)
            return
        if getattr(wrapper, "_state", None) != "attached":
            _publish(wrapper, {
                "firmwareVersionStatus": "Unavailable",
                "firmwareCatalogVersion": self.catalog_version,
                "lastVersionCheck": checked_at,
                "versionCheckError": "Device is not attached",
            }, self.logger)
            return
        try:
            real_version = int(getter())
            test_version = self._test_version_for(device.id)
            version = test_version if test_version is not None else real_version
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
            _publish(wrapper, {
                "hasFirmware": has_firmware,
                "firmwareVersion": str(version) if has_firmware else "",
                "firmwareUpgradeable": upgradeable,
                "firmwareUpgradeabilityStatus": upgradeability_status,
                "latestFirmwareVersion": (
                    str(latest_version) if latest_version else ""),
                "firmwareUpdateAvailable": update_available,
                "firmwareMajorUpdateAvailable": major_update_available,
                "firmwareUpdateStatus": update_status,
                "firmwareCatalogVersion": self.catalog_version,
                "firmwareVersionStatus": (
                    "Collected" if has_firmware else "No firmware"),
                "lastVersionCheck": checked_at,
                "versionCheckError": upgradeability_error,
            }, self.logger)
            if (update_available and not previous_update and
                    device.states.get("firmwareUpdateAvailable") is True):
                self.logger.warning(
                    "%sPhidget firmware update available: device='%s' id=%s "
                    "installed=%s latest=%s%s",
                    "TEST ONLY: " if test_version is not None else "",
                    device.name, device.id,
                    version, latest_version,
                    " (major update)" if major_update_available else "")
        except Exception as error:
            _publish(wrapper, {
                "firmwareVersionStatus": "Check failed",
                "firmwareCatalogVersion": self.catalog_version,
                "lastVersionCheck": checked_at,
                "versionCheckError": str(error),
            }, self.logger)

    @staticmethod
    def _server_matches(monitor, wrapper):
        return ServerIdentity.from_wrapper(wrapper).matches(monitor.serverName)

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
                _publish(monitor, {
                    "serverVersion": "%d.%d" % (major, minor),
                    "serverVersionStatus": "Collected",
                    "lastVersionCheck": checked_at,
                    "versionCheckError": "",
                }, self.logger)
                return
            except Exception as error:
                _publish(monitor, {
                    "serverVersionStatus": "Check failed",
                    "lastVersionCheck": checked_at,
                    "versionCheckError": str(error),
                }, self.logger)
                return
        _publish(monitor, {
            "serverVersion": "",
            "serverVersionStatus": "Unavailable",
            "lastVersionCheck": checked_at,
            "versionCheckError": "No attached plugin device on this server",
        }, self.logger)
