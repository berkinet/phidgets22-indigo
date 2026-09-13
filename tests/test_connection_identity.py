# -*- coding: utf-8 -*-

import pathlib
import sys
import types
import unittest


SERVER_PLUGIN = (pathlib.Path(__file__).parents[1] /
                 "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin")
sys.path.insert(0, str(SERVER_PLUGIN))

from config_util import saved_bool
from connection_identity import (ChannelIdentity, ConfiguredChannelIdentity,
                                 PhysicalDeviceIdentity, PortIdentity,
                                 ServerIdentity)


class ConnectionIdentityTests(unittest.TestCase):
    def test_runtime_server_prefers_unique_name_and_matches_all_aliases(self):
        wrapper = types.SimpleNamespace(
            runtimeServerName="Kitchen",
            runtimeServerUniqueName="Kitchen._phidget22server._tcp.local",
            runtimeServerHostname="kitchen.local.",
            runtimeServerPeerName="192.0.2.1:5661",
            channelInfo=types.SimpleNamespace(netInfo=types.SimpleNamespace(
                isRemote=True, serverName="Configured Kitchen")))

        identity = ServerIdentity.from_wrapper(wrapper)

        self.assertEqual(
            identity.key, "Kitchen._phidget22server._tcp.local")
        self.assertEqual(identity.display_name, "Kitchen")
        for alias in ("Configured Kitchen", "Kitchen",
                      "Kitchen._phidget22server._tcp.local",
                      "kitchen.local.", "192.0.2.1:5661"):
            self.assertTrue(identity.matches(alias))

    def test_local_and_remote_physical_devices_do_not_collide(self):
        local = PhysicalDeviceIdentity("local", 123456)
        remote = PhysicalDeviceIdentity("Server A", 123456)

        self.assertNotEqual(local, remote)
        self.assertEqual(len({local, remote}), 2)

    def test_ports_and_channels_have_distinct_identity_levels(self):
        physical = PhysicalDeviceIdentity("Server A", 123456)
        first_port = PortIdentity(physical, 1)
        second_port = PortIdentity(physical, 2)
        digital_input = ChannelIdentity(first_port, False, 0, 5)
        voltage_input = ChannelIdentity(first_port, False, 0, 30)

        self.assertNotEqual(first_port, second_port)
        self.assertNotEqual(digital_input, voltage_input)
        self.assertEqual(digital_input.port.physical_device, physical)

    def test_saved_channel_identity_normalizes_indigo_properties(self):
        props = {
            "serverName": " Server A ",
            "serialNumber": "123456",
            "hubPort": "2",
            "channel": "0",
            "isVintHub": "true",
            "isVintDevice": "false",
        }

        identity = ConfiguredChannelIdentity.from_properties(
            props, "digitalInput", saved_bool)

        self.assertEqual(identity.channel.port.physical_device.server_key,
                         "Server A")
        self.assertEqual(identity.channel.port.physical_device.serial_number,
                         123456)
        self.assertEqual(identity.channel.port.hub_port, 2)
        self.assertTrue(identity.channel.hub_port_device)


if __name__ == "__main__":
    unittest.main()
