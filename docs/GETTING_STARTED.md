# Getting started

## Configure the plugin

Use Indigo 2025.2 or newer with its Python 3.13 runtime. Then:

1. Install the official Phidget22 package for Indigo's Python:

   ```bash
   "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13" \
     -m pip install --upgrade phidget22
   ```

2. Install and enable **Phidgets 22** in Indigo.
3. Open **Plugins → Phidgets 22 → Configure**. The defaults are suitable for
   most installations; normally you can simply click **Save**.

The Phidget Network Server must be enabled on every computer or Phidget SBC
whose devices you want Indigo to discover.

## Create a device

1. In Indigo, create a new device and select **Phidgets 22** as its type.
2. Select the required model, such as **Digital Input**, **Temperature Sensor**,
   or **Voltage Input**.
3. Click **Edit Device Settings**.
4. Select the discovered server, Phidget, and—when applicable—VINT port,
   function, and channel. Levels with only one valid choice are selected
   automatically.
5. Review any model-specific settings, then click **Save**.

The **Phidgets path** shows the observed route to an existing device after it
has connected.

## Monitor a Phidget Network Server

Create a **Phidget Network Server** device and select a discovered or previously
configured server. Offline servers remain selectable when another Indigo
Phidget device already references them. This device is read-only: it does not
reboot, configure, or otherwise control the server.

The Indigo device remains present while the server is offline. Its states
report attachment, advertised name, service and server types, address, host,
port, authentication requirement, flags, last attachment and detachment times,
last outage duration, and reconnect count. The standard Phidget attached and
detached triggers can target the server device.

After a two-second discovery-loss grace period, the plugin reports one warning
and fires the detached trigger. If the server remains unavailable through the
configured attachment timeout, the plugin escalates the condition to an error
and repeats it at the configured detached-device reminder interval. Recovery
produces one informational message with the total outage duration.

The **Phidget device detached** trigger has an optional **Must remain detached**
delay. Device status changes immediately, but the plugin executes that trigger
only if the device remains detached for the configured number of seconds. A
reattachment before expiry cancels the pending trigger. Different triggers can
therefore use different persistence periods; zero retains immediate execution.

## Use an LCD

Create an **LCD** device and select its discovered LCD channel. For a 1204
TextLCD Adapter, select the dimensions of the physical panel connected to the
adapter; the adapter cannot detect those dimensions itself. Integrated text
LCDs and graphic LCDs should use **Automatic / graphic LCD**.

Initial backlight and contrast values are applied whenever the channel
attaches. Text panels show one, two, or four initial-line fields according to
the selected panel size. Optionally, those lines can be restored after each
attachment.

## Use ADP0001 GPIO pins

First create and configure the **I2C Data Adapter** device. Then create one
**I2C Adapter GPIO Input** or **I2C Adapter GPIO Output** Indigo device for each
GPIO pin in use, select that adapter, and choose GPIO 0 or GPIO 1. A pin may be
assigned only once and therefore cannot be configured as both input and output.

Inputs default to pull-up, inverted state, and 50 ms debounce. For a momentary
dry-contact switch, wire `GND → switch → GPIO`; pressing the switch then appears
as On in Indigo. Outputs are Indigo relays with On, Off, Toggle, and status
actions. They are logic signals with 499 Ω series resistance and approximately
10 mA available current—not load drivers. Use appropriate interface hardware
for relays, lamps, and similar loads.

## Use an SGP41 gas sensor

First create an **I2C Data Adapter** using a 3.3 V I2C bus, then add an
**I2C SGP41 VOC/NOx Gas Sensor** and select that adapter. The SGP41 address is
fixed at `0x59`. Enter the ambient relative humidity and temperature used for
compensation; the defaults are 50 %RH and 25 °C.

After startup or adapter reattachment, the sensor conditions its NOx pixel for
10 seconds. During that period Indigo publishes the raw VOC signal and shows
the conditioning state; raw NOx readings begin when conditioning finishes.
Both raw signals and the calculated VOC/NOx gas indices are updated once per
second. The indices begin at zero during warm-up and are not gas concentrations.

Use the sensor's **Display state** setting to choose whether Raw VOC or Raw NOx
appears in Indigo's Home → Devices → State column. BME280/BMP280 devices offer
the same setting for temperature, pressure, and—on BME280 only—humidity.

LCD commands are available under Indigo's **Device Actions**:

- Set LCD display
- Stop LCD animation
- Clear LCD
- Put LCD to sleep or wake it, when supported by the hardware

**Set LCD display** provides Static, Marquee, and Flash / alternate modes,
along with backlight and contrast. The selected text LCD determines whether
one, two, or four row fields are shown. Static mode on a graphic LCD instead
shows text and pixel coordinates. This implementation uses the built-in 5×8
font.

Text LCD animations have three modes. **Marquee — independent rows** scrolls
each row's message independently, while applying one direction, repeat gap,
and interval to the whole display. **Flash / alternate** switches every row
together between text sets A and B. Starting the animation action again
replaces the running animation; Static, clear, sleep, and detachment stop it.
The stop action leaves the most recently displayed frame visible.

**Virtual single-line marquee** instead shows one text field and treats every
physical row as one continuous row-major line. A 2×20 display therefore acts
as a 40-character path: Left enters at the lower right and moves toward the
upper left; Right enters at the upper left and moves toward the lower right.
Direction, interval, and repeat gap use the same controls as the independent-
row marquee.

Static and Flash text wider than its physical row is clipped to fit. Marquee
text is not clipped because the complete message scrolls through the row. Each
clipped row produces one Indigo Event Log warning showing its original and
displayed text; Flash logs this when the animation starts, not on every frame.

## Inspect visible Phidgets

Choose **Plugins → Phidgets 22 → Print all visible Phidgets to log** to write
the discovered local and remote device/channel hierarchy to Indigo's Event
Log. **Print Indigo Phidget devices to log** lists only devices configured in
this plugin. The menu also offers an asynchronous firmware-version collection
and a JSON export of all configured plugin devices and states.

### Indigo 2025.1 compatibility

Indigo 2025.1 uses Python 3.11, according to the
[Indigo Python packages documentation](https://wiki.indigodomo.com/doku.php?id=indigo_2025.1_documentation%3Apython_packages).
Use with Indigo 2025.1 may be possible, but remains unverified on a live
installation and may require manual intervention, particularly installing or
updating Phidget22 for Indigo's Python runtime. Indigo 2025.2 remains the
supported minimum for the Store release. To test 2025.1, install the dependency
for its documented Python 3.11 runtime with:

```zsh
"/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11" -m pip install --upgrade phidget22
```

The plugin's dependency messages detect the running Python version and provide
the matching command. No additional Python version needs to be installed.
