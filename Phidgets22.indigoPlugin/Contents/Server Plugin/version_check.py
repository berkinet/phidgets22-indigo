# -*- coding: utf-8 -*-
"""Non-blocking Phidget22 native-library version checking."""

import calendar
import json
import re
import threading
from urllib.request import Request, urlopen


PHIDGETS_PYPI_URL = "https://pypi.org/pypi/phidget22/json"
PHIDGETS_PYTHON_INFO_URL = "https://www.phidgets.com/docs/Language_-_Python"
PHIDGETS_UPDATE_COMMAND = ('"/Library/Frameworks/Python.framework/Versions/3.13/bin/'
                           'python3.13" -m pip install --upgrade phidget22')
DEFAULT_TIMEOUT_SECONDS = 5

_INSTALLED_PATTERN = re.compile(
    r"Version\s+(\d+(?:\.\d+)*)(?:\s+-\s+Built\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{4}))?",
    re.IGNORECASE)


def _version_tuple(version):
    return tuple(int(part) for part in version.split("."))


def parse_installed_version(library_version):
    """Return a comparable dotted version from Phidget.getLibraryVersion()."""
    match = _INSTALLED_PATTERN.search(library_version or "")
    if match is None:
        raise ValueError("Unrecognized installed Phidget22 version: %r" % library_version)

    version = match.group(1)
    if match.group(2) and len(version.split(".")) < 3:
        month = list(calendar.month_abbr).index(match.group(2).title())
        build_date = "%04d%02d%02d" % (int(match.group(4)), month, int(match.group(3)))
        version = "%s.%s" % (version, build_date)
    return version


def parse_latest_package_version(payload):
    """Return the current official Phidget22 package version from PyPI JSON."""
    version = json.loads(payload)["info"]["version"]
    _version_tuple(version)
    return version


def fetch_latest_package_version(timeout=DEFAULT_TIMEOUT_SECONDS, opener=urlopen):
    request = Request(PHIDGETS_PYPI_URL,
                      headers={"User-Agent": "Phidgets-Indigo-Version-Check/1"})
    response = opener(request, timeout=timeout)
    try:
        payload = response.read().decode("utf-8", errors="replace")
    finally:
        response.close()
    return parse_latest_package_version(payload)


def check_and_log(library_version, logger, timeout=DEFAULT_TIMEOUT_SECONDS, opener=urlopen):
    """Check once and log exactly one user-facing result."""
    try:
        installed = parse_installed_version(library_version)
        current = fetch_latest_package_version(timeout=timeout, opener=opener)
        if _version_tuple(installed) < _version_tuple(current):
            logger.warning(
                "Installed Phidget22 version is %s; newer version %s is available. "
                "To update it, run: %s. For more information, see: %s",
                installed, current, PHIDGETS_UPDATE_COMMAND, PHIDGETS_PYTHON_INFO_URL)
        else:
            logger.info(
                "Installed Phidget22 version is %s and is up to date. "
                "For more information, see: %s",
                installed, PHIDGETS_PYTHON_INFO_URL)
    except Exception as error:
        logger.info(
            "Installed Phidget22 version is %s; unable to reach Phidgets or determine "
            "the current package version (%s). For more information, see: %s",
            library_version, error, PHIDGETS_PYTHON_INFO_URL)


def start_version_check(library_version, logger, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Run the online check without delaying Indigo plugin startup."""
    thread = threading.Thread(
        target=check_and_log,
        args=(library_version, logger, timeout),
        name="Phidget22 version check")
    thread.daemon = True
    thread.start()
    return thread
