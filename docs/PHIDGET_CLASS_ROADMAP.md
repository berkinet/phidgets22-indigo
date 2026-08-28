# Phidget class support roadmap

This inventory is based on the hardware/channel classes exposed by the locally
installed Phidget22 1.26 Python package. Recheck the package when Phidget22 is
upgraded because new channel classes may be added.

The plugin currently supports 9 of the 35 hardware/channel classes, leaving 26
possible additions.

| Phidget22 class | Plugin support |
| --- | --- |
| Accelerometer | Not supported |
| BLDCMotor | Not supported |
| CapacitiveTouch | Not supported |
| CurrentInput | Not supported |
| DCMotor | Not supported |
| DataAdapter | Supported as shared I2C transport |
| DigitalInput | Supported |
| DigitalOutput | Supported |
| DistanceSensor | Not supported |
| Encoder | Not supported |
| FrequencyCounter | Supported |
| GPS | Not supported |
| Gyroscope | Not supported |
| Hub | Not supported |
| HumiditySensor | Supported |
| IR | Not supported |
| LCD | Supported |
| LEDArray | Not supported |
| LightSensor | Not supported |
| Magnetometer | Not supported |
| MotorPositionController | Not supported |
| MotorVelocityController | Not supported |
| PHSensor | Not supported |
| PowerGuard | Not supported |
| PressureSensor | Not supported |
| RCServo | Not supported |
| RFID | Not supported |
| ResistanceInput | Not supported |
| SoundSensor | Not supported |
| Spatial | Not supported |
| Stepper | Not supported |
| TemperatureSensor | Supported |
| VoltageInput | Supported |
| VoltageOutput | Not supported |
| VoltageRatioInput | Supported |

## Infrastructure modules

These package modules are not counted as user-facing hardware classes:

- `Manager` — used by the plugin for discovery.
- `Log` — used for Phidget API logging.
- `Dictionary` — Phidget network key/value facility.
- `FirmwareUpgrade` — firmware-upgrade infrastructure.
- `Generic` — generic channel infrastructure.

## Suggested implementation order

The initial `LCD` support is complete. The remaining pre-1.0 hardware work is:

1. Add and hardware-test an I2C BME280 5 V barometric/environmental sensor
   profile on the ADP0001.
2. Add and hardware-test an I2C SGP41 air-quality sensor profile on the
   ADP0001.

After the 1.0 Store publication, the suggested sequence is:

1. Add access to GPIO 0 and GPIO 1 on the ADP0001 DataAdapter, as described
   below. This is an extension of the existing `DigitalInput` and
   `DigitalOutput` support rather than a new Phidget22 channel class.
2. `LightSensor`, `PressureSensor`, `SoundSensor`, and `PHSensor`:
   straightforward sensor-state devices.
3. `CapacitiveTouch`, `DistanceSensor`, `Encoder`, and `RFID`: event-oriented
   inputs.
4. `Accelerometer`, `Gyroscope`, `Magnetometer`, `Spatial`, and `GPS`:
   multi-state motion and location devices.
5. `RCServo`, `Stepper`, `DCMotor`, `BLDCMotor`, `MotorPositionController`, and
   `MotorVelocityController`: outputs requiring careful safety, limit, and
   action design.
6. `IR`, `LEDArray`, `PowerGuard`, and `Hub`: remaining
   specialized interfaces.

`CurrentInput`, `VoltageOutput`, and `ResistanceInput` are intentionally not
on the implementation roadmap at present. They remain in the inventory above
so the document continues to accurately describe the classes exposed by the
Phidget22 package.

## ADP0001 I2C environmental sensors required before 1.0

The ordered SGP41 and 5 V BME280 boards are the remaining planned hardware
profiles before the first public Store release. Confirm each board's exact
identity, address options, electrical requirements, and observed responses on
arrival rather than assuming that all breakout boards use the same design.

- BME280: expose temperature, relative humidity, and barometric pressure as
  Indigo states, with a configurable polling interval and actionable address
  validation.
- SGP41: expose the supported VOC/NOx measurements. Decide from the actual
  board and tested driver whether the first profile publishes raw signals,
  processed gas indices, or both, and how temperature/humidity compensation is
  supplied.
