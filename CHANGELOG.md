# Release notes

## 0.3.21 — 2026-08-28

### Changed

- Replace the dither-shaded donut prototype with a larger black-and-white
  wireframe torus whose rear segments are suppressed by depth testing.
- Reduce angular movement per frame and remove surface dithering to improve
  shape recognition and motion clarity on the LCD1100.

## 0.3.20 — 2026-08-28

### Added

- Add a depth-buffered, dither-shaded spinning donut prototype for graphic
  LCDs, with a configurable frame interval for LCD1100 performance testing.
- Integrate the prototype with the existing display action and animation
  lifecycle so replacement, stop, detach, and shutdown cancel it cleanly.

## 0.3.19 — 2026-08-28

- Fix GPIO child-device validation when Indigo supplies distinct proxy objects
  for the same selected I2C adapter during lookup and device iteration.
- Compare adapter IDs instead of Python object identity, allowing the selected
  adapter ID and observed GPIO path to be saved reliably.

## 0.3.18 — 2026-08-28

### Added

- Add separate **I2C Adapter GPIO Input** and **I2C Adapter GPIO Output**
  Indigo devices for GPIO 0 and GPIO 1 on a selected ADP0001.
- Support floating or pull-up inputs, optional state inversion, and configurable
  software debounce; defaults suit a momentary switch wired from GPIO to GND.
- Expose GPIO outputs as Indigo relays with On, Off, Toggle, and status actions.
- Reject duplicate assignment of one adapter pin across GPIO input and output
  devices and document the ADP0001 output's electrical limits.

## 0.3.17 — 2026-08-28

### Changed

- Defer transient `device is in use` errors during the initial attachment
  timeout so routine plugin replacement can recover without flooding Indigo's
  event log.
- Group persistent startup-contention errors by server and physical Phidget and
  report the affected Indigo devices and channels with actionable ownership
  guidance.
- Continue reporting ownership errors immediately after the startup window, and
  set persistent startup failures to the explicit `Channel in use` error state.

## 0.3.16 — 2026-08-28

### Fixed

- Hide native graphic-LCD text and formula controls in **Set LCD display**
  actions for character LCDs, preventing a configured 16×2 display from
  incorrectly showing the LCD1100's eight text rows.

## 0.3.15 — 2026-08-28

### Added

- Add Text page and Formula graph content modes for native graphic LCDs.
- Plot a restricted mathematical expression at all 128 horizontal samples with
  explicit X/Y ranges, optional axes, and connected-line or pixel rendering.
- Validate formulas without unrestricted Python evaluation and break plots at
  invalid, non-finite, out-of-range, or likely discontinuous samples.

## 0.3.14 — 2026-08-28

### Added

- Offer the LCD1100's three built-in fonts: 5×8, 6×10, and 6×12.
- Render complete graphic-LCD text pages with the corresponding 8, 6, or 5
  top-aligned lines and one atomic flush.

### Changed

- Preserve previously saved single-line X/Y graphic text actions while using
  the new font-aware multi-line editor for newly configured actions.

## 0.3.13 — 2026-08-28

### Added

- Probe configured I2C LCD addresses with a read-only transaction while saving
  the device and show an inline configuration error when no device responds.

### Fixed

- Replace raw Phidget NACK tracebacks during I2C LCD initialization with an
  actionable message covering the configured address, jumpers, power, and
  wiring.

## 0.3.12 — 2026-08-27

### Changed

- Replace the ambiguous Stop LCD animation behavior with **Stop and turn off
  LCD**, which cancels animation, clears the panel, and sets its backlight to
  the hardware minimum.

## 0.3.11 — 2026-08-27

### Fixed

- Stop adapter-backed LCD animation timers before Indigo closes their shared
  DataAdapter, preventing a spurious write-error traceback during plugin
  shutdown.

## 0.3.10 — 2026-08-27

### Fixed

- Persist cleared LCD action text fields as explicit empty values so stale
  lines from an earlier action configuration cannot remain in Indigo device
  state or continue scrolling on the display.

## 0.3.9 — 2026-08-27

### Added

- Generalize the fixed Freenove LCD2004 implementation into one configurable
  HD44780/PCF8574-compatible display family.
- Add selectable 16×2 and 20×4 geometries so the integrated-expander Freenove
  LCD1602 and backpack-based LCD2004 share the same driver and wiring preset.
- Add an editable 7-bit I2C address and a Custom / advanced wiring option for
  RS, RW, Enable, backlight, D4–D7, and backlight polarity.
