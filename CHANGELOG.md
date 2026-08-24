# Release notes

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
