# Phidgets 22 review: runtime errors and recovery

Reviewed 14 October 2026. Baseline: **2026.1.39**, `main`, commit `bcbc7886980c9a2bad78f90433dbf07ee3fc8309`.

The recent fixes improved specific outage messages, but runtime error management is still inconsistent. The highest-priority problems concern lifecycle ownership, exceptions escaping callback boundaries, and repeated fault reporting. More suppression alone would hide some failures without making recovery correct.

This is an assessment, not an implementation release. Runtime source, release tags, and tests were not changed. The report and its companion probes are local review artifacts.

## Scope and evidence

- Repository-wide inventory of error/warning logging and explicit traceback emission. Python syntax checked for all 50 top-level server-plugin modules; all five XML files and the version plist validated.
- Detailed source review of native-channel lifecycle, Indigo dispatch, async Digital Output/GPIO actions, logical I2C peripherals, LCD callbacks/animations, server monitoring, outage coalescing/persistence, state publication, RFID output polling, and event/version-collection boundaries. Discovery/configuration and identity helpers were checked where they affect those paths. This was not a line-by-line audit of every configuration option or bundled sensor algorithm.
- All **418 existing tests pass**. Persistence, device-wrapper, outage, network-server and LCD test modules also pass independently.
- Seven observations reproduced with existing test doubles in [the companion probes](2026-10-14-error-report-management-probes.py). No live Indigo process, network server, or hardware was changed or accessed. Deterministic callback interleavings establish possible failures, not their frequency on hardware.
- Physical acceptance remains necessary: startup with a server already down, sustained power loss, restoration during a pending write, shutdown during attachment, and adapter loss with active sensors/displays.

## Findings, in priority order

### 1. P1 — Attachment completion can resurrect a stopped or detached device

[phidget.py:665](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/phidget.py:665>)

`onAttachHandler` checks lifecycle state before calling initialization, but does not validate that lifecycle again before committing `attached`. Initialization can overlap `stop()` or a detach. The late completion then cancels timers, clears the saved outage, clears Indigo's error, reports attachment and allows subclass attachment action groups to run. A deterministic probe stops the wrapper from inside initialization: the native handle is closed, but the final wrapper state is `attached` and Indigo receives a healthy error clear.

**Fix:** capture a lifecycle epoch at callback entry and require that same epoch at completion. Stop/detach must invalidate in-flight initialization. Subclasses must not run attachment side effects for a discarded callback. Add interleaving tests for stop, detach, and a subsequent fresh attachment, including the saved record and LCD action groups.

This is consistent with the earlier shutdown log, but that log alone does not prove this race caused every repeated action.

### 2. P1 — GPIO output failure callbacks can raise a second exception; other runtime boundaries also lack guards

[adapter_gpio.py:106](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/adapter_gpio.py:106>), [actions.py:35](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/actions.py:35>), [temperaturesensor.py:45](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/temperaturesensor.py:45>), [event_coordinator.py:84](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/event_coordinator.py:84>).

GPIO overrides the standard Digital Output callback. It logs a failed write, then always reads status, even for `Device not Attached`. The status read is unguarded; the probe demonstrates a `RuntimeError` escaping the callback. It also bypasses operation/value context and duplicate suppression.

Sensor action dispatch does not have the device-action dispatcher's exception boundary. Native temperature, humidity, digital-input and frequency callbacks can propagate state-publication failures. Delayed trigger execution is also unguarded. An enclosing Indigo/SDK host may catch some failures, but the plugin itself does not meet its no-unhandled-exception/no-Python-output requirement.

**Fix:** reuse the base async completion path for GPIO, return immediately on failure, and add concise contextual guards at actual callback/action/timer entry points. Failure to publish an error must not cause a second escaping exception. Test both hardware failure and Indigo publication failure; retain normal command semantics.

### 3. P1 — Several ordinary repeated workloads still cause error storms

[sgp41.py:272](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/sgp41.py:272>), [bme280.py:225](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/bme280.py:225>), [digitaloutput.py:23](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/digitaloutput.py:23>), [lcd.py:216](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/lcd.py:216>), [actions.py:29](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/actions.py:29>).