- Prevent enabled LCD devices from claiming the same address on one adapter.

### Changed

- Migrate the original `freenove-lcd2004-pcf8574t` saved profile to the generic
  Freenove wiring preset without changing existing 20×4 behavior.
- Present adapter-backed displays as I2C character LCDs rather than assuming
  that every selected adapter owns an LCD2004.

### Testing

- Verify both 16×2 and 20×4 DDRAM layouts, configurable addresses, custom
  expander pin mappings, legacy defaults, and the existing LCD action contract.

## 0.3.8 — 2026-08-27

### Fixed

- Wait for the selected shared DataAdapter to become fully attached before
  initializing an adapter-backed LCD. Indigo may start the logical LCD after
  creating the adapter wrapper but before its physical channel attachment has
  completed.
- Complete the deferred logical LCD attachment as soon as the adapter reports
  ready, and use the same path to reinitialize the controller after adapter
  reattachment.

### Testing

- Reproduce the real startup ordering where the LCD starts against an adapter
  in `starting` state, confirm that no premature I2C transaction occurs, then
  confirm initialization completes after the adapter reaches `attached`.

## 0.3.7 — 2026-08-27

### Added

- Add the first operational adapter-backed display profile: Freenove LCD2004,
  20×4 HD44780-compatible controller, PCF8574T backpack, address `0x27`, and
  the documented Freenove P0–P7 mapping.
- Replace transport-specific LCD discovery controls with one **Available
  display** selector populated by native Phidget LCDs and supported displays
  behind configured adapters.
- Implement four-bit controller initialization, exact 20×4 DDRAM row mapping,
  complete-frame writes, binary backlight, display sleep/wake, and all existing
  static, marquee, Virtual marquee, and Flash actions through the shared
  adapter transaction lock.
- Persist only the selected provider/profile reference while retaining the
  existing native LCD properties and Action identifiers.
- Start dependent displays regardless of Indigo device startup order and
  reinitialize them after their shared adapter reattaches.

### Notes

- Contrast on this display is adjusted with the backpack potentiometer. Saved
  contrast values remain compatible with existing actions but have no physical
  effect on this profile.
- Real-hardware validation is required after installation of this release.

### Testing

- Add byte-level PCF8574T initialization, address, pin mapping, row-address,
  frame, backlight, sleep, unified selection, profile, and factory coverage.
- Run the complete native LCD regression suite unchanged.

## 0.3.6 — 2026-08-26

### Added

- Advertise each configured DataAdapter's available logical functions through
  the `availableFunctions` Indigo state, initially including LCD display
  transport.
- Add a transport-neutral display-provider inventory that searches native
  Phidget LCD channels and configured LCD-capable adapters and returns one
  friendly list without exposing native versus I2C implementation choices.
- Add an LCD contract resolver that obtains the already-open shared adapter
  from the plugin rather than reopening its physical DataAdapter channel.
- Add the future `getAvailableDisplayMenu` callback. It remains intentionally
  absent from the LCD pane until a tested controller profile can make an
  adapter-backed selection operational.

### Testing

- Cover adapter capability advertisement, unified native/adapter inventory,
  friendly provider names, filtering, and shared-provider resolution.

## 0.3.5 — 2026-08-26

### Fixed

- Remove the misleading manual-configuration instruction from missing-model
  notices because the discovery address fields are read-only.
- Reject Save for a new device when no compatible channel is available or
  selected, while continuing to permit edits to an already configured device
  that is temporarily offline and retains its saved address.

### Testing

- Cover new-device rejection, offline configured-device preservation, and the
  corrected I2C Data Adapter notice.

## 0.3.4 — 2026-08-26

### Fixed

- Render the model-specific missing-device notice as a visible field inside
  every device configuration pane. Indigo does not display `showAlertText`
  returned while initially loading device configuration values, so the 0.3.3
  alert was calculated but never shown.
- Keep the notice synchronized with the discovery inventory and hide it as
  soon as at least one compatible channel is available.

### Testing

- Confirm a missing model sets the shared visibility binding and that the I2C
  Data Adapter pane contains the correct model-specific notice.

## 0.3.3 — 2026-08-26

### Added

- Add the ADP0001 as an **I2C Data Adapter** Indigo device, including standard
  local/remote/VINT discovery, selectable bus voltage, and 10, 100, or 400 kHz
  I2C frequency.
