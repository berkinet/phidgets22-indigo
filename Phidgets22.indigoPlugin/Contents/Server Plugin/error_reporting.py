"""Concise bounded reporting; callers retain retry and lifecycle ownership."""
from collections import OrderedDict
from functools import wraps
import inspect
import logging
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
    def __init__(self, logger, clock=time.monotonic, interval=3600):
        self.logger = logger
        self.clock = clock
        self.interval = max(1, int(interval))
        self.lock = threading.RLock()
        self.faults = OrderedDict()

    def report(self, level, key, message, *arguments):
        now = self.clock()
        with self.lock:
            previous = self.faults.get(key)
            if previous is not None:
                previous['count'] += 1
                interval = max(86400, self.interval) if now - previous['started'] >= 86400 else self.interval
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
            preferences = getattr(getattr(owner, 'indigo_plugin', None), 'pluginPrefs', {})
            try:
                interval = int(preferences.get('detachedReminderInterval', 3600))
                interval = interval if interval > 0 else 3600
            except (TypeError, ValueError, OverflowError):
                interval = 3600
            result = owner._fault_reporter = FaultReporter(
                getattr(owner, "logger", None) or logging.getLogger("Phidgets22"), interval=interval)
        return result


def log_error(owner, message, *args):
    return reporter(owner).report('error', ('error', message, tuple(concise_error(x) for x in args)), message, *args)


def log_warning(owner, message, *args):
    return reporter(owner).report('warning', ('warning', message, tuple(concise_error(x) for x in args)), message, *args)


def clear_faults(owner, prefix=None):
    existing = getattr(owner, "_fault_reporter", None)
    if not isinstance(existing, FaultReporter):
        return 0
    if prefix is None:
        return existing.clear()
    with existing.lock:
        keys = [key for key in existing.faults
                if isinstance(key, tuple) and len(key) > 1 and str(key[1]).startswith(prefix)]
        return sum(existing.clear(key) for key in keys)



def _preserve_signature(callback, guarded):
    """Keep actual argument counts/defaults for Indigo's callback dispatcher.

    This compiles only parameter names declared in trusted plugin source;
    default objects are passed through a private namespace, never rendered
    or evaluated as source text. No user configuration is executed.
    """
    signature = inspect.signature(callback)
    declarations, forwarded = [], []
    namespace = {'_guarded_callback': guarded}
    positional_only = 0
    has_varargs = False
    for index, parameter in enumerate(signature.parameters.values()):
        name = parameter.name
        kind = parameter.kind
        if kind is inspect.Parameter.VAR_POSITIONAL:
            declarations.append('*' + name)
            forwarded.append('*' + name)
            has_varargs = True
            continue
        if kind is inspect.Parameter.VAR_KEYWORD:
            declarations.append('**' + name)
            forwarded.append('**' + name)
            continue
        if kind is inspect.Parameter.KEYWORD_ONLY and not has_varargs:
            declarations.append('*')
            has_varargs = True
        declaration = name
        if parameter.default is not inspect.Parameter.empty:
            reference = '_default_%d' % index
            namespace[reference] = parameter.default
            declaration += '=' + reference
        declarations.append(declaration)
        forwarded.append(name + '=' + name if kind is inspect.Parameter.KEYWORD_ONLY else name)
        if kind is inspect.Parameter.POSITIONAL_ONLY:
            positional_only += 1
    if positional_only:
        declarations.insert(positional_only, '/')
    source = 'def _callback(%s):\n    return _guarded_callback(%s)\n' % (
        ', '.join(declarations), ', '.join(forwarded))
    exec(compile(source, '<Phidgets callback signature>', 'exec'), namespace)
    result = wraps(callback)(namespace['_callback'])
    result.__signature__ = signature
    return result

def runtime_boundary(operation, stopped=True):
    """Contain foreign-thread failures; retries belong to the callback itself."""
    def decorate(callback):
        @wraps(callback)
        def guarded(owner, *args, **kwargs):
            if stopped and (getattr(owner, '_state', None) in ('stopping', 'stopped') or
                            getattr(owner, '_stopped', False) is True or
                            getattr(getattr(owner, 'indigo_plugin', None), '_shutting_down', False) is True):
                return None
            try:
                result = callback(owner, *args, **kwargs)
                existing = getattr(owner, '_fault_reporter', None)
                if isinstance(existing, FaultReporter) and result is not None and result is not False:
                    existing.clear(('boundary', operation))
                return result
            except Exception as error:
                device = getattr(owner, 'indigoDevice', None)
                reporter(owner).report('error', ('boundary', operation),
                    "%s failed: device='%s' id=%s; %s: %s", operation,
                    getattr(device, 'name', 'plugin'), getattr(device, 'id', 'n/a'),
                    type(error).__name__, concise_error(error))
                return None
        return _preserve_signature(callback, guarded)
    return decorate


def set_device_error(owner, message):
    try:
        owner.indigoDevice.setErrorStateOnServer(message)
        owner._reported_availability_error = message
        return True
    except Exception as error:
        log_error(owner, "Unable to publish device availability: device='%s'; %s",
                  getattr(owner.indigoDevice, 'name', 'unknown'), error)
        return False


def validation_boundary(operation):
    def decorate(callback):
        @wraps(callback)
        def validate(owner, values, *args, **kwargs):
            try:
                return callback(owner, values, *args, **kwargs)
            except Exception as error:
                import indigo
                errors = getattr(indigo, 'Dict', dict)()
                errors['showAlertText'] = "Invalid configuration: %s" % concise_error(error)
                log_error(owner, "%s failed: %s", operation, error)
                return False, values, errors
        return _preserve_signature(callback, validate)
    return decorate
