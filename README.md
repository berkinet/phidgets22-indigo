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