- Add a locked, validated DataAdapter transaction interface that future LCD,
  temperature, humidity, and other logical peripheral devices can share
  without opening the physical channel more than once.
- Publish configured voltage, frequency, and packet-size capabilities as
  Indigo states after attachment.
- Show a model-specific alert when no compatible channel was automatically
  discovered instead of opening a configuration pane without an explanation.

### Testing

- Add adapter configuration, transaction, validation, factory, discovery, XML,
  and missing-model alert coverage. Real ADP0001 hardware verification remains
  required before adding an I2C peripheral profile.

## 0.3.2 — 2026-08-26

### Changed

- Establish `LCDPhidget` as the common plugin-level display contract for all
  Phidgets-connected LCD transports.
- Add `NativeLCDPhidget` as the concrete implementation backed by
  `Phidget22.Devices.LCD`, and make the device factory select it for every
  existing LCD device without changing Indigo actions, states, or saved
  configuration.
- Require future display subclasses to provide their concrete Phidget22
  channel, creating the construction seam needed by an I2C `DataAdapter`
  implementation.

### Testing

- Add inheritance and factory coverage for the common/native LCD boundary.
- Confirm all existing native text and graphic LCD behavior remains unchanged.

## 0.3.1 — 2026-08-25

### Fixed

- Queue an LCD display action that arrives before its remote LCD channel has
  attached, instead of raising an Indigo plugin-execution error during plugin
  reloads, upgrades, server restarts, or brief network outages.
- Retain only the newest detached display request and apply it once immediately
  after the LCD attaches, preventing stale display updates from being replayed.

### Testing

- Add regression coverage for immediate attached display requests and
  latest-request replacement and replay while detached.

## 0.3.0 — 2026-08-25

### Changed

- Adopt the three-part version scheme required by the Indigo Plugin Store.
- Preserve `com.yikes.eric.phidgets-indigo` as the permanent plugin identity so
  existing Indigo devices and actions remain associated with the plugin.
- Prepare the first published GitHub release for Indigo Plugin Store
  distribution.

## 0.2.1.49 — 2026-08-24

### Added

- Reveal a **Static overflow behavior** menu only when a static text-LCD line
  contains a recognized Indigo variable or device-state substitution token.
- Offer **Truncate**, **Marquee if needed**, and **Reject if too long** policies
  after the substituted value is compared with the attached LCD row width.
- Reveal direction, repeat-gap, and interval controls only when **Marquee if
  needed** is selected. Short substituted values remain static.

### Testing

- Add UI callback coverage for conditional overflow controls and runtime
  coverage for post-substitution marquee conversion and explicit rejection.

## 0.2.1.48 — 2026-08-24

### Added

- Document Indigo Variable and Device State Substitution directly in the Set
  LCD display Action window, including `%%v:12345%%` variable and
  `%%d:12345:someStateId%%` device-state examples.
- Confirm substitution across the LCD action's static, marquee, Virtual
  marquee, Flash, and graphic text fields before rendering.

### Testing

- Add action-dispatch coverage proving that Indigo device-state substitution
  syntax is resolved before Virtual marquee text reaches the LCD wrapper.

## 0.2.1.47 — 2026-08-24

### Fixed

- Explicitly disable the text controller's persistent cursor and cursor-blink
  modes so cursor columns cannot appear among moving marquee text.
- Treat every Set LCD display action as a wake operation before applying its
  requested backlight, so a prior emulated Sleep cannot suppress brightness.
- Repeat Virtual single-line marquee text after exactly the configured gap,
  rather than adding another full 40-character display-capacity gap between
  passages on a 2×20 LCD.
- Reject multiline Virtual marquee text in the action editor and safely turn
  legacy embedded newlines into spaces before display, preventing control-code
  glyphs from appearing as vertical bars.
- Show `∅ empty`, a right-arrow plus the stored character count, or a multiline
  warning directly below the Virtual marquee text field so hidden content is
  visible even when the single-line editor looks empty or truncated.

### Testing

- Add coverage for Set display waking an emulated sleeping LCD, continuous
  40-cell Virtual marquee repetition with an exact configured gap, rejecting
  embedded newlines, and reporting hidden text content in the action editor.

## 0.2.1.46 — 2026-08-24

### Fixed

- Make **Put LCD to sleep** and **Wake LCD** work on text LCD adapters that do
  not implement native Phidget sleep/wake control. Sleep now turns the
  backlight down to its supported minimum, and Wake restores its prior level.
