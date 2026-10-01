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
