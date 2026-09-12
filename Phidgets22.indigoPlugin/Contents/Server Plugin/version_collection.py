# -*- coding: utf-8 -*-

"""Asynchronous, read-only collection of server and device versions."""

import datetime
import threading
import traceback


DEFAULT_INTERVAL_SECONDS = 86400
INITIAL_DELAY_SECONDS = 10
ATTACH_DELAY_SECONDS = 2


def _timestamp():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _publish(device, values, logger):
    """Publish independently so one stale state list cannot abort a pass."""
    for key, value in values.items():
        try:
            device.updateStateOnServer(key, value=value)
        except Exception:
            logger.debug(
                "Unable to update version state %s for device='%s' id=%s:\n%s",
                key, getattr(device, "name", "unknown"),
                getattr(device, "id", "unknown"), traceback.format_exc())


class VersionCollector(object):
    """Schedule version reads without blocking Indigo's lifecycle thread."""

    def __init__(self, plugin, logger, timer_factory=threading.Timer,
                 thread_factory=threading.Thread):
        self.plugin = plugin
        self.logger = logger
        self._timer_factory = timer_factory
        self._thread_factory = thread_factory
        self._lock = threading.RLock()
        self._collection_lock = threading.Lock()
        self._timer = None
        self._generation = 0
        self._stopped = True

    @property
    def interval(self):
        try:
            return max(0, int(self.plugin.pluginPrefs.get(
                "versionCollectionInterval", DEFAULT_INTERVAL_SECONDS)))
        except (TypeError, ValueError):
            return DEFAULT_INTERVAL_SECONDS

    def migrate_state_lists(self):
        for device in list(getattr(__import__("indigo"), "devices", ())):
            if getattr(device, "pluginId", None) != self.plugin.pluginId:
                continue
            try:
                device.stateListOrDisplayStateIdChanged()
            except Exception:
                self.logger.warning(
                    "Unable to refresh version states for device='%s' id=%s:\n%s",
                    getattr(device, "name", "unknown"),
                    getattr(device, "id", "unknown"), traceback.format_exc())

    def start(self):
        with self._lock:
            self._stopped = False
        self.migrate_state_lists()
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
        if getter is None:
            _publish(device, {
                "hasFirmware": False,
                "firmwareVersion": "",
                "firmwareUpgradeable": False,
                "firmwareUpgradeabilityStatus": "Not supported",
                "firmwareVersionStatus": "No firmware",
                "lastVersionCheck": checked_at,
                "versionCheckError": "",
            }, self.logger)
            return
        if getattr(wrapper, "_state", None) != "attached":
            _publish(device, {
                "firmwareVersionStatus": "Unavailable",
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
            if has_firmware:
                upgrade_identifier = getattr(
                    phidget, "_getDeviceFirmwareUpgradeString", None)
                if upgrade_identifier is not None:
                    try:
                        upgradeable = bool(str(
                            upgrade_identifier() or "").strip())
                        upgradeability_status = (
                            "Supported" if upgradeable else "Not supported")
                    except Exception as error:
                        upgradeability_status = "Unknown"
                        upgradeability_error = str(error)
            _publish(device, {
                "hasFirmware": has_firmware,
                "firmwareVersion": str(version) if has_firmware else "",
                "firmwareUpgradeable": upgradeable,
                "firmwareUpgradeabilityStatus": upgradeability_status,
                "firmwareVersionStatus": (
                    "Collected" if has_firmware else "No firmware"),
                "lastVersionCheck": checked_at,
                "versionCheckError": upgradeability_error,
            }, self.logger)
        except Exception as error:
            _publish(device, {
                "firmwareVersionStatus": "Check failed",
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
