# -*- coding: utf-8 -*-

"""Typed parsing helpers shared by Indigo configuration and factories."""

import math
import queue
import re
import threading


STATE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def saved_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def bounded_int(value, minimum=None, maximum=None, choices=None):
    result = int(value)
    if choices is not None and result not in choices:
        raise ValueError
    if minimum is not None and result < minimum:
        raise ValueError
    if maximum is not None and result > maximum:
        raise ValueError
    return result


def bounded_float(value, minimum=None, maximum=None):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError
    if minimum is not None and result < minimum:
        raise ValueError
    if maximum is not None and result > maximum:
        raise ValueError
    return result


def state_id(value):
    result = str(value or "").strip()
    if not STATE_ID_PATTERN.match(result):
        raise ValueError
    return result


def call_with_timeout(callback, timeout=1.0):
    """Run a hardware probe without indefinitely blocking Indigo's UI thread."""
    results = queue.Queue(maxsize=1)

    def invoke():
        try:
            results.put((True, callback()))
        except Exception as error:
            results.put((False, error))

    thread = threading.Thread(target=invoke, name="Phidgets config probe")
    thread.daemon = True
    thread.start()
    try:
        succeeded, result = results.get(timeout=float(timeout))
    except queue.Empty:
        raise TimeoutError("hardware probe timed out after %.1f seconds" % timeout)
    if not succeeded:
        raise result
    return result
