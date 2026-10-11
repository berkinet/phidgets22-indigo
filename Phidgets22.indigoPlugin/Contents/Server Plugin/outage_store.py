"""Outage records kept outside Indigo device configuration."""
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
