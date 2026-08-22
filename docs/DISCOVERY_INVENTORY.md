# Read-only discovery inventory

The production-hardening branch maintains an observational inventory of channels reported by the Phidget22 `Manager` API.

## Purpose

The inventory now also supplies an optional, hierarchical configuration path. It does not:

- create or modify Indigo devices;
- change already-saved Indigo devices unless the user edits and saves them;
- open discovered channels;
- replace manual serial/channel/hub-port addressing; or
- create or register network servers.

Existing saved devices and manual configuration remain valid. Choosing a discovered Phidget and channel fills the established serial, channel, hub-port, and VINT properties when the configuration is saved. For remote channels it also records the discovered server name so attachment cannot drift to an identically addressed device on another server.

## Configuring a discovered channel

In an Indigo device configuration dialog:

1. Choose a server from **Discovered server**.
2. Choose a compatible entry from **Phidget**.
3. For a VINT hub, choose the physical **VINT port**.
4. Choose the attached VINT device or an available hub-port function.
5. Choose one of that device or function's compatible channels.
6. Save the device.

The menus follow the physical topology: server, hub, port, attached device or port function, then channel. Because the Indigo Model is already known, servers and devices are pruned to compatible paths, while every physical port on a compatible VINT hub remains visible. Model compatibility is applied after the port is selected. At each level, a sole compatible option is selected automatically and the cascade continues until a real choice is required; a completely unique path is filled without further selection. A channel menu appears only when multiple compatible channel numbers require a choice. The serial number is populated as read-only confirmation. The legacy channel and server-name properties remain stored but are hidden from the dialog.

If a selected channel detaches before the dialog is saved, validation stops the save and asks for an available channel rather than retaining stale discovery data.

## Lifecycle

After the plugin enables Phidget network-server discovery, it starts a `DiscoveryInventory`. The inventory registers Manager attach and detach handlers and keeps a thread-safe in-memory snapshot.

If the inventory cannot start, the plugin logs a warning and continues starting normally. Existing configured devices do not depend on the inventory.

The Manager is closed and the snapshot is cleared during plugin shutdown before the global Phidget API is finalized.

## Using the inventory

In Indigo, choose:

**Plugins → Phidgets 22 → Log Discovered Phidgets**

The plugin logs the number of observed channels followed by one line per channel. Each line includes the available server, device, serial number, hub port, channel number, channel class, and device label.

Serial numbers and device labels may identify a private hardware installation. Review or redact them before publishing diagnostic logs.

## Interpreting results

The inventory records channels, not merely physical enclosures. A single Phidget can therefore produce multiple rows, including multiple rows with the same serial number and hub port.

For remote channels, the identity includes the discovered server. For local channels, the server is reported as `Local`.

The output should be compared with existing manually configured Indigo devices. That comparison will establish which discovery fields are reliable enough to drive constrained configuration menus in a later change.

## Verification

Pure unit tests cover metadata extraction, stable formatting, attach tracking, detach removal, snapshot behavior, and Manager lifecycle using a fake Manager/channel. Final validation still requires Indigo and the actual Phidget network topology.

A three-second native-library smoke test on the development host successfully opened the Manager, observed 296 channels across the available network servers, produced a snapshot, and closed the Manager. This verifies the read-only discovery mechanism against the current network topology, but not yet inside Indigo's plugin host.
