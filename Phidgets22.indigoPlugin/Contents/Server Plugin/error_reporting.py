"""Concise bounded reporting; callers retain retry and lifecycle ownership."""
from collections import OrderedDict
from functools import wraps
import logging
import sys
import threading
import time


_REGISTRY_LOCK = threading.RLock()


def concise_error(error):
    if error is None:
        return 'unknown failure'
    text = ' '.join(str(error).split())
    # SDK details can contain long transport explanations; keep the useful head.
    return text[:600]


class FaultReporter:
    def __init__(self, logger, clock=time.monotonic):
        self.logger = logger
        self.clock = clock
        self.lock = threading.RLock()
        self.faults = OrderedDict()

    def report(self, level, key, message, *arguments):
        now = self.clock()
        with self.lock:
            previous = self.faults.get(key)
            if previous is not None:
                previous['count'] += 1
                interval = 86400 if now - previous['started'] >= 86400 else 3600
                if now - previous['reported'] < interval:
                    return False
                previous['reported'] = now
            else:
                self.faults[key] = dict(started=now, reported=now, count=1)
                if len(self.faults) > 128:
                    self.faults.popitem(last=False)
        clean = tuple(concise_error(arg) if isinstance(arg, (str, Exception)) else arg
                      for arg in arguments)
        getattr(self.logger, level)(message.replace('\n', ' '), *clean)
        return True

    def clear(self, key=None):
        with self.lock:
            if key is None:
                count = len(self.faults)
                self.faults.clear()
                return count
            return int(self.faults.pop(key, None) is not None)


def reporter(owner):
    with _REGISTRY_LOCK:
        result = getattr(owner, '_fault_reporter', None)
        if not isinstance(result, FaultReporter):
            result = owner._fault_reporter = FaultReporter((getattr(owner, "logger", None) or logging.getLogger("Phidgets22")))
        return result


def log_error(owner, message, *args):
    return reporter(owner).report('error', ('error', message, tuple(concise_error(x) for x in args)), message, *args)


def log_warning(owner, message, *args):
    return reporter(owner).report('warning', ('warning', message, tuple(concise_error(x) for x in args)), message, *args)


def clear_faults(owner):
    existing = getattr(owner, "_fault_reporter", None)
    return existing.clear() if isinstance(existing, FaultReporter) else 0


def runtime_boundary(operation, stopped=True):
    """Contain foreign-thread failures; retries belong to the callback itself."""
    def decorate(callback):
        @wraps(callback)
        def guarded(owner, *args, **kwargs):
            if stopped and (getattr(owner, '_state', None) in ('stopping', 'stopped') or
                            getattr(owner, '_stopped', False) is True):
                return None
            try:
                result = callback(owner, *args, **kwargs)
                existing = getattr(owner, '_fault_reporter', None)
                if existing is not None:
                    existing.clear(('boundary', operation))
                return result
            except Exception as error:
                device = getattr(owner, 'indigoDevice', None)
                reporter(owner).report('error', ('boundary', operation),
                    "%s failed: device='%s' id=%s; %s: %s", operation,
                    getattr(device, 'name', 'plugin'), getattr(device, 'id', 'n/a'),
                    type(error).__name__, concise_error(error))
                return None
        return guarded
    return decorate


def set_device_error(owner, message):
    try:
        owner.indigoDevice.setErrorStateOnServer(message)
        return True
    except Exception as error:
        log_error(owner, "Unable to publish device availability: device='%s'; %s",
                  getattr(owner.indigoDevice, 'name', 'unknown'), error)
        return False
