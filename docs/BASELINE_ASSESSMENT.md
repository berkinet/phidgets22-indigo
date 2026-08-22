# Phidgets22 Indigo Plugin Baseline Assessment

Assessment date: 2026-08-21  
Baseline commit: `ce87e8c1fd215972192ff52c5ff4304ba4260f05`  
Working branch: `codex/production-hardening`

## Purpose and scope

This document records the plugin's existing structure and observable behavior before production-hardening work begins. It is a code and configuration assessment, not a statement that every path has been exercised against Indigo and physical Phidgets.

The governing constraint is to preserve the behavior that is already trusted in daily production use. Findings below are therefore observations and test targets. They are not authorization to refactor or change stable paths.

No runtime code, Indigo XML, bundled Phidget22 code, or plugin metadata was changed during this assessment.

## Product baseline

- Indigo plugin identifier: `com.yikes.eric.phidgets-indigo`
- Display name: `Phidgets 22`
- Plugin version: `0.2.0`
- Indigo Server API version: `3.0`
- Bundled Phidget22 Python package version: `1.23.20251006`
- Repository default branch: `master`
- Current development branch: `codex/production-hardening`
- Supported operating mode documented by the project: network Phidgets only; locally attached hardware must be exposed through a Phidget Network Server.

The plugin bundles the complete generated Phidget22 Python API under `Server Plugin/Phidget22`. The plugin-specific integration is comparatively small and consists primarily of `plugin.py`, `phidget.py`, seven device wrappers, Indigo XML definitions, sensor metadata, and utilities.

## System structure

| Area | Files | Current responsibility |
| --- | --- | --- |
| Indigo lifecycle and dispatch | `plugin.py` | Plugin startup, preferences, UI validation hook, device-wrapper construction, Indigo actions, triggers, stop, and shutdown |
| Shared Phidget lifecycle | `phidget.py` | Channel/network descriptors, asynchronous open, initial attachment timeout, common attach/detach/error handlers, close, and range checking |
| Device integrations | `digitalinput.py`, `digitaloutput.py`, `frequencycounter.py`, `humiditysensor.py`, `temperaturesensor.py`, `voltageinput.py`, `voltageratioinput.py` | Phidget22 object creation, channel-specific configuration, event handlers, Indigo states, display state, and supported Indigo actions |
| Indigo UI and declarations | `Devices.xml`, `PluginConfig.xml`, `Events.xml`, `Actions.xml`, `MenuItems.xml` | Device configuration forms, plugin preferences, attach/detach triggers, and declared action/menu surfaces |
| Sensor metadata | `PhidgetInfo.py`, `sensortypes.py`, `Resources/phidgets.json` | Builds Indigo menu choices and maps Phidget units to Indigo state names |
| Diagnostics utility | `phidget_util.py` | Formats physical/channel information for attach and detach log messages |
| Standalone discovery utility | `scan.py` | Command-line Manager-based scanner; it is not imported by the running Indigo plugin |
| Metadata | `Info.plist`, `README.md` | Plugin identity, versions, requirements, and high-level support statement |

## Lifecycle and data flow

### 1. Plugin initialization

Indigo constructs `Plugin` from `plugin.py`. The constructor:

- initializes file and Indigo logging;
- creates `activePhidgets`, a map from Indigo device ID to wrapper instance;
- loads `Resources/phidgets.json` through `PhidgetInfo` for configuration menus; and
- initializes an in-memory trigger registry.

### 2. Plugin startup

`Plugin.startup()`:

1. Enables or disables low-level Phidget API logging from plugin preferences.
2. Applies the selected plugin logging level when it is nonzero.
3. Logs the installed native Phidget library version.
4. Unconditionally enables discovery of `PHIDGETSERVER_DEVICEREMOTE` servers.

The `enableServerDiscovery` preference is presented as read-only and defaults to true, but startup currently enables discovery without consulting that value.

### 3. Indigo device configuration

Each of the seven device forms collects physical addressing manually:

- serial number;
- channel;
- whether the device is connected to a VINT hub;
- whether it is itself a VINT device; and
- hub port when applicable.

The forms explicitly state that these fields will eventually be populated automatically.

`validateDeviceConfigUi()` does not validate the values. It constructs an Indigo display address from the supplied fields. If an Indigo variable named `p22_<serial number>` exists and has a value, that value is substituted as a friendly label in the display address.

The address is descriptive; the wrapper is still opened using the numeric configuration fields.

### 4. Device start

`Plugin.deviceStartComm()`:

1. Parses common addressing properties and plugin preferences.
2. Constructs `ChannelInfo`, containing the serial number, channel, hub port, hub-port-device flag, and a `NetInfo` object.
3. Parses shared display and sampling properties.
4. Selects one of seven wrapper classes through a device-type conditional.
5. Stores the wrapper in `activePhidgets`.
6. Calls the wrapper's `start()` method.
7. Tells Indigo that the device's dynamic state list or display state may have changed.

Construction and startup exceptions are logged. A failed startup is not re-raised to Indigo by this method.

### 5. Shared channel open

`PhidgetBase.start()` applies these Phidget22 constraints:

