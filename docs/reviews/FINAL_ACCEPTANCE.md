# Error-management hardening acceptance

Implementation stages 1–5 completed on 14 October 2026, following the two reviews.
Final planned release: **2026.1.44**. Preceding stage releases: 2026.1.40–43.
Install only the final cumulative release; no need to install each intermediate.

## Automated evidence

- Full suite: 453 tests pass. Runtime syntax, XML and version consistency checked.
- Focused modules are also run in independent processes to detect fixture/order
  dependencies. The test suite retains existing algorithm, transport, grace,
  persistence, and configuration regression coverage.
- New coverage includes stop/detach during initialization, stale write callbacks,
  duplicate attach callbacks, repeated fault reporting and recovery, no explicit
  traceback emission, GPIO failed-write handling, poll continuation after Indigo
  publication failures, initialization retry limits/cancellation, provider-down
  startup, restored server deadlines, formula arity, units, identity compatibility,
  outage cleanup, catalog TTL, and partial LCD transfer resynchronization.
- The validator source-line-count/attribute-existence test was replaced by a
  malformed configuration behavior test. Repeated-error expectations and fake
  sensor states were updated to match the deliberate reporting/lifecycle changes.
- No real actuator commands were issued, no live server was stopped/restarted,
  and no real hardware outage/recovery was simulated by these tests.

## Live acceptance to perform on Indigo

1. With a Network Server stopped, restart the plugin. Verify immediate Offline
   on the server device and channel errors after startup grace, with retained
   measurements clearly unavailable. Logical peripherals must show provider
   unavailability, not a healthy stale reading.
2. Restore the server. Confirm each channel/peripheral initializes and updates,
   clears its error, and reports recovery. LCD attachment action groups should
   run once per valid attachment, not after stop or an invalidated initialization.
3. During a sustained outage, repeat status and Turn Off requests for test outputs.
   Verify first/distinct failures remain visible, identical repeats are bounded,
   and outage reminders continue. Confirm failed output commands are not replayed
   when attachment returns. Use a safe disconnected/test output for this check.
4. Restart during that outage. Confirm elapsed time and next reminder survive,
   while the startup error indication is not delayed until the reminder deadline.
   Verify the first daily message and daily cadence after 24 hours.
5. Stop/reload during active display/sensor work. Confirm shutdown completes;
   no attachment actions, new polls, or healthy-state publications occur afterward.
6. On 16x2/20x4 I2C displays, confirm updated cells and cleared text render correctly
   without routine full-screen clear/flicker. After disconnect/reconnect, verify a
   full resynchronization and current/latest display request.
7. Verify a Fahrenheit trigger of 9°F configures a 5°C change threshold, and invalid
   formulas/configuration values are rejected before hardware sampling.

## Deliberately retained behavior and limits

The first sensor initialization/read remains synchronous for metadata/state
correctness. HD44780 byte/ROM behavior remains unchanged apart from frame updates;
ROM-dependent Unicode conversion is not claimed. Outage files remain atomic and
fsynced; callbacks can still be delayed by a genuinely slow filesystem. Generic
boundary guards contain failures, while each poll/monitor explicitly owns retries.
Fault reporting is bounded in memory and uses first/reminder/recovery behavior;
there are no Python tracebacks in Indigo at any logging level.

Native initialization retries are limited to five increasing-delay attempts for
recognized transient failures. If exhausted, the message asks for correction and
an Indigo-device restart; a genuine later detach/attach begins a fresh lifecycle.
Hardware-dependent acceptance is pending, not implied by passing unit tests.
