# I2C text LCD compatibility design

## Status

The first complete adapter-backed display profile is implemented in version
0.3.7. `LCDPhidget` is the common
plugin-level contract, and `NativeLCDPhidget` is the concrete implementation
selected for existing native LCD devices. `DataAdapterPhidget` now owns and
configures a physical ADP0001 DataAdapter channel as a shared I2C bus. Display
The initial verified target is a Freenove LCD2004 with PCF8574T backpack at
address `0x27`, using a configured ADP0001 at 5 V and 100 kHz.

Version 0.3.6 added provider awareness. DataAdapter devices advertise readable
available functions, initially `LCD display transport`, and the LCD layer can
combine native channels and configured capable adapters into one internal
provider inventory. The adapter-backed choice is not shown in the LCD pane
until at least one controller profile can render through it. Version 0.3.7
activates that selector and retains the native Phidget LCD path as another
provider in the same list.

## Motivation

Phidgets identifies the 1204 PhidgetTextLCD Adapter as not recommended for new
designs and has stated that its text-LCD products will eventually be
discontinued. Phidgets recommends the LCD1100 graphic display for new native
LCD applications and currently has no plan for a VINT text-LCD adapter. The
ADP0001 I2C Adapter and related data adapters provide a possible supported
transport for third-party displays.

The plugin should retain the existing 1204 compatibility path and native
Phidget22 `LCD` support for the LCD1100. A future I2C text-display path should
reuse the existing Indigo LCD device and action contract so users do not need
to recreate Action Groups or learn a parallel display API.

## Compatibility objective

Keep existing callers unchanged:

```python
lcd.clear()
lcd.writeLines(lines)
lcd.setBacklight(value)
lcd.setContrast(value)
lcd.startAnimation(...)
lcd.stopAnimation()
lcd.setSleeping(value)
```

`LCDPhidget` remains the plugin-level compatibility contract. An I2C display
implementation should extend that contract, even though the attached display
is not a native Phidget22 `LCD` channel. It remains Phidgets-connected through
the Phidget22 `DataAdapter` used by the ADP0001.

This compatibility layer must not be documented as making an I2C peripheral a
native Phidget22 LCD. It only makes both transports implement the same plugin
interface.

## Proposed structure

```text
LCDPhidget (existing plugin contract and shared display behavior)
├── NativeLCDPhidget
│   └── Phidget22.Devices.LCD
│       ├── 1204 legacy text adapter
│       └── LCD1100 graphic display
DataAdapterPhidget
└── Phidget22.Devices.DataAdapter (one open physical channel)
    ├── I2CLCDPhidget (future logical child)
    ├── I2CTemperaturePhidget (possible future logical child)
    └── other addressed I2C peripheral profiles
```

The exact class names may change, but these constraints should not:

1. Existing Indigo actions continue targeting the common `LCDPhidget`
   contract.
2. Existing native LCD behavior remains the default implementation.
3. Shared substitution, overflow handling, animation scheduling, locking,
   cancellation, and Indigo states remain above the transport boundary.
4. Hardware calls move behind small overridable hooks only where required.
5. The device factory selects the concrete implementation from saved device
   configuration; callers do not branch on the transport.

Version 0.3.2 establishes this inheritance and construction boundary without
changing the existing device type or saved properties. The native subclass
supplies a `Phidget22.Devices.LCD` channel to the common contract. The I2C
subclass and its transport hooks will be added after the ADP0001 and display
profile can be exercised on real hardware.

Likely hardware hooks include:

- Initialize the attached display.
- Clear display memory.
- Write one complete row or frame.
- Flush buffered output when the transport supports buffering.
- Read or set dimensions.
- Set backlight, contrast, sleep, and cursor modes when supported.
- Create custom characters when supported.

## Indigo configuration model

The user-facing LCD workflow uses one display selector. It searches native LCD
channels first, then configured adapters that advertise the `lcd` function,
and combines both results without asking the user to choose a transport.
Internally, I2C configuration still uses two Indigo devices so one physical
bus can safely serve more than one peripheral:

```text
Create I2C Data Adapter
  → Select server and ADP0001 DataAdapter channel
  → Configure voltage and frequency
Create LCD
  → Select a friendly available display
  → Plugin retains the native channel or adapter/profile reference internally
```

The adapter device exclusively owns the Phidget22 channel and serializes all
transactions. Logical peripherals reference it by Indigo device ID. The
ADP0001's DigitalInput and DigitalOutput channels continue to use the existing
device types and are created only when the user wants them.

The I2C peripheral generally cannot identify its display type, dimensions, or
backpack wiring. Discovery therefore ends at the DataAdapter. Probing common
addresses such as `0x27` and `0x3F` may establish that a device acknowledges,
but cannot prove that it is a compatible LCD backpack.

## Capability differences

The common contract must expose capabilities rather than imply that every
display supports every control:

- Character rows versus pixel graphics.
- Variable, binary, or unavailable backlight control.
- Software-controlled or mechanical-only contrast.
- Native, emulated, or unavailable sleep/wake.
- Buffered versus immediate writes.
- Custom-character support.

The Indigo configuration and Action windows should reveal only meaningful
controls. Unsupported operations should either use an explicitly documented
emulation or produce a clear validation/runtime error.

## Initial I2C target

The first target is the Freenove LCD2004: an HD44780-compatible 20×4 character
LCD connected through a PCF8574T backpack. Its verified profile is fixed at
address `0x27` with `RS=P0`, `RW=P1`, `E=P2`, backlight `P3`, and data
`D4–D7=P4–P7`. The implementation provides:

- Four-bit HD44780 initialization and command timing.
- PCF8574 bit mapping for `RS`, `E`, backlight, and data lines.
- DDRAM row-address mapping for each supported screen geometry.
- Clear, cursor positioning, text writes, and optional custom glyphs.
- Configurable or preset backpack wiring because mappings are not universal.
- Appropriate DataAdapter voltage, frequency, I2C address, and transaction
  behavior.

This profile does not claim compatibility with every product sold as
`LiquidCrystal_I2C`.

## Testing requirements

Create a shared LCD contract suite that runs against native and I2C test
doubles. It should cover:

- Static writes, clipping, and complete-frame behavior.
- Variable and device-state substitution.
- Static overflow policies.
- Independent-row, Virtual, and Flash animations.
- Replacement and cancellation of active animations.
- Backlight and sleep/wake semantics.
- Indigo state publication.
- Attachment, detachment, restart, and shutdown.

Transport tests should separately verify native LCD method calls and exact I2C
byte/command sequences. Real-hardware acceptance testing is required before an
I2C profile is released.

## Implementation sequence

1. **Complete in 0.3.3:** add the shared ADP0001 DataAdapter device, discovery,
   bus configuration, locking, validation, and transaction boundary.
2. **Complete in 0.3.7:** inventory the ADP0001 and display/backpack model,
   address, voltage, and pin
   mapping.
3. **Complete in 0.3.7:** implement the initialization and exact PCF8574T
   transaction sequence behind the existing LCD contract.
4. **Complete in 0.3.7:** activate unified provider selection and retain saved
   native configuration compatibility.
5. **Complete in 0.3.7:** add native regression, I2C sequence, discovery,
   configuration, startup-order, and profile tests.
6. Validate the full Indigo action set on hardware.

## Non-goals for the first implementation

- Replacing or removing 1204 support.
- Reimplementing the LCD1100 native graphic path over I2C.
- Automatic identification of arbitrary I2C displays.
- Universal support for every PCF8574 backpack mapping.
- Changing existing Indigo LCD Action Group identifiers or semantics.
