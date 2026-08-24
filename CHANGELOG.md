# Release notes

## 0.2.1.38 — 2026-08-24

### Added

- Add **Start or update LCD animation** and **Stop LCD animation** actions for
  text displays.
- Add Marquee mode, in which each display row scrolls its own message using a
  shared direction, gap, and interval.
- Add Flash mode, which alternates all display rows together between text sets
  A and B.
- Expose animation mode and running status as Indigo states.

### Reliability

- Starting an animation again atomically replaces the previous animation.
- Normal writes, clears, sleep, detach, and plugin shutdown cancel animation
  timers so competing operations cannot write to the same display.
- Guard animation timers with generation counters so stale callbacks cannot
  resume after replacement or cancellation.

### Testing

- Add regression coverage for independent-row marquee frames, synchronized
  flash frames, replacement, stale callbacks, stopping, action dispatch, and
  animation configuration validation.

## 0.2.1.37 — 2026-08-24

### Fixed

- Explicitly flush LCD writes and clears so text becomes visible on adapters
  such as the 1204 instead of remaining buffered after a successful SDK call.
- Make the **Write LCD text** action derive its fields from the selected
  device: one, two, or four rows for text LCDs and text/x/y fields for graphic
  LCDs.
- Remove the redundant separate multiline action.

### Testing

- Add regression coverage for explicit flushes and selected-device action
  field resolution.

## 0.2.1.36 — 2026-08-24

### Fixed

- Initialize configured text LCD panels after applying their screen size so
  adapters such as the 1204 can accept text writes.
- Add row-aware initial-text fields and a **Write LCD lines** action, including
  two explicit rows for 2-row panels and up to four for supported displays.

### Testing

- Add regression coverage for text-panel initialization and multi-line writes.

## 0.2.1.35 — 2026-08-24

### Added

- Add discovery and lifecycle support for Phidget22 `LCD` channels, including
  text LCD adapters and graphic LCDs.
- Add Indigo actions to write text, clear the display, set backlight and
  contrast, and sleep or wake supported displays.
- Add text-panel dimension configuration, fixed 5×8 text rendering, optional
  initial-text restoration after attachment, and LCD status states.

### Testing

- Add regression coverage for LCD discovery, configuration declarations,
  attachment setup, text restoration, coordinate validation, display actions,
  and hardware capability differences.

## 0.2.1.34 — 2026-08-24

### Fixed

- Report the Frequency Counter's session-cumulative `getCount()` value instead
  of the per-data-interval count supplied to the count-change callback.

### Testing

- Add regression coverage proving that fluctuating interval counts produce a
  monotonic cumulative Indigo `count` state.

## 0.2.1.33 — 2026-08-23

### Fixed

- Register the Frequency Counter count-change callback so the `count` and
  `timeChange` states receive updates.
- Use the declared `onOffState` as the Digital Input display state.
- Refresh Digital Output state after a successful initial attachment or
  reattachment.
- Correct the Temperature Sensor and Frequency Counter menu defaults.
- Correct misspelled event labels and Sprinkler On icon labels.
- Validate that the attachment timeout is a positive whole number when plugin
  preferences are saved.

### Testing

- Add regression coverage for the device-state callbacks, attachment refresh,
  XML defaults and labels, and attachment-timeout validation.

## 0.2.1.32 — 2026-08-22

- Initial public release of the updated Phidgets 22 plugin for Indigo.