The recent limiter protects only a specific async `NOTATTACHED` result. Repeated Request Status failures, synchronous command failures (including Toggle's prerequisite read), and unexpected sensor poll failures still log every invocation. SGP41 polls at roughly one-second intervals: three simulated failed polls produced three error logs containing three tracebacks. Detached LCD requests warn for every queue replacement, so a frequently scheduled display action can flood warnings while correctly retaining only its latest request.

**Fix:** define a bounded fault policy by device, operation and failure category: report first occurrence, distinguish meaningful changes, use periodic summaries/escalation for continuing faults, and announce verified recovery. Preserve retries where appropriate; do not queue actuator commands as a side effect of logging changes. Do not suppress unrelated failures merely because the device already has another fault. Test sustained request/poll sequences, not just one failed callback.

### 4. P2 — Native attachment and successful initialization are conflated in reporting and retry logic

[phidget.py:116](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/phidget.py:116>), [phidget.py:467](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/phidget.py:467>), [phidget.py:636](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/phidget.py:636>), [plugin.py:577](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/plugin.py:577>).

Initialization failures set the wrapper to `detached`, but `isChannelDetached` returns false if the SDK is attached. Timed reporting and the scan then skip the device. The generic native wrapper has no initialization retry in that path; a retry requires another attachment callback or an explicit restart. The probe reproduces a wrapper left `detached`, omitted from the scan, with one configuration attempt and no timeout report afterward. Specialized I2C LCD retry behavior does not solve the generic native-channel case.

**Fix:** represent transport attachment, initialization failure and operational readiness separately. A detach scan can correctly omit physically attached hardware, but diagnostics must still expose initialization failure. Retry only clearly recoverable initialization failures with bounded delay; keep configuration errors actionable. Do not clear the saved outage or declare recovery before initialization succeeds.

### 5. P2 — Logical I2C peripherals can keep a healthy-looking retained reading during provider loss

[i2c_peripheral.py:51](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/i2c_peripheral.py:51>), [sgp41.py:281](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/sgp41.py:281>), [bme280.py:234](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/bme280.py:234>).

Provider loss cancels polling and changes internal state but does not publish an Indigo error/availability indication. Startup with an existing offline provider similarly returns in `starting` without marking the logical sensor unavailable. A probe verifies zero error-state publications in both cases. No poll is running to correct the display afterward. The manual scan intentionally skips objects without native-channel lifecycle locks, so it does not identify these logical peripherals either.

**Fix:** propagate provider unavailability to each dependent Indigo device, preserving last measurements with an explicit unavailable indication. Clear the indication after that peripheral's own successful initialization/read, not merely because its adapter reappears. Keep provider shutdown quiescence separate from an active outage so shutdown itself does not generate storms.

### 6. P2 — Explicit traceback logging still violates the repository requirement

Examples: [lcd.py:254](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/lcd.py:254>), [version_collection.py:257](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/version_collection.py:257>), [discovery_ui.py:869](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/discovery_ui.py:869>).

Nine explicit traceback-emission sites exist across six modules: LCD (three), version collection (two), SGP41, BME280, state publication, and discovery UI. They include `traceback.format_exc()` passed to logging and `exc_info=True`. This is established source behavior, not a hypothetical host issue. The SGP41 probe renders the traceback argument. Existing tests named “without traceback” mostly exercise selected `PhidgetException` branches, leaving generic exceptions outside that protection.

**Fix:** replace each site with a concise single-line error containing device/operation context, error class/code and useful explanation. Do not merely downgrade tracebacks to debug: the repository requirement covers Python-generated output. Assert rendered log messages and log records' exception data, not only the unformatted message template.

### 7. P2 — Async suppression lacks request/lifecycle epochs

[digitaloutput.py:64](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/digitaloutput.py:64>), [digitaloutput.py:102](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/digitaloutput.py:102>).

Request closures preserve text context but not submission epoch or completion validity. Every successful completion clears the entire detached-failure set. An earlier successful write finishing after a newer detached failure can therefore rearm duplicate logs even without attachment recovery. A late completion can also request a status read after the wrapper has stopped. The probe shows the same detached request logging twice when an intervening older success resets the set.

**Fix:** associate completions with lifecycle and request epochs; discard stopped/obsolete side effects and reset outage suppression on verified recovery. Add out-of-order completion tests spanning detach, stop, and reattach. This is a potential race; its occurrence in the reported power outage has not been established.

### 8. P2 — Server outage reminders follow a different persistence/cadence policy

[network_server.py:323](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/network_server.py:323>), [phidget.py:328](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/phidget.py:328>).

Native channels preserve outage records and switch to daily reminders after 24 hours. Network Server devices keep an in-memory outage start and always reschedule their configured reminder interval. Their elapsed time also uses seconds while channel reports use hours/minutes. A long server outage can consequently continue generating shorter-interval server errors even when channel messages have backed off, and restarting resets the server's outage duration.

**Fix:** explicitly choose and document one long-outage policy for servers, channels and logical devices, including persistence, elapsed formatting, startup grace, daily transition and recovery. Avoid assuming that a channel persistence fix also covered the server monitor. Add server-specific 24-hour and restart tests.

### 9. P2 — Identity/count rules remain inconsistent between summaries

[connection_identity.py:79](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/connection_identity.py:79>), [outage_coordinator.py:150](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/outage_coordinator.py:150>), [outage_coordinator.py:217](</Users/rdp/Documents/Codex/Phidgets22 plugin update/phidgets22-indigo-public/Phidgets22.indigoPlugin/Contents/Server Plugin/outage_coordinator.py:217>).

Per-device unavailable messages now separate hub ports, which fixes the confirmed RFID/LCD example. Server summaries still count unique serial numbers as “physical Phidgets,” collapsing multiple attached boards on one hub. Startup grouping also uses configured/cached server keys; an undiscovered wildcard server becomes `local` internally even when remote, while a named configuration gets its own group. Mixed “any” and named configurations can therefore split definitions for the same serial/port before discovery.

**Fix:** separate server endpoint identity, addressing/hub identity, attached-board identity, native channel identity and Indigo device identity. Use discovery-backed normalization where available; preserve uncertainty where unavailable rather than inventing a server match. Label counts according to the identity actually counted. Include hub-port and mixed-server-selection tests in both startup and server summaries.

## Other concerns requiring targeted validation

- `deviceStartComm` replaces the registry entry before starting a new wrapper and does not itself stop an existing wrapper. Indigo may guarantee stop-before-start in normal operation; test that integration contract and failure cleanup before claiming duplicate handles are impossible. This is not presented as a confirmed production leak.
- Outage files are written with `fsync` and atomically replaced while lifecycle locks are held. This avoids the earlier configuration-write loop, but disk failure repeatedly logs errors and a slow disk can delay callbacks. Measure and consider a separate bounded persistence path. Any change must preserve immediate crash-safe records and clean shutdown.
- Timer cancellation alone does not stop a callback that has already begun. Event and outage coordinators clear pending timers but do not have a terminal stopped flag preventing every late producer from scheduling new work. Confirm with deterministic shutdown interleavings.

## Test-suite review

Retain the valuable coverage already present: attach/detach grace, stale timer cancellation, repeated outage intervals, persisted deadlines, configuration-address changes, no device-property writes during persistence, async operation context, provider quiescence, and server reachability. There is no evidence justifying wholesale pruning; the suite is inexpensive to execute. No tests were removed or rewritten during this assessment.

The important omissions are behavior combinations: callback completion after stop, provider-down startup for logical sensors, failed async callback followed by a failed status read, unexpected poll/publication exceptions, repeated synchronous actions, old completion after a newer outage, and server reminders across restart/24 hours. Add these as meaningful regression scenarios when fixing the corresponding implementation.

Consolidate only where useful: standard and GPIO output completion should share behavioral contracts; tests of healthy output formatting can remain model-specific. Keep special transport-error and invalid-response tests because they protect distinct recovery decisions. Tests asserting warning/error calls should inspect rendered messages and recovery state, not only call count or a template string. Use barriers/manual clocks for races rather than wall-clock sleeps.

## Recommended implementation sequence

1. Fix lifecycle epoch handling and late-callback guards. Add focused regressions before changing logging volume.
2. Unify callback boundaries and fault reporting; adopt concise error normalization and a bounded first/report/reminder/recovery policy. Bring GPIO and synchronous actions under it.
3. Correct logical-peripheral availability and native initialization recovery. Preserve last data with explicit unavailable/error state.
4. Align server reminder policy and identity/count semantics; complete the report matrix for scans, timed reminders and recovery.
5. Run full automated checks, then staged live power-loss/startup/shutdown acceptance before a release. Keep actuator commands unqueued and validate actual door-output state after recovery.

Prefer small releases around these failure modes over a broad rewrite. The recent live regressions show why isolated passing tests must be supplemented by interleaving tests and physical acceptance. The current passing suite is a useful baseline, not evidence that the error-management requirement has been achieved.
