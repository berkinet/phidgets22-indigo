import importlib.util
import logging
import pathlib
import sys
import unittest


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
SPEC = importlib.util.spec_from_file_location("discovery", SERVER_PLUGIN / "discovery.py")
discovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discovery)


class FakeChannel(object):
    values = {
        "getIsRemote": True,
        "getServerName": "phidget-server",
        "getServerUniqueName": "phidget-server._phidget22server._tcp.local",
        "getServerHostname": "server.local",
        "getServerPeerName": "192.0.2.10:5661",
        "getDeviceSerialNumber": 123456,
        "getDeviceLabel": "Test Hub",
        "getDeviceName": "VINT Hub Phidget",
        "getDeviceSKU": "HUB0000",
        "getDeviceClass": 21,
        "getDeviceClassName": "Phidget Hub",
        "getChannel": 0,
        "getChannelClass": 5,
        "getChannelClassName": "PhidgetDigitalInput",
        "getChannelName": "Digital Input",
        "getChannelSubclass": 1,
        "getHubPort": 2,
        "getIsHubPortDevice": False,
    }

    def __getattr__(self, name):
        if name not in self.values:
            raise AttributeError(name)
        return lambda: self.values[name]


class FakeManager(object):
    def __init__(self):
        self.attach_handler = None
        self.detach_handler = None
        self.is_open = False

    def setOnAttachHandler(self, handler):
        self.attach_handler = handler

    def setOnDetachHandler(self, handler):
        self.detach_handler = handler

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False


