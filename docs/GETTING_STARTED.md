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

## Print the Phidgets network map

Choose **Plugins → Phidgets 22 → Print Phidgets network diagram to log**.
The complete discovered hierarchy is written to Indigo's Event Log, organized
by server, physical Phidget, VINT port, and channel.
