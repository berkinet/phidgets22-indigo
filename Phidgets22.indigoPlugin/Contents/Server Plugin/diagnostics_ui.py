"""Read-only diagnostic menu callbacks, separate from configuration validation."""
import indigo
from discovery import format_channel, format_network_diagram
from error_reporting import runtime_boundary


class DiagnosticsUiMixin:
    @runtime_boundary("logDiscoveryInventory")
    def logDiscoveryInventory(self):
        if self.discoveryInventory is None:
            self.logger.warning("Phidget discovery inventory is unavailable")
            return
        channels = self.discoveryInventory.snapshot()
        self.logger.info("Discovered Phidget inventory: %d channel(s)", len(channels))
        for channel in channels:
            self.logger.info("  %s", format_channel(channel))

    @runtime_boundary("printPhidgetsNetworkDiagram")
    def printPhidgetsNetworkDiagram(self):
        if self.discoveryInventory is None:
            self.logger.warning("Phidget discovery inventory is unavailable")
            return
        for line in format_network_diagram(self.discoveryInventory.snapshot()):
            self.logger.info("%s", line)

    @runtime_boundary("printIndigoPhidgetDevices")
    def printIndigoPhidgetDevices(self):
        devices = sorted(
            (device for device in indigo.devices
             if getattr(device, "pluginId", None) == self.pluginId),
            key=lambda device: str(device.name).lower())
        self.logger.info("Indigo Phidget devices: %d", len(devices))
        for device in devices:
            states = getattr(device, "states", {})
            connection = states.get("connectionPath", "")
            suffix = " connection=%r" % connection if connection else ""
            self.logger.info(
                "  name=%r id=%s type=%s enabled=%s address=%r%s",
                device.name, device.id, device.deviceTypeId,
                getattr(device, "enabled", True),
                getattr(device, "address", ""), suffix)

