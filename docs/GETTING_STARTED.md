# Getting started

## Configure the plugin

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

## Use an LCD

Create an **LCD** device and select its discovered LCD channel. For a 1204
TextLCD Adapter, select the dimensions of the physical panel connected to the
adapter; the adapter cannot detect those dimensions itself. Integrated text
LCDs and graphic LCDs should use **Automatic / graphic LCD**.

Initial backlight and contrast values are applied whenever the channel
attaches. Text panels show one, two, or four initial-line fields according to
the selected panel size. Optionally, those lines can be restored after each
attachment.

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

Text LCD animations have two modes. **Marquee** scrolls each row's message
independently, while applying one direction, repeat gap, and interval to the
whole display. **Flash / alternate** switches every row together between text
sets A and B. Starting the animation action again replaces the running
animation; Static, clear, sleep, and detachment stop it. The stop
action leaves the most recently displayed frame visible.

Static and Flash text wider than its physical row is clipped to fit. Marquee
text is not clipped because the complete message scrolls through the row. Each
clipped row produces one Indigo Event Log warning showing its original and
displayed text; Flash logs this when the animation starts, not on every frame.

## Print the Phidgets network map

Choose **Plugins → Phidgets 22 → Print Phidgets network diagram to log**.
The complete discovered hierarchy is written to Indigo's Event Log, organized
by server, physical Phidget, VINT port, and channel.