- device serial number;
- channel number;
- remote/local flag;
- hub-port-device flag; and
- hub port.

It then starts a one-shot attachment timer, installs wrapper-specific handlers, and calls the Phidget22 asynchronous `open()` operation.

No hostname, network-server port, password, or server name is applied. Although `NetInfo` has fields for hostname, port, and password, the current runtime path neither populates nor consumes them.

### 6. Attach

The common attach handler:

- cancels the initial attachment timer;
- clears the Indigo error state;
- logs the physical/channel identity; and
- fires the Indigo `deviceAttached` trigger.

Each measurement wrapper then applies its device-specific configuration, such as data interval, change trigger, sensor type, filter, input mode, or power supply. Exceptions during this post-attach configuration are logged and do not undo the common attached state.

### 7. State updates and actions

Phidget22 event callbacks update Indigo states directly. Dynamic state lists and display-state selection are supplied by the wrappers at runtime.

Only `DigitalOutput` accepts Indigo device-control actions. It implements turn on, turn off, toggle, brightness, and status request through asynchronous Phidget22 setters or direct reads.

Only `DigitalInput` implements a sensor status request. Other sensor wrappers are event-driven.

### 8. Detach and initial timeout

The initial attachment timer sets the Indigo device error state to `Detached` and logs an error if no attach callback occurs within the configured timeout.

The common detach callback also sets `Detached`, logs the event, and fires the Indigo `deviceDetached` trigger. The channel remains open; the code does not close or recreate it on detach, leaving reconnection behavior to the Phidget22 channel object.

The timer is only for the initial open. A later detach does not start a new timeout or create a distinct server-unavailable/reconnecting state.

### 9. Device stop and plugin shutdown

`deviceStopComm()` removes the wrapper from `activePhidgets` and calls `close()` after cancelling any attachment timer.

Plugin shutdown calls `Phidget.finalize(0)`. There is no explicit loop over `activePhidgets` in `shutdown()`; normal Indigo device-stop callbacks are presumed to perform per-channel cleanup.

## Supported device classes

The source and README agree on seven supported channel classes.

| Indigo device type | Phidget22 class | Indigo states/display | Configuration applied after attach | Indigo actions |
| --- | --- | --- | --- | --- |
| Digital Input | `DigitalInput` | `onOffState`, `lastUpdate`; configurable state icons | Event handlers only | Request status |
| Digital Output | `DigitalOutput` | Inherited dimmer `onOffState` and `brightnessLevel` | Event handlers only | On, off, toggle, brightness, request status |
| Frequency Counter | `FrequencyCounter` | `frequency`, `count`, `timeChange`; selectable display | Data interval, frequency cutoff, enabled state, plus filter type or DAQ1400 input mode/power supply | None |
| Humidity Sensor | `HumiditySensor` | `humidity` | Data interval and humidity change trigger | None |
| Temperature Sensor | `TemperatureSensor` | `tempC`, `tempF`; selectable display unit | Data interval, optional thermocouple type, temperature change trigger | None |
| Voltage Input | `VoltageInput` | Raw voltage plus sensor-derived or custom state | Data interval, sensor type, voltage trigger, sensor-value trigger | None |
| Voltage Ratio Input | `VoltageRatioInput` | Raw voltage ratio plus sensor-derived or custom state | Data interval, sensor type, ratio trigger, sensor-value trigger | None |

The bundled SDK contains many additional Phidget22 channel classes. Their presence in the bundle does not mean the Indigo plugin supports them.

## Network and discovery model

The current production path uses Phidget22's global server discovery and remote-channel addressing:

1. Discovery of remote device servers is enabled globally during plugin startup.
2. Each wrapper marks its channel remote using the read-only `networkPhidgets` preference.
3. The channel is narrowed using serial number, channel, hub port, and hub-port-device status.
4. Phidget22 discovers and attaches the matching remote channel asynchronously.

There is no active Indigo-side inventory of discovered servers, devices, or channels. The `Manager`-based implementation in `scan.py` demonstrates discovery concepts but is a standalone command-line utility and is not connected to the plugin UI.

Consequently, the current runtime does not select a named server for a device. If multiple discoverable servers expose channels that satisfy the same addressing constraints, the plugin provides no additional server constraint in its active path.

## Error handling and diagnostics baseline

### Current behavior

- Initial attachment timeout: Indigo error `Detached` plus an error log.
- Runtime detach: Indigo error `Detached`, debug identity log, and detach trigger.
- Reattach: clears Indigo error, emits debug identity log, and fires attach trigger.
- Phidget error event: logs code and string.
- Device-start exception: logs a traceback.
- Post-attach configuration exception: logs a traceback inside the wrapper.
- Digital-output asynchronous write failure: logs result code and details, then refreshes Indigo state.
- Optional suppression: selected legacy error codes can be hidden globally or, for one code, per voltage device.

### Current limitations

