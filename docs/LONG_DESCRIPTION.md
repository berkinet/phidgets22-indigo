
# Phidgets 22 — Full Guide

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

The Store may display an older minimum based on the plugin API declaration.
That is an installation compatibility threshold, not a claim of tested support
for older Indigo releases.

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

Releases use `year.major.minor` version numbers, starting with **2026.1.0**.
See [Release notes](https://github.com/berkinet/phidgets22-indigo/blob/main/CHANGELOG.md) for changes in each published version.

Maintainers should follow the
[Indigo Plugin Store publication guide](https://github.com/berkinet/phidgets22-indigo/blob/main/docs/INDIGO_PLUGIN_STORE.md) for the
permanent plugin identity, release procedure, and Store submission checklist.

## Status

The following Phidget classes are currently supported:

* Phidget Network Server (read-only availability and connection metadata)
* DigitalInput
* DigitalOutput
* FrequencyCounter
* HumiditySensor
* BME280/BMP280 environmental sensors through an ADP0001 I2C adapter
* SGP41 VOC/NOx gas sensors through an ADP0001 I2C adapter, including raw
  signals and Sensirion VOC/NOx indices
* LCD
  * Native Phidget LCD channels
  * Configurable HD44780/PCF8574-compatible character LCDs through an ADP0001
    DataAdapter, including Freenove 16×2 and 20×4 modules
* DataAdapter (shared I2C transport)
  * ADP0001 GPIO 0/1 as separate Indigo input or relay devices
* TemperatureSensor
* VoltageInput
* VoltageRatioInput

Only network phidgets are supported. To use local attached phidgets, enable the [network server](https://www.phidgets.com/docs/Phidget_Network_Server).

## Version reporting

The plugin collects version information without changing servers or device
firmware. Native Phidget devices report the installed and latest compatible
firmware versions, whether the Phidgets `phidget22admin` catalog supports the
exact hardware, and whether a newer firmware version is available. Potentially
breaking major updates are identified separately. Logical peripherals and hub
port modes without independent firmware report **No firmware**. Network Server
devices report the server protocol version when an attached plugin device on
that server is available for the read.

At each collection, the plugin checks Phidgets' official `phidget22admin`
archive index. If a newer archive exists, it reads only the firmware filenames
from that archive; it does not install firmware or run the admin tool. If the
check fails, it keeps the last successfully downloaded catalog across plugin
restarts (or the bundled snapshot if none has been downloaded), and tries again
on the next collection. The filename cache is stored beside the Indigo plugin
log. Firmware availability is therefore
relative to the most recently retrieved catalog, not a guarantee that every
new Phidgets release has already been checked.

Automatic collection is daily by default and can be disabled or changed to 6
hours, 12 hours, or weekly in the plugin configuration. Use **Update Indigo
Phidget device firmware versions** in the plugin menu for an immediate
asynchronous check.

Use **Print Indigo Phidget devices to log** for the configured Indigo records.
Use **Print all visible Phidgets to log** to print every local and remote
device and channel currently visible to the plugin's Phidget22 Manager. The
report is generated through the loaded SDK and requires no external executable.

Use **Export Indigo Phidget devices and states to a JSON file** to write every
configured plugin device and its complete current state dictionary to
`Phidgets 22 Device States.json` in Indigo's Logs directory. Indigo scripts
and Action Groups can request the same read-only snapshot through the plugin
action:

```python
plugin = indigo.server.getPlugin("com.yikes.eric.phidgets-indigo")
plugin.executeAction("exportDeviceStatesJson")
```

When a firmware update first becomes available, the plugin logs one Warning
for each affected Indigo device. After each collection it updates the Indigo
variable `Phidgets22_FirmwareUpdatesAvailable` with a readable list of all
enabled devices reporting updates. A change to a non-empty list fires the
global plugin Event **Device firmware update available** once, so one Indigo
Trigger can handle the whole collection. An unchanged list or a change to an
empty list does not fire the Event. The plugin action **Log devices with
available firmware updates** writes the current list at Warning level. The
plugin never installs firmware.

In a Trigger action's text field (for example an email body), reference the
variable using Indigo's `%%v:VARIABLE_ID%%` substitution. Replace
`VARIABLE_ID` with the ID of `Phidgets22_FirmwareUpdatesAvailable` shown in
Indigo's Variables list. The firmware Event's configuration page displays the
actual, selectable `%%v:<ID>%%` reference for copying into an action. If the
variable has not been created yet, run a version collection first.

To exercise the full firmware-update notification path without changing
hardware, call the script-only `testFirmwareVersionOverride` plugin action
through `plugin.executeAction()`. Supply an attached Indigo Phidget device ID and a positive
firmware version older than both the installed and latest catalog versions.
The action runs a normal asynchronous collection with that one reported
version overridden. Its Warning and variable entry are marked `TEST ONLY`.
Leave the override active for another collection to verify that no duplicate
notification fires. Clear it by executing the same action with the same device
ID and an empty firmware version; another collection restores the SDK value
and clears the test update. The override is also discarded on plugin restart.

Indigo scripting-shell example:

```python
plugin = indigo.server.getPlugin("com.yikes.eric.phidgets-indigo")
plugin.executeAction("testFirmwareVersionOverride", props={
    "deviceId": "123456789", "firmwareVersion": "100"})
# Later, restore the real SDK-reported version:
plugin.executeAction("testFirmwareVersionOverride", props={
    "deviceId": "123456789", "firmwareVersion": ""})
```

The test action is hidden from Indigo's Action picker, but remains callable
from scripts. It can execute the user's real Trigger actions, such as email or
logging. It never writes firmware to a Phidget.

When the plugin starts, the first live value received for each state establishes
its baseline without firing Indigo Device State Changed triggers. Later state
updates retain normal trigger behavior.

## SGP41 gas indices

The SGP41 device samples once per second and publishes both raw sensor signals
and the stateful Sensirion `vocIndex` and `noxIndex` values. The indices remain
zero during the algorithm's initial warm-up and then range from 1 through 500.
They describe changes relative to the sensor's learned recent environment; they
are not gas concentrations or regulatory exposure measurements.

Temperature and relative-humidity compensation can each use either a directly
entered value or an arbitrary Indigo device state. A selected temperature state
must contain degrees Celsius and a humidity state must contain percent relative
humidity. If a selected state becomes unavailable or invalid, sampling continues
with the corresponding directly entered fallback value and logs one warning.

The bundled pure-Python Gas Index Algorithm is derived from Sensirion's
BSD-licensed reference implementation. Attribution is recorded in
[THIRD_PARTY_NOTICES.md](https://github.com/berkinet/phidgets22-indigo/blob/main/THIRD_PARTY_NOTICES.md).

## Phidget Addressing

See the [Phidget Documentation](https://www.phidgets.com/docs/Addressing_Phidgets) for details on how to address a Phidget.

## Custom sensor formulas

Voltage Input and Voltage Ratio Input devices can calculate a custom state from
the raw reading. In a formula, `x` is the reading. Formulas may contain numeric
constants, parentheses, `+`, `-`, `*`, `/`, `%`, `**`, comparisons (`<`, `<=`,
`>`, `>=`, `==`, `!=`), `and`, `or`, `not`, `True`, `False`, and conditional
expressions such as `1 if x > 2.5 else 0`. Boolean results become numeric `1.0`
or `0.0` when Number output is selected.

The custom formula controls include an **Output type** choice:

- **Number** requires numeric branches and also accepts boolean results as
  `1.0` or `0.0` for backward compatibility.
- **Text** requires every result branch to be a quoted string literal of no
  more than 100 printable characters. For example,
  `"Off" if x <= 2.5 else "On"`.
- **On/Off** requires a boolean result, such as `x > 2.5`, and creates a real
  Indigo boolean state.

Text supports literal and conditional selection only. String concatenation,
repetition, methods, formatting, and use as a function argument are rejected.

The constants `pi` and `e` and these functions are available: `abs`, `min`,
`max`, `round`, `clamp`, `sqrt`, `exp`, `log`, `log10`, `sin`, `cos`, `tan`,
`asin`, `acos`, `atan`, `sinh`, `cosh`, `tanh`, `floor`, and `ceil`. `round`
accepts an optional whole-number digit count from -15 through 15. `clamp`
accepts a value, minimum, and maximum. Other Python names and operations are
not supported.

## Development documentation

The runtime code is divided by responsibility: `plugin.py` coordinates Indigo
and Phidget lifecycle, `device_factory.py` constructs channel wrappers,
`actions.py` implements action callbacks, and `discovery_ui.py` implements
configuration and discovery callbacks.

- [Baseline architecture and assessment](https://github.com/berkinet/phidgets22-indigo/blob/main/docs/BASELINE_ASSESSMENT.md)
- [Read-only discovery inventory](https://github.com/berkinet/phidgets22-indigo/blob/main/docs/DISCOVERY_INVENTORY.md)
- [Read-only version collection](https://github.com/berkinet/phidgets22-indigo/blob/main/docs/VERSION_COLLECTION.md)
- [Preparatory cleanup audit](https://github.com/berkinet/phidgets22-indigo/blob/main/docs/CLEANUP_AUDIT.md)
- [Phidget class support roadmap](https://github.com/berkinet/phidgets22-indigo/blob/main/docs/PHIDGET_CLASS_ROADMAP.md)
- [Indigo Plugin Store publication](https://github.com/berkinet/phidgets22-indigo/blob/main/docs/INDIGO_PLUGIN_STORE.md)

### Indigo 2025.1 compatibility

Indigo 2025.1 uses Python 3.11, according to the
[Indigo Python packages documentation](https://wiki.indigodomo.com/doku.php?id=indigo_2025.1_documentation%3Apython_packages).
**Requires Indigo 2025.2. May work on 2025.1. However, some manual setup may be required.**

Live Indigo 2025.1 validation remains pending. Manual setup may include
installing or updating Phidget22 for Indigo's Python runtime. For the
documented Python 3.11 runtime, use:

```zsh
"/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11" -m pip install --upgrade phidget22
```

The plugin's dependency messages detect the running Python version and provide
the matching command. No additional Python version needs to be installed.
