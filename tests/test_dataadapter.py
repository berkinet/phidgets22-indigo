import pathlib
import sys
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))

import dataadapter
from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException


class FakeDataAdapter(object):
    def __init__(self):
        self.voltage = None
        self.frequency = None
        self.calls = []

    def setDataAdapterVoltage(self, value):
        self.voltage = value

    def getDataAdapterVoltage(self):
        return self.voltage

    def setFrequency(self, value):
        self.frequency = value

    def getFrequency(self):
        return self.frequency

    def getMaxSendPacketLength(self):
        return 8

    def getMaxReceivePacketLength(self):
        return 6

    def i2cSendReceive(self, address, payload, receive_length):
        self.calls.append((address, payload, receive_length))
        return b"reply"

    def i2cComplexTransaction(self, address, packet_string, payload):
        self.calls.append((address, packet_string, payload))
        return b"complex"


class DataAdapterTests(unittest.TestCase):
    def wrapper(self, state="attached"):
        wrapper = object.__new__(dataadapter.DataAdapterPhidget)
        wrapper.phidget = FakeDataAdapter()
        wrapper.indigoDevice = mock.Mock(name="I2C Bus")
        wrapper.indigoDevice.name = "I2C Bus"
        wrapper.voltage = 5
        wrapper.frequency = 2
        wrapper._state = state
        wrapper._transaction_lock = dataadapter.threading.RLock()
        return wrapper

    def test_attach_configures_bus_and_publishes_capabilities(self):
        wrapper = self.wrapper(state="starting")

        wrapper.configureAttachedPhidget(wrapper.phidget)

        self.assertEqual(wrapper.phidget.voltage, 5)
        self.assertEqual(wrapper.phidget.frequency, 2)
        updates = dict((call.args[0], call.kwargs["value"])
                       for call in wrapper.indigoDevice.updateStateOnServer.call_args_list)
        self.assertEqual(updates, {
            "adapterStatus": "I2C ready",
            "availableFunctions": "LCD display transport",
            "dataAdapterVoltage": 5,
            "dataAdapterFrequency": 2,
            "maxSendPacketLength": 8,
            "maxReceivePacketLength": 6,
        })

    def test_adapter_advertises_lcd_provider_capability(self):
        self.assertTrue(dataadapter.DataAdapterPhidget.supportsFunction("lcd"))
        self.assertFalse(dataadapter.DataAdapterPhidget.supportsFunction("humidity"))

    def test_send_receive_validates_and_forwards_transaction(self):
        wrapper = self.wrapper()

        self.assertEqual(wrapper.i2cSendReceive(0x27, [0, 1], 2), b"reply")
        self.assertEqual(wrapper.phidget.calls, [(0x27, b"\x00\x01", 2)])

        for address in (-1, 0x80):
            with self.assertRaisesRegex(ValueError, "7-bit"):
                wrapper.i2cSendReceive(address)
        with self.assertRaisesRegex(ValueError, "maximum packet"):
            wrapper.i2cSendReceive(0x27, range(9))
        with self.assertRaisesRegex(ValueError, "maximum packet"):
            wrapper.i2cSendReceive(0x27, receiveLength=7)

    def test_transactions_require_an_attached_adapter(self):
        wrapper = self.wrapper(state="detached")

        with self.assertRaisesRegex(RuntimeError, "not attached"):
            wrapper.i2cSendReceive(0x27, [1])

    def test_read_only_address_probe_reports_ack_and_nack(self):
        wrapper = self.wrapper()

        self.assertTrue(wrapper.i2cAddressResponds(0x27))
        self.assertEqual(wrapper.phidget.calls, [(0x27, b"", 1)])

        wrapper.phidget.i2cSendReceive = mock.Mock(
            side_effect=PhidgetException(ErrorCode.EPHIDGET_NACK))
        self.assertFalse(wrapper.i2cAddressResponds(0x26))

    def test_complex_transaction_uses_same_owned_bus(self):
        wrapper = self.wrapper()

        result = wrapper.i2cComplexTransaction(0x27, "sT2p", [1, 2])

        self.assertEqual(result, b"complex")
        self.assertEqual(wrapper.phidget.calls, [(0x27, "sT2p", b"\x01\x02")])


if __name__ == "__main__":
    unittest.main()
