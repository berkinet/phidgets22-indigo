# Release notes

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
