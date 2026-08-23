
# Phidgets 22 for Indigo

<img src="./Phidgets22.indigoPlugin/Contents/Resources/icon.png" width="200" height="200" alt="[Phidget22 logo]" align="right"/>

An update to the [Phidgets Plugin](https://www.indigodomo.com/pluginstore/76/)
for [Indigo](https://www.indigodomo.com/).

Originally created by [Eric Perlman (@perlman)](https://github.com/perlman).
This version is based on his original
[phidgets-indigo](https://github.com/perlman/phidgets-indigo) project.

## Download and install

Download the latest `Phidgets22-*.zip` file from
[GitHub Releases](https://github.com/berkinet/phidgets22-indigo/releases), unzip
it, and double-click `Phidgets22.indigoPlugin` to install it in Indigo.

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

## Status

The following Phidget classes are currently supported:
* DigitalInput
* DigitalOutput
* FrequencyCounter
* HumiditySensor
* TemperatureSensor
* VoltageInput
* VoltageRatioInput

Only network phidgets are supported. To use local attached phidgets, enable the [network server](https://www.phidgets.com/docs/Phidget_Network_Server).

## Phidget Addressing

See the [Phidget Documentation](https://www.phidgets.com/docs/Addressing_Phidgets]) for details on how to address a Phidget.

## Development documentation

- [Baseline architecture and assessment](docs/BASELINE_ASSESSMENT.md)
- [Read-only discovery inventory](docs/DISCOVERY_INVENTORY.md)
- [Preparatory cleanup audit](docs/CLEANUP_AUDIT.md)
