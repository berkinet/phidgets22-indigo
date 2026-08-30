
# Phidgets 22 for Indigo

<img src="./Phidgets22.indigoPlugin/Contents/Resources/icon.png" width="200" height="200" alt="[Phidget22 logo]" align="right"/>

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

- [Indigo](https://www.indigodomo.com) 2022.1 or newer
- The official [Phidget22 Python package](https://www.phidgets.com/docs/Language_-_Python), installed for Indigo's Python 3.13:

  ```bash
  "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13" \
    -m pip install --upgrade phidget22
  ```

The plugin intentionally does not bundle the native Phidget22 library. Installing
the official package with Indigo's interpreter avoids macOS Gatekeeper quarantine
on routine plugin updates and keeps the Python bindings and native library matched.

See the brief [Getting started guide](docs/GETTING_STARTED.md) for plugin setup,
device creation, and printing a Phidgets network map.

See [Release notes](CHANGELOG.md) for changes in each published version.

Maintainers should follow the
[Indigo Plugin Store publication guide](docs/INDIGO_PLUGIN_STORE.md) for the
permanent plugin identity, release procedure, and Store submission checklist.

## Status

The following Phidget classes are currently supported:
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
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Phidget Addressing

See the [Phidget Documentation](https://www.phidgets.com/docs/Addressing_Phidgets]) for details on how to address a Phidget.

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

- [Baseline architecture and assessment](docs/BASELINE_ASSESSMENT.md)
- [Read-only discovery inventory](docs/DISCOVERY_INVENTORY.md)
- [Preparatory cleanup audit](docs/CLEANUP_AUDIT.md)
- [Phidget class support roadmap](docs/PHIDGET_CLASS_ROADMAP.md)
- [Indigo Plugin Store publication](docs/INDIGO_PLUGIN_STORE.md)
