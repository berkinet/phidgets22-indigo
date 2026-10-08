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

## Restart an auto-off delay on every On request

Choose the Phidgets 22 plugin event **Turn On request received**, then select
the Digital Output or I2C Adapter GPIO Output device. Add a Turn Off action
with a five-minute delay and **Override previous delay** enabled. Each explicit
Turn On request restarts that countdown, including requests while already on,
from scripts, actions, or manual controls.

For an existing auto-off trigger, replace its "state becomes On" event with
this plugin event and keep its delayed action. The event reports command
receipt, not hardware success; Toggle, brightness, and status requests do not
fire it. Indigo owns the delay; no additional plugin timer is created.

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
Every tag the hardware can read is reported. Optional allowed/denied lists
classify detections without suppressing the original detection events. Tag IDs remain strings, preserving leading zeroes.

Indigo states include `tagPresent`, `presenceActive`, `lastTag`, `protocol`, `antennaEnabled`, and
`lastUpdate`. The last tag ID and protocol remain available after the tag leaves
or the reader disconnects. Before the first detection those fields are empty.
Use **RFID tag detected** and **RFID tag lost** triggers and select the specific
reader. Repeated detection of the same present tag does not repeat the trigger;
a new detection after loss does. State values are published before the trigger.

**Enable RFID antenna** and **Disable RFID antenna** are device actions.
Disabling the antenna clears `tagPresent` and fires tag lost if a tag was present.
The latest successful antenna setting is restored on hardware reconnect;
a plugin restart reapplies the saved startup setting. A disconnect clears
`tagPresent` and antenna state without firing tag lost; use the existing Phidget
detached/attached triggers for connection monitoring. A tag already present
on attachment produces a detection. Errors identify the reader and operation.

### RFID output actions and states

On an **RFID Reader (1024)** device, select one of these device actions and
choose **On** or **Off**:

| Action | Channel | On/Off state |
| --- | --- | --- |
| Set RFID digital output | 0 | `digitalOutput` |
| Set RFID LED driver | 1 | `ledDriver` |
| Set RFID onboard LED | 2 | `onboardLED` |

