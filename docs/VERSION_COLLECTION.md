# Read-only version collection

This phase adds reporting only. It does not install server software, load
firmware, reboot hardware, or expose an update action.

## Targets

Version information is collected for two independently modeled targets:

1. Phidget Network Server Indigo devices.
2. Enabled Phidgets 22 Indigo devices.

For a Phidget device, having firmware and supporting firmware upgrades are
separate properties. A device can report a firmware version without supporting
an upgrade. Logical peripherals which have no firmware, such as an I2C sensor
implemented on a Data Adapter, report that fact normally rather than as an
error.

## Storage and lifecycle

Indigo device states are the authoritative store. There is no parallel
persistent database or cache. Each Indigo device owns its reported values,
even when several channel devices happen to expose the same physical Phidget
firmware.

At plugin startup, all devices owned by the plugin are asked to rebuild their
dynamic state lists. This migrates existing devices in place. New devices use
the same dynamic state definitions when they are created.

Collection runs asynchronously shortly after startup, after newly started
devices have had an opportunity to attach, on the configured interval, and on
request from the plugin menu. The interval can be disabled. A collection
failure changes only the version-reporting states and never changes normal
device operation or availability.

## Data sources

An attached channel's Phidget SDK handle supplies its physical-device firmware
version. The SDK's firmware-upgrade identifier indicates whether the physical
device supports the firmware-upgrade mechanism. Logical peripherals without a
native Phidget handle have no firmware of their own.

The Network Server protocol version is read from an attached remote Phidget
channel belonging to that server. If a monitored server has no attached plugin
channel at collection time, its version is reported as unavailable; no new
channel is opened merely to obtain a version.