- `Detached` represents multiple conditions: no initial match, hardware removal, hub removal, and network/server loss.
- No explicit retry status, retry count, outage duration, or recovery log level exists.
- Post-attach configuration can fail after the common handler has cleared the Indigo error state.
- There is no structured diagnostic report or menu action.
- There is no explicit lifecycle state model beyond the Indigo error and Phidget callbacks.
- Configuration errors are discovered during parsing or attachment rather than in `validateDeviceConfigUi()`.

## Indigo extension surfaces

- Events: `deviceAttached` and `deviceDetached`, each scoped to a selected plugin device.
- Actions: none declared in `Actions.xml`; standard Indigo device/sensor actions are handled through plugin callbacks.
- Menu items: none declared.
- Plugin preferences: network mode, server discovery, attach timeout, error suppression, plugin logging, and low-level Phidget API logging.
- Dynamic menus: sensor/filter/thermocouple/input/power types are populated from `phidgets.json`.

## Observations requiring controlled verification

These are potential deficiencies or ambiguities found by inspection. Because the plugin is in daily use, each should be reproduced or covered by a focused test before any change.

1. **Humidity change-trigger range**: `HumiditySensorPhidget` passes `getHumidityChangeTrigger()` as both the minimum and maximum. The intended Phidget22 accessors appear likely to be the minimum and maximum trigger methods. As written, non-current values may be rejected locally.
2. **Frequency count states**: `count` and `timeChange` are exposed, and an `onCountChangeHandler()` exists, but only the frequency-change callback is registered. Confirm whether those two states ever update in production and whether the current SDK exposes a count callback for the supported hardware.
3. **Digital-input display state**: the wrapper returns `onState` as its display-state ID while its dynamic boolean state is named `onOffState`. Confirm what Indigo actually displays and whether `onState` is a recognized inherited alias for a custom device.
4. **Digital-output initial state**: attach clears the error state but does not call `updateIndigoStatus()`. Confirm whether Indigo retains the correct state across plugin restarts before the first action or explicit status request.
5. **Post-attach configuration failure**: common attach handling clears `Detached` before wrapper configuration. Confirm the user-visible state when a data interval, sensor type, or other post-attach property is rejected.
6. **Initial timer race**: the common attach handler assumes `self.timer` exists and is cancellable. Test fast attach, stop-during-open, and attach near timeout boundaries.
7. **Device-stop assumptions**: `deviceStopComm()` pops without a default. Confirm Indigo never invokes stop for a device absent from `activePhidgets`, including failed construction/start cases.
8. **Server-discovery preference semantics**: `enableServerDiscovery` is stored in `NetInfo` but not consulted by startup or `PhidgetBase`. Confirm whether it is intentionally fixed true and should remain a compatibility-only preference.
9. **Unused network fields**: `NetInfo.hostname`, `port`, and `password` are unused. Determine whether they are abandoned scaffolding or the intended seam for explicit server support.
10. **Custom formulas**: voltage and voltage-ratio custom formulas use Python `eval()` on user-supplied plugin configuration. This is existing advanced functionality with security and support implications; document the trusted-admin assumption before considering release.
11. **Boolean property interpretation**: several values are coerced with `bool(value)`. Confirm Indigo supplies actual booleans rather than strings for all relevant checkbox fields.
12. **Legacy suppression codes**: error codes `4098`, `4099`, and `4103` are suppressed by numeric value. Verify their meaning against the bundled/current Phidget22 SDK and the physical devices that generate them.

## Validation performed

The following non-hardware checks passed against the baseline:

- Python compilation for all plugin-specific and bundled `.py` files using the system Python 3 interpreter, with bytecode redirected outside the repository.
- XML well-formedness for `Actions.xml`, `Devices.xml`, `Events.xml`, `MenuItems.xml`, and `PluginConfig.xml` using `xmllint`.
- Property-list validation for `Info.plist` using `plutil`.
- JSON parsing for `Resources/phidgets.json`; its top-level object contains 48 entries.
- Clean Git working tree before documentation was added.

These checks do not validate Indigo XML semantics, native Phidget library loading, Indigo API behavior, network discovery, or hardware behavior.

## Hardware-dependent baseline still needed

Before behavioral changes, capture the following on the production/test Indigo installation for each device class actually available:

- exact Phidget model and serial number (serial number may remain private in published records);
- connection topology: network server, hub, hub port, and channel;
- current plugin configuration values;
- successful plugin restart and initial attachment;
- current Indigo states immediately after attach;
- normal event/state updates;
- supported Indigo control/status actions;
- unplug/detach behavior;
- replug/reattach behavior;
- network-server stop and restart behavior;
- hub disconnect and reconnect behavior where applicable;
- relevant normal and failure logs.

This becomes the tested-support matrix. A device class or model should not be advertised as supported solely because a corresponding class exists in the bundled Phidget22 SDK.

## Recommended next decision gate

Review this baseline against the live installation before implementation. The first implementation slice should be selected only after confirming:

1. which current device classes and models must be protected;
2. which observation above is visible in real operation;
3. which server/discovery topology is used in production; and
4. where a small, reversible improvement can be tested without changing the established channel-open behavior.

The likely first feature remains discovery-backed configuration, but its initial slice should inventory servers/devices/channels without yet replacing or rewriting the existing manual addressing path.