- Keep a backlight value selected while the emulated sleep is active as the
  level to restore on Wake, without prematurely illuminating the display.
- Publish the emulated sleeping state to Indigo so action groups complete
  normally and device state remains accurate.

### Testing

- Add regression coverage for emulated sleep, changing the desired backlight
  while asleep, wake restoration, and Indigo sleeping-state updates.

## 0.2.1.45 — 2026-08-24

### Fixed

- Clear the LCD's buffered frame before writing each Marquee, Virtual
  single-line marquee, or Flash frame. This positively erases separator and
  padding cells instead of relying on trailing spaces to replace old glyphs,
  preventing vertical remnants from appearing between marquee repeats.
- Continue to flush only after every physical row has been written, keeping
  each cleared and redrawn frame visually atomic.

### Testing

- Add regression coverage proving that every virtual-marquee frame is cleared,
  fully written, and then flushed in that order.

## 0.2.1.44 — 2026-08-24

### Fixed

- Resolve custom LCD action targets from Indigo's authoritative
  `pluginAction.deviceId` instead of assuming the optional callback device
  argument is populated. This fixes **Put LCD to sleep** from an Action Group,
  where Indigo passed `device=None`.
- Apply the same target resolution to Clear, Wake, Set display, and Stop
  animation so all LCD custom actions behave consistently.
- Retain the callback device as a compatibility fallback and report a clear
  error when an action has no target or its LCD is inactive.

### Testing

- Add regression coverage for executing LCD Sleep with `device=None` and a
  valid action `deviceId`.

## 0.2.1.43 — 2026-08-24

### Changed

- Refactor the main plugin module into focused components without changing the
  Indigo-facing callbacks:
  - `device_factory.py` constructs every supported Phidget wrapper from saved
    device properties.
  - `actions.py` owns native and LCD action dispatch plus action UI validation.
  - `discovery_ui.py` owns preferences, discovery menus, device configuration,
    address derivation, and discovery diagnostics.
- Keep startup, active-device lifecycle, trigger coordination, server-outage
  batching, and shutdown in the now substantially smaller `plugin.py`.
- Use a per-device builder registry so adding another Phidget class no longer
  requires extending a large construction branch in `plugin.py`.

### Testing

- Add structural regression coverage for mixin ownership, every registered
  device builder, shared channel addressing, and unknown device types.
- Run the complete existing behavior suite against the refactored module
  boundaries.

## 0.2.1.42 — 2026-08-24

### Added

- Add **Virtual single-line marquee** to the LCD display action. It exposes one
  text field and treats every physical row as one row-major virtual line (40
  characters on a 2×20 display).
- Keep the existing direction, interval, and repeat-gap controls. Left-moving
  text enters at the lower-right cell and travels toward the upper-left;
  right-moving text enters at the upper-left and travels toward the
  lower-right.
- Preserve the existing independent-row Marquee as a separate display mode.

### Testing

- Add regression coverage for both virtual-marquee directions, entry points,
  row-boundary wrapping, action layout, validation, and dispatch.

## 0.2.1.41 — 2026-08-24

### Fixed

- Clip overlong Static and Flash text to the physical display-row width
  instead of aborting the Indigo action.
- Log one warning for each clipped row, including the original and displayed
  text. Flash warnings occur when the animation starts, not on every frame.
- Add an action-dialog note explaining the clipping behavior. Marquee text
  remains unbounded because it scrolls through the complete message.

### Testing

- Add regression coverage for overlong Static content and both Flash frames.

## 0.2.1.40 — 2026-08-24

### Fixed

- Replace unsupported `setdefault()` calls in the action configuration
  callback with Indigo-compatible mapping operations.
- Restore the device-aware Static text fields that could not render after the
  callback exception.

### Testing

- Add regression coverage using an Indigo-like `Dict` without `setdefault()`
  and verify that a 2-row Static layout exposes both text fields.

## 0.2.1.39 — 2026-08-24

### Changed

- Consolidate Static, Marquee, and Flash content into one **Set LCD display**
  action.
- Move backlight and contrast into **Set LCD display**, initialized from the
  selected device's current values.
- Remove the separate **Write LCD text**, **Set LCD backlight**, and
  **Set LCD contrast** actions.
- Keep **Stop LCD animation** as a separate immediate action.

### Testing

- Update action declaration, device-aware layout, validation, and dispatch
  coverage for the consolidated display action.

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
