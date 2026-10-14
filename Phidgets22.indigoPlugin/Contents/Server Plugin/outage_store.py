"""Outage records kept outside Indigo device configuration."""
import math
import time
from error_reporting import log_error
import json
import os
import threading


class OutageStore:
    def __init__(self, directory):
        self.directory = directory
        self.lock = threading.RLock()

    def _path(self, device_id):
        return os.path.join(self.directory, 'phidgets-outage-%d.json' % int(device_id))

    def load(self, device_id):
        with self.lock:
            path = self._path(device_id)
            if not os.path.exists(path):
                return None
            with open(path, encoding='utf-8') as saved:
                return json.load(saved)

    def save(self, device_id, record):
        with self.lock:
            path = self._path(device_id)
            if record is None:
                if os.path.exists(path):
                    os.remove(path)
                return
            temporary = path + '.tmp'
            try:
                with open(temporary, 'w', encoding='utf-8') as saved:
                    json.dump(record, saved, allow_nan=False)
                    saved.flush()
                    os.fsync(saved.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)

    def prune(self, valid_device_ids):
        valid = {int(value) for value in valid_device_ids}
        with self.lock:
            for name in os.listdir(self.directory):
                if not (name.startswith('phidgets-outage-') and name.endswith('.json')):
                    continue
                identifier = name[len('phidgets-outage-'):-5]
                if identifier.isdigit() and int(identifier) not in valid:
                    os.remove(os.path.join(self.directory, name))


class OutagePersistence:
    """Shared wall-clock records with monotonic runtime elapsed time."""
    def _restore_outage(self):
        self._restored_reminder_due = None
        store = getattr(self.indigo_plugin, "outageStore", None)
        if store is None:
            return
        try:
            record = store.load(self.indigoDevice.id)
            if record is None:
                return
            if record["address"] != self._outage_address():
                return
            now = time.time()
            started, due = float(record["started"]), float(record["due"])
            if not (math.isfinite(started) and math.isfinite(due) and
                    0 < started <= now and started <= due):
                raise ValueError("invalid outage timestamps")
            self._detached_at = time.monotonic() - (now - started)
            self._restored_reminder_due = due
            self._daily_reminder_reported = record.get("daily") is True
        except Exception as error:
            self.logger.warning("Ignoring invalid saved outage for %s: %s",
                                self._error_identity(), str(error).replace("\n", " "))

    def _persist_outage(self, delay=None):
        store = getattr(self.indigo_plugin, "outageStore", None)
        if store is None:
            return
        try:
            record = None
            if self._detached_at is not None:
                now = time.time()
                elapsed = max(0, time.monotonic() - self._detached_at)
                record = {
                    "address": self._outage_address(), "started": now - elapsed,
                    "due": now + (delay if delay is not None else
                                  self.initial_connection_timeout),
                    "daily": self._daily_reminder_reported}
            store.save(self.indigoDevice.id, record)
        except Exception as error:
            log_error(self, "Unable to save outage for %s: %s",
                              self._error_identity(), str(error).replace("\n", " "))