class DiscoveryTests(unittest.TestCase):
    def test_describe_remote_channel(self):
        description = discovery.describe_channel(FakeChannel())
        self.assertEqual(description["serverName"], "phidget-server")
        self.assertEqual(description["serialNumber"], 123456)
        self.assertEqual(description["hubPort"], 2)
        self.assertEqual(description["channelClassName"], "PhidgetDigitalInput")

    def test_inventory_tracks_attach_and_detach(self):
        inventory = discovery.DiscoveryInventory(logging.getLogger("test"), manager_factory=FakeManager)
        inventory.start()
        inventory.manager.attach_handler(inventory.manager, FakeChannel())

        snapshot = inventory.snapshot()
        self.assertEqual(len(snapshot), 1)
        self.assertIn("server=phidget-server", discovery.format_channel(snapshot[0]))

        inventory.manager.detach_handler(inventory.manager, FakeChannel())
        self.assertEqual(inventory.snapshot(), [])
        inventory.stop()
        self.assertFalse(inventory.manager.is_open)

    def test_hierarchical_choices_filter_group_and_resolve(self):
        inventory = discovery.DiscoveryInventory(logging.getLogger("test"), manager_factory=FakeManager)
        inventory.start()
        first = FakeChannel()
        second = FakeChannel()
        second.values = dict(FakeChannel.values, getChannel=1)
        unrelated = FakeChannel()
        unrelated.values = dict(FakeChannel.values, getChannel=2,
                                getChannelClassName="PhidgetDigitalOutput")
        inventory.manager.attach_handler(inventory.manager, first)
        inventory.manager.attach_handler(inventory.manager, second)
        inventory.manager.attach_handler(inventory.manager, unrelated)

        servers = inventory.server_choices("digitalInput")
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0][1], "phidget-server")
        devices = inventory.device_choices_for_server("digitalInput", servers[0][0])
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0][1], "VINT Hub")
        channels = inventory.channel_choices("digitalInput", devices[0][0])
        self.assertEqual(len(channels), 2)
        self.assertEqual(inventory.resolve_channel(channels[1][0])["channel"], 1)

    def test_invalid_tokens_are_safe(self):
        inventory = discovery.DiscoveryInventory(logging.getLogger("test"), manager_factory=FakeManager)
        self.assertEqual(inventory.channel_choices("digitalInput", "not-a-token"), [])
        self.assertIsNone(inventory.resolve_channel("not-a-token"))

    def test_reverse_resolves_legacy_hub_port_address(self):
        inventory = discovery.DiscoveryInventory(logging.getLogger("test"), manager_factory=FakeManager)
        inventory.start()
        voltage_input = FakeChannel()
        voltage_input.values = dict(
            FakeChannel.values,
            getDeviceSerialNumber=622702,
            getServerName="Test-Server-A",
            getServerUniqueName="Test-Server-A._phidget22server._tcp.local",
            getHubPort=0,
            getChannel=0,
            getIsHubPortDevice=True,
            getChannelClass=29,
            getChannelClassName="PhidgetVoltageInput",
            getChannelName="Voltage Input",
            getDeviceSKU="VOLTAGEINPUT_PORT",
        )
        inventory.manager.attach_handler(inventory.manager, voltage_input)

        selection = inventory.selection_for_saved_address("voltageInput", {
            "serialNumber": "622702",
            "channel": "0",
            "serverName": "Test-Server-A",
            "isVintHub": True,
            "isVintDevice": False,
            "hubPort": "0",
        })

        self.assertIsNotNone(selection)
        channel = inventory.resolve_channel(selection["discoveredChannel"])
        self.assertEqual(channel["serverName"], "Test-Server-A")
        self.assertEqual(channel["hubPort"], 0)
        self.assertEqual(
            inventory.resolve_device(selection["discoveredDevice"])["serialNumber"],
            622702,
        )

    def test_reverse_resolution_refuses_ambiguous_legacy_address(self):
        inventory = discovery.DiscoveryInventory(logging.getLogger("test"), manager_factory=FakeManager)
        inventory.start()
        first = FakeChannel()
        first.values = dict(FakeChannel.values, getDeviceSerialNumber=622702,
                            getServerName="first", getServerUniqueName="first.local")
        second = FakeChannel()
        second.values = dict(FakeChannel.values, getDeviceSerialNumber=622702,
                             getServerName="second", getServerUniqueName="second.local")
        inventory.manager.attach_handler(inventory.manager, first)
        inventory.manager.attach_handler(inventory.manager, second)

        selection = inventory.selection_for_saved_address("digitalInput", {
            "serialNumber": "622702",
            "channel": "0",
            "isVintHub": True,
            "isVintDevice": True,
            "hubPort": "2",
        })

        self.assertIsNone(selection)

    def test_hub_port_modes_group_as_one_physical_hub(self):
        inventory = discovery.DiscoveryInventory(logging.getLogger("test"), manager_factory=FakeManager)
        inventory.start()
        for port in (0, 1, 2):
            channel = FakeChannel()
            channel.values = dict(FakeChannel.values, getHubPort=port, getChannel=0,
                                  getIsHubPortDevice=True, getDeviceSKU="DIGITALINPUT_PORT")
            inventory.manager.attach_handler(inventory.manager, channel)
        server = inventory.server_choices("digitalInput")[0][0]
        devices = inventory.device_choices_for_server("digitalInput", server)
        self.assertEqual(len(devices), 1)
        self.assertNotIn("DIGITALINPUT_PORT", devices[0][1])
        ports = inventory.port_choices("digitalInput", devices[0][0])
        self.assertEqual([label for value, label in ports], ["Port 0", "Port 1", "Port 2"])
        targets = inventory.target_choices("digitalInput", ports[0][0])
        self.assertEqual(len(targets), 1)
        self.assertEqual(len(inventory.channel_choices("digitalInput", devices[0][0], targets[0][0])), 1)

    def test_occupied_port_hides_generic_functions_and_shows_vint_device(self):
        inventory = discovery.DiscoveryInventory(logging.getLogger("test"), manager_factory=FakeManager)
        inventory.start()
        for port in (0, 1):
            channel = FakeChannel()
            channel.values = dict(FakeChannel.values, getHubPort=port, getChannel=0,
                                  getIsHubPortDevice=True,
                                  getChannelClassName="PhidgetDigitalOutput",
                                  getDeviceSKU="DIGITALOUTPUT_PORT")
            inventory.manager.attach_handler(inventory.manager, channel)
        humidity = FakeChannel()
        humidity.values = dict(FakeChannel.values, getHubPort=1, getChannel=0,
                               getIsHubPortDevice=False,
                               getChannelClassName="PhidgetHumiditySensor",
                               getChannelName="Humidity Sensor",
                               getDeviceName="Humidity Sensor Phidget", getDeviceSKU="HUM1001")
        inventory.manager.attach_handler(inventory.manager, humidity)
        temperature = FakeChannel()
        temperature.values = dict(humidity.values, getChannelClass=28,
                                  getChannelClassName="PhidgetTemperatureSensor",
                                  getChannelName="Temperature Sensor")
        inventory.manager.attach_handler(inventory.manager, temperature)

        output_server = inventory.server_choices("digitalOutput")[0][0]
        hub = inventory.device_choices_for_server("digitalOutput", output_server)[0][0]
        self.assertEqual([label for value, label in inventory.port_choices("digitalOutput", hub)], ["Port 0", "Port 1"])

        humidity_server = inventory.server_choices("humiditySensor")[0][0]
        humidity_hub = inventory.device_choices_for_server("humiditySensor", humidity_server)[0][0]
        port = inventory.port_choices("humiditySensor", humidity_hub)[1]
        self.assertEqual(port[1], "Port 1")
        target = inventory.target_choices("humiditySensor", port[0])[0]
        self.assertEqual(target[1], "Humidity Sensor (HUM1001)")
        temperature_target = inventory.target_choices("temperatureSensor", port[0])[0]
        self.assertEqual(temperature_target[1], "Temperature Sensor (HUM1001)")

    def test_empty_port_offers_only_the_selected_model_function(self):
        inventory = discovery.DiscoveryInventory(logging.getLogger("test"), manager_factory=FakeManager)
        inventory.start()
        functions = (
            (5, "PhidgetDigitalInput", "Digital Input", "DIGITALINPUT_PORT"),
            (6, "PhidgetDigitalOutput", "Digital Output", "DIGITALOUTPUT_PORT"),
            (29, "PhidgetVoltageInput", "Voltage Input", "VOLTAGEINPUT_PORT"),
            (32, "PhidgetVoltageRatioInput", "Voltage Ratio Input", "VOLTAGERATIOINPUT_PORT"),
        )
        for channel_class, class_name, channel_name, sku in functions:
            channel = FakeChannel()
            channel.values = dict(FakeChannel.values, getHubPort=0, getChannel=0,
                                  getIsHubPortDevice=True, getChannelClass=channel_class,
                                  getChannelClassName=class_name, getChannelName=channel_name,
                                  getDeviceSKU=sku)
            inventory.manager.attach_handler(inventory.manager, channel)
        server = inventory.server_choices("digitalOutput")[0][0]
        hub = inventory.device_choices_for_server("digitalOutput", server)[0][0]
        port = inventory.port_choices("digitalOutput", hub)[0][0]
        labels = [label for value, label in inventory.target_choices("digitalOutput", port)]
        self.assertEqual(labels, ["Digital Output"])

    def test_interfacekit_exposes_all_eight_matching_channels(self):
        inventory = discovery.DiscoveryInventory(logging.getLogger("test"), manager_factory=FakeManager)
        inventory.start()
        for channel_number in range(8):
            channel = FakeChannel()
            channel.values = dict(FakeChannel.values, getDeviceClass=9,
                                  getDeviceName="PhidgetInterfaceKit 8/8/8",
                                  getDeviceSKU="1010/1018/1019", getHubPort=-1,
                                  getChannel=channel_number, getChannelClass=6,
                                  getChannelClassName="PhidgetDigitalOutput",
                                  getChannelName="Digital Output", getIsHubPortDevice=False)
            inventory.manager.attach_handler(inventory.manager, channel)
        server = inventory.server_choices("digitalOutput")[0][0]
        interfacekit = inventory.device_choices_for_server("digitalOutput", server)[0][0]
        self.assertFalse(inventory.is_vint_device(interfacekit))
        self.assertEqual(len(inventory.channel_choices("digitalOutput", interfacekit)), 8)

    def test_device_choice_prefers_friendly_name_over_part_number(self):
        description = discovery.describe_channel(FakeChannel())
        description["deviceLabel"] = ""
        description["deviceName"] = "PhidgetInterfaceKit 8/8/8"
        description["deviceSKU"] = "1010/1018/1019"
        description["deviceClass"] = 9
        choice = discovery.format_device_choice(description)
        self.assertEqual(choice, "InterfaceKit 8/8/8 (1010/1018/1019)")

    def test_network_diagram_groups_usb_and_vint_devices_under_server(self):
        vint = discovery.describe_channel(FakeChannel())
        vint.update({
            "serverName": "Test-Server-B",
            "serialNumber": 622666,
            "hubPort": 0,
            "isHubPortDevice": True,
            "channelClassName": "PhidgetVoltageInput",
            "channelName": "Voltage Input",
        })
        usb = dict(vint, serialNumber=283587, deviceClass=13,
                   deviceName="PhidgetTemperatureSensor 4-Input",
                   deviceSKU="1048", hubPort=-1, isHubPortDevice=False,
                   channel=1, channelClassName="PhidgetTemperatureSensor",
                   channelName="Temperature Sensor")

        diagram = "\n".join(discovery.format_network_diagram([vint, usb]))

        self.assertIn("Server: Test-Server-B", diagram)
        self.assertIn("Device: VINT Hub — serial 622666", diagram)
        self.assertIn("Port 0", diagram)
        self.assertIn("Voltage Input — channel 0", diagram)
        self.assertIn("TemperatureSensor 4-Input (1048) — serial 283587", diagram)
        self.assertIn("Temperature Sensor — channel 1", diagram)


if __name__ == "__main__":
    unittest.main()
