# Read-only version collection

This phase adds reporting only. It does not install server software, load
firmware, reboot hardware, or expose an update action.

## Targets

Version information is collected for two independently modeled targets:

1. Phidget Network Server Indigo devices.
2. Enabled Phidgets 22 Indigo devices.

For a Phidget device, having firmware, having compatible firmware in the
bundled catalog, and having a newer version available are separate properties.
A device can report a firmware version without a compatible catalog entry.
Logical peripherals and hub-port modes which have no independent firmware
report that fact normally rather than as an error.

## Storage and lifecycle

Indigo device states are the authoritative store. There is no parallel
persistent database or cache. Each Indigo device owns its reported values,
even when several channel devices happen to expose the same physical Phidget
firmware.

At plugin startup, each enabled device rebuilds its dynamic state list after
its device-specific wrapper is registered. This migrates existing devices in
place without temporarily removing their device-specific states. New devices
use the same dynamic state definitions when they are created.

Collection runs asynchronously shortly after startup, after newly started
devices have had an opportunity to attach, on the configured interval, and on
request from the plugin menu. The interval can be disabled. A collection
failure changes only the version-reporting states and never changes normal
device operation or availability.

## Data sources

An attached channel's Phidget SDK handle supplies its physical-device firmware
version and exact firmware-upgrade identifier. That identifier, plus the VINT
ID where applicable, is matched against a filename-only catalog generated from
`phidget22admin` 1.26.20260828. The highest matching version determines whether
an update is available; crossing a hundred-series boundary is marked as a
potentially breaking major update. No firmware payloads are bundled or applied.

The Network Server protocol version is read from an attached remote Phidget
channel belonging to that server. If a monitored server has no attached plugin
channel at collection time, its version is reported as unavailable; no new
channel is opened merely to obtain a version.
