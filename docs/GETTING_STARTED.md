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
attaches. Optionally, the configured initial text can also be restored after
each attachment.

LCD commands are available under Indigo's **Device Actions**:

- Write LCD text
- Clear LCD
- Set LCD backlight
- Set LCD contrast
- Put LCD to sleep or wake it, when supported by the hardware

Text coordinates are character columns and rows on a text LCD. Graphic LCD
coordinates are pixels. This first implementation uses the built-in 5×8 font.

## Print the Phidgets network map

Choose **Plugins → Phidgets 22 → Print Phidgets network diagram to log**.
The complete discovered hierarchy is written to Indigo's Event Log, organized
by server, physical Phidget, VINT port, and channel.
