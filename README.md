# Phidgets 22 for Indigo

<img src="https://raw.githubusercontent.com/berkinet/phidgets22-indigo/main/Phidgets22.indigoPlugin/Contents/Resources/icon.png" width="200" height="200" alt="[Phidget22 logo]" align="right"/>

An update to the [Phidgets Plugin](https://www.indigodomo.com/pluginstore/76/)
for [Indigo](https://www.indigodomo.com/).

Originally created by [Eric Perlman (@perlman)](https://github.com/perlman).
This version is based on his original
[phidgets-indigo](https://github.com/berkinet/phidgets-indigo) project.

## Download and install

On the [GitHub repository](https://github.com/berkinet/phidgets22-indigo), click
**Code**, select **Download ZIP**, unzip the downloaded repository, and
double-click `Phidgets22.indigoPlugin` to install it in Indigo.

## Requirements

**Requires Indigo 2025.2. May work on 2025.1. However, some manual setup may be required.**

- Supported runtime: [Indigo](https://www.indigodomo.com) 2025.2 or newer (Python 3.13)
- The official [Phidget22 Python package](https://www.phidgets.com/docs/Language_-_Python), installed for Indigo's Python 3.13:

  ```zsh
  "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13" \
    -m pip install --upgrade phidget22
  ```

The plugin intentionally does not bundle the native Phidget22 library. Installing
the official package with Indigo's interpreter avoids macOS Gatekeeper quarantine
on routine plugin updates and keeps the Python bindings and native library matched.

See the brief [Getting started guide](https://github.com/berkinet/phidgets22-indigo/blob/main/docs/GETTING_STARTED.md) for plugin setup,
device creation, and printing a Phidgets network map.


See the [full guide](https://github.com/berkinet/phidgets22-indigo/blob/main/docs/LONG_DESCRIPTION.md) for supported devices, features, and advanced usage, and the
[release notes](https://github.com/berkinet/phidgets22-indigo/blob/main/CHANGELOG.md) for changes.

## RFID reader (1024_1)

Create a **RFID Reader (1024)** device and select its discovered server and
reader. The serial number identifies each reader independently. Leave
**Enable antenna on startup** checked to begin reading automatically.
No tag enrolment or allowlist is required: every tag the hardware can read is
accepted. Tag IDs remain strings, preserving leading zeroes.

Indigo states are `tagPresent`, `lastTag`, `protocol`, `antennaEnabled`, and
`lastUpdate`. The last tag ID and protocol remain available after the tag leaves
or the reader disconnects. Before the first detection those fields are empty.
Use **RFID tag detected** and **RFID tag lost** triggers and select the specific
reader. Repeated detection of the same present tag does not repeat the trigger;
a new detection after loss does. State values are published before the trigger.

**Enable RFID antenna** and **Disable RFID antenna** are device actions.
Disabling the antenna clears presence and fires tag lost if a tag was present.
The latest successful antenna setting is restored on hardware reconnect;
a plugin restart reapplies the saved startup setting. A disconnect clears
presence and antenna state without firing tag lost; use the existing Phidget
detached/attached triggers for connection monitoring. A tag already present
on attachment produces a detection. Errors identify the reader and operation.

For the Chicken Feeder, use tag detected to open the feeder and restart an
Indigo automation timer. Let that automation close it after 5–10 minutes.
Do not close directly on tag lost if the hold-open period is desired. The
reader plugin does not maintain a feeder timer or enrol birds. Tag programming
is not exposed by this reader/presence implementation.

Reference: [Phidgets 1024_1 Python API](https://www.phidgets.com/?view=api&product_id=1024_1&lang=Python).