- Both profiles must share an ADP0001 with existing I2C displays and sensors,
  reject address collisions, recover after adapter/server detach, and avoid
  blocking Indigo while measurements are pending.

## ADP0001 GPIO 0 and GPIO 1

Expose the two GPIO pins on the ADP0001 DataAdapter while preserving its
existing role as the shared I2C transport. Each pin may be configured as a
digital input or a digital output, but never both at the same time.

### Planned configuration and behavior

- Present GPIO 0 and GPIO 1 as functions belonging to the selected ADP0001,
  without taking ownership of or disrupting its DataAdapter/I2C channel.
- Input mode supports floating or pull-up operation. Pull-up is the recommended
  default for a dry-contact switch wired between GPIO and GND.
- Input mode provides configurable state inversion, so a grounded/closed switch
  can be presented to Indigo as `on`, and a configurable debounce interval for
  momentary buttons and mechanical contacts.
- Output mode provides on, off, and toggle actions and publishes the current
  logical state.
- Configuration help must state that a GPIO pin is a logic signal, not a load
  driver. Its voltage follows the adapter's selected supply voltage and its
  current and series-resistance limits must be respected; relays, lamps, and
  similar loads require suitable driver hardware.

### First acceptance scenario

Connect `GND -> momentary push button -> GPIO`, configure the input with its
pull-up enabled, and use the Indigo state change to control an LCD backlight.
Verify both pins, input and output mode changes, debounce and inversion,
attach/detach and plugin restart behavior, and concurrent GPIO activity while
both I2C LCD traffic and the DataAdapter remain operational.

## LCD implementation notes

The shared ADP0001 DataAdapter foundation and future compatibility with
character displays connected through it are documented separately in
[`I2C_LCD_COMPATIBILITY_DESIGN.md`](I2C_LCD_COMPATIBILITY_DESIGN.md). That work
requires real-hardware verification before a display profile is released.

Phidget22 exposes both text and graphic displays through the `LCD` channel
class. The initial implementation supports the useful common subset while
detecting the attached channel's capabilities rather than assuming one model.

### Initial device configuration

- Standard server/device/hub-port/channel discovery fields.
- Screen size selection for text LCD adapters. These adapters cannot detect
  the attached panel dimensions, so the selected size must be applied before
  text is written. The attached panel is then initialized.
- Initial backlight and contrast values.
- Complete frames are explicitly flushed so multi-row writes and animation
  changes become visible together.
- Optional row-aware initial text to restore when the channel attaches.

### Initial Indigo states

- Attachment/status information supplied by the shared wrapper.
- `backlight`, `contrast`, `screenWidth`, `screenHeight`, and `sleeping` where
  the attached hardware exposes them.
- `lastText` as the last text successfully requested through the plugin. This
  is plugin state, not a readback of the pixels currently on the display.
- `animationMode` and `animationRunning` for text-display animations.

### Initial Indigo actions

- Set static or animated display content, backlight, and contrast in one
  device-aware action. Static content uses one to four complete rows on a text
  LCD, or text at an x/y pixel position on a graphic LCD.
- Clear the display.
- Sleep or wake the display when supported.
- Start/update or stop a text-display animation. Marquee can scroll each row
  independently or treat all rows as one row-major virtual line; Flash
  alternates every row together between two text sets.

Action values are checked against the attached display dimensions and reported
min/max ranges. The wrapper refreshes its states after attachment and after
successful actions.

### Deferred LCD features

- Graphic primitives (`drawPixel`, `drawLine`, and `drawRect`).
- Bitmap upload and custom character bitmaps.
- Multiple frame buffers, copying, and saved frame buffers.
- Cursor and cursor-blink controls specific to text displays.
- User-selectable fonts and font sizing.

These can be added without changing the initial device type because the
wrapper will already distinguish text and graphic LCD subclasses.

## Work required for each class

Adding a class normally requires coordinated changes to:

1. `CHANNEL_CLASSES_BY_DEVICE_TYPE` in `discovery.py`.
2. The Indigo device declaration and configuration UI in `Devices.xml`.
3. A channel wrapper implementing attachment configuration, event handlers,
   Indigo states, and actions where appropriate.
4. A focused builder registered in `device_factory.py`; `plugin.py` retains
   only the shared start/stop lifecycle around the constructed wrapper.
5. Focused regression tests for discovery, state updates, and actions.