The channel mapping follows the [Phidgets 1024 documentation](https://www.phidgets.com/?prodid=23).
Each output also has an availability state (`digitalOutputAvailable`,
`ledDriverAvailable`, `onboardLEDAvailable`). State reads happen on attachment,
after a command, and every second. When unavailable, the On/Off value is the
last known reading, not a confirmed current state. A failed command is logged
with the reader and output name. A channel that fails to initialize requires
a device restart; open channels automatically reconnect through the SDK.

The RFID device owns all three output channels. Close their Control Panel test
windows and avoid creating separate Indigo Digital Output devices for these
same channels. Output actions do not change antenna or tag-presence states.
Reconnects read the hardware state without replaying previous output commands.
Simulated readers offer the same actions and states, starting with outputs Off.
Tag writing is not supported.

### Delayed presence for feeder access

Set **Presence clear delay (minutes)** in each reader's device configuration,
for example `5`. The default is `0` (clear immediately on loss); decimals are
accepted, so `0.1` gives a six-second delay for simulation testing.

`presenceActive` becomes true on an allowed detection and stays true as long
as that tag remains present. Tag loss starts the configured countdown. A new
allowed detection cancels the countdown; the next loss starts a full new delay.
Denied tags and policy lookup errors cannot activate or extend this presence.
With both list checks disabled, every compatible tag qualifies.

For the Chicken Feeder, create two Indigo **device state change** triggers:

- **Presence active** changes to true → run the action/script that opens the door.
- **Presence active** changes to false → run the action/script that closes the door.

The plugin maintains presence and its timer; Indigo triggers control the door.
`tagPresent` continues to show immediate physical detection, including denied
tags. Each reader has its own timer. Changing the configured delay affects the
next loss, leaving an already-running countdown at its original deadline.

Disconnecting the reader or disabling its antenna starts the same loss delay.
Stopping, disabling, or restarting the device/plugin clears delayed presence
and cancels its timer; a fresh allowed detection activates it again. Countdowns
are not saved across restarts. Clearing an active state can fire the close
trigger. Simulated readers follow the same rules.

Tag programming is not exposed by this reader/presence implementation.

Reference: [Phidgets 1024_1 Python API](https://www.phidgets.com/?view=api&product_id=1024_1&lang=Python).

### Simulated reader (no hardware)

Create an **RFID Reader (1024)** device and check **Simulated reader (no
hardware)** in its device configuration, then Save. No discovered reader or
serial number is required. The connection states identify it as simulated.

Use the device action **Simulate RFID tag detected**, enter a tag ID and choose
its protocol. The tag stays present until **Simulate RFID tag lost**, a different
simulated tag, or antenna disable. Repeating the same tag does not retrigger
until it has been lost. Changing tags emits loss of the previous tag followed
by detection of the new one. Enable/disable antenna actions work in simulation;
scans with the antenna disabled report an error. Restart starts with no tag
present and restores the configured antenna startup setting.

Simulated scans update the normal states and execute real configured Indigo
triggers. You can create two simulated readers to test independent automations.
Simulation actions reject physical readers. To switch to hardware later,
uncheck simulation and select a discovered reader. Tag management below also works with simulated readers.

### Per-reader tag management

1. Create one or two **Indigo variables** for this reader, for example
   `FeederA_AllowedTags` and `FeederA_DeniedTags`. They may initially be empty.
2. Edit the RFID device configuration. Select its **Allowed tags variable**
   and/or **Denied tags variable**. Enable **Check for allowed tag** and/or
   **Check for denied tag** when you want those checks active.
3. Scan a tag (or use **Device Actions → Phidgets Actions → Simulate RFID tag
   detected**). Open the device configuration and check **Manage this reader's
   tags**. Select a recent tag, or enter its ID manually. **Refresh recent tags**
   reloads detections and list membership while the dialog is open.
4. Select an operation in **List edit**, then click **Stage list edit**. Review
   the pending edits and destination variable names. Click **Save** to apply;
   **Cancel** leaves all variables unchanged. **Clear pending edits** discards
   staged changes without closing the dialog.

Each variable contains one exact tag ID per line. Blank lines are ignored;
matching is case-sensitive and preserves leading zeroes. Protocol is shown in
history but is not part of list matching. A tag ID listed here matches that ID
across protocols. Every reader selects its own variables; deliberately sharing
variables shares the list. Avoid using unrelated variables for tag lists.

| Enabled checks | Allowed result |
| --- | --- |
| Neither | Every tag |
| Allowed only | ID appears in the allowed variable |
| Denied only | ID does not appear in the denied variable |
| Both | ID appears in allowed and does not appear in denied |

An empty allowed list permits no tags; an empty denied list blocks none.
The variables are read again on each new detection. **Allowed RFID tag detected** and **Denied RFID tag detected** are additional per-reader triggers.
For feeder hold-open control, use the `presenceActive` state-change triggers
described above. The original **RFID tag detected** continues to fire for every
tag, including denied tags and policy lookup errors.

`lastTagAllowed` is the decision for the last detection. `tagPolicyResult` is
`Allowed`, `Denied`, or `Error`; `tagPolicyError` contains lookup error details.
These states are published before detection triggers and retained after loss.
Denied detections log a Warning naming the reader, tag, protocol, and list-based
reason. Each visit logs once; repeated reports while present do not repeat it.
On lookup failure, allowed is false and neither policy trigger fires; the raw
trigger still fires and the error is logged. Editing lists does not reassess a
currently present tag or generate a new detection: simulate loss and detection
to test a changed policy.

History keeps the 50 most recent unique tag/protocol pairs per reader, with
repeat visits updating last-seen time. It is kept in plugin preferences across
normal restarts. Add ignores duplicates; Remove deletes the ID from that list.
If a tag is in the opposite selected list, Add asks you to choose the explicit
**Move** operation, which removes it there and adds it to the target list.
Pending edits merge into current variable contents on Save, preserving unrelated
changes. If you change variable selections after staging, clear and restage the
edits. Save failures identify the variable in Indigo's log; because Indigo does
not offer atomic multi-variable writes, review both lists if a Move partly fails.

### Expected saturation on generic voltage-ratio inputs

For a generic/raw **Voltage Ratio Input** (no numbered sensor selected), enable
**Suppress saturation error messages** in that device's configuration when
reaching the input limit is expected. The default is unchecked. Custom formulas
can still be used. Only saturation error 4105 moves to debug logging; other
errors keep their existing handling. Selecting a specific sensor hides the
checkbox and ignores its saved value. The option does not change readings,
formulas, triggers, or the hardware measurement range.

### Signed numeric display

Devices with a numeric primary display now include a **Signed display value (+/-)**
text state, `signedValue`. Use it directly in a control-page display instead of
triggers that add a sign to a variable. For example, a numeric reading of `7.66`
becomes `+7.66`, and `-7.66` stays `-7.66`. Zero at two decimal places is `+0.00`,
including small negative values that round to zero.

The state follows the chosen numeric display: a custom numeric formula, voltage,
voltage ratio, temperature unit, humidity, frequency/count/time, or selected
BME280/SGP41 measurement. It uses the reading's decimal precision or the device's
configured precision; “No limit” preserves the supplied number's precision.
At startup it initializes from the retained numeric display state without firing
triggers, then follows new readings. The initial text represents the retained
reading and does not imply a fresh hardware measurement. Text and On/Off displays do not get
this companion state. Numeric states remain unchanged for calculations and
triggers. Non-finite or nonnumeric readings clear the companion text; this is
formatting, not a new sensor-validity or freshness indicator. `signedValue` is
reserved and cannot be used as a custom formula's state name.

For Pool water level, use `cmBelowFull` for numeric comparisons and `signedValue`
for signed display. Once the display uses that state, the sign-formatting triggers
and variable are no longer needed. The plugin does not edit those automations.

### DAQ1500 Wheatstone bridge / load cells

Create a **Voltage Ratio Input** for each DAQ1500 bridge channel (0 or 1).
Select the discovered server, VINT hub port, DAQ1500, and channel. The dialog
recognizes the bridge and replaces numbered-sensor settings with bridge controls.
Choose **DAQ1500 bridge gain**: 1x, 2x, 64x, or 128x (default), and leave
**Enable bridge input** checked. Both settings are reapplied on reconnect.
Start at 128x and lower it if your maximum expected load causes saturation.

The default interval is 1000 ms. Use at least 100 ms when both channels are
active (20 ms is available with only one channel). Hardware-reported interval
limits are checked on attachment. Select six decimal places or No limit when
inspecting small raw ratios. The `voltageRatio` state is in V/V.

To calibrate a scale:

1. Save the channel, bridge gain, and enabled setting. Let the device attach,
   then reopen its configuration. Keep the ratio change trigger at zero and
   saturation messages enabled while calibrating.
2. Remove the load, let the reading settle, and click **Capture unloaded zero**.
3. Apply a known weight and let the reading settle. Enter **Known weight**, select
   its units (kg, g, lb, or N), and click **Calibrate with known weight**.
4. Click **Save**. The numeric `weight` state becomes the device display, with
   `signedValue` following its configured precision. Raw `voltageRatio` remains
   available. The selected units label the weight state; they do not convert
   previously calibrated values automatically.

The displayed **Calibration gain** and **Calibration offset** use
`weight = (voltageRatio + offset) * calibrationGain`. Calibration gain is a
software conversion factor, separate from the hardware's 1x–128x bridge gain.
Calibration is saved per channel and survives plugin restarts and reconnects.
The plugin does not import calibration from the Phidgets Control Panel.

**Tare scale** stages a new zero offset while preserving calibration gain;
click Save to apply it. **Clear calibration** returns the display to raw ratio
on Save. Cancel discards all pending calibration and tare changes. Buttons read
the active saved device; for a new device, save it before calibrating. Readings
are rejected while disconnected, disabled, or waiting for recovery from an error.
Let the load settle before capture; each button captures one reading.

When moving the same load cell and bridge to another server, hub, port, or
channel, select the new connection and click **Keep calibration for moved scale**,
then Save. This preserves calibration gain and tare offset; it does not take a
reading or change the hardware before Save. Use this only for the same scale,
with unchanged bridge gain and units. Check zero after installation, since
mechanical mounting can affect it.

A different load cell, hardware gain, or units requires recalibration. Clear the
old calibration, save the new channel/gain, then reopen the dialog to calibrate.
Custom formulas remain available as an alternative to built-in calibration;
the two cannot be enabled together. Disabled or disconnected devices retain
last readings; those retained states do not indicate a current measurement.

Reference: [Phidgets DAQ1500 guide](https://www.phidgets.com/?prodid=957).
Automated tests cover setup, calibration, and failure handling. Physical DAQ1500
and Indigo dialog validation remain pending.
