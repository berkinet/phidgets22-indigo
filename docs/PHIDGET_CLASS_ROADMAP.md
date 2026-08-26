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

The initial `LCD` support is complete. The remaining suggested sequence is:

1. `LightSensor`, `PressureSensor`, `SoundSensor`, and `PHSensor`:
   straightforward sensor-state devices.
2. `CapacitiveTouch`, `DistanceSensor`, `Encoder`, and `RFID`: event-oriented
   inputs.
3. `Accelerometer`, `Gyroscope`, `Magnetometer`, `Spatial`, and `GPS`:
   multi-state motion and location devices.
4. `RCServo`, `Stepper`, `DCMotor`, `BLDCMotor`, `MotorPositionController`, and
   `MotorVelocityController`: outputs requiring careful safety, limit, and
   action design.
5. `IR`, `LEDArray`, `PowerGuard`, and `Hub`: remaining
   specialized interfaces.

`CurrentInput`, `VoltageOutput`, and `ResistanceInput` are intentionally not
on the implementation roadmap at present. They remain in the inventory above
so the document continues to accurately describe the classes exposed by the
Phidget22 package.

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
