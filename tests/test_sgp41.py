import pathlib
import sys
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
indigo = sys.modules.setdefault("indigo", types.ModuleType("indigo"))
indigo.List = list
indigo.Dict = dict
indigo.PluginBase = type("PluginBase", (object,), {"__del__": lambda self: None})

import sgp41
from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException


class FakeAdapter(object):
    def __init__(self):
        self._state = "attached"
        self.channelInfo = mock.sentinel.channel_info
        self.indigoDevice = types.SimpleNamespace(
            name="I2C Adapter", states={"connectionPath": "Mac→I2C Adapter"})
        self.calls = []

    def supportsFunction(self, function_id):
        return function_id == "sgp41"

    def i2cCommandResponse(self, address, payload, delay, receive_length):
        self.calls.append((address, payload, delay, receive_length))
        if payload == b"\x36\x82":
            return b"\x12\x34\x37\x56\x78\x7D\x9A\xBC\xE0"
        if payload.startswith(b"\x26\x12"):
            return b"\x11\x22\xFF"
        return b"\x11\x22\xFF\x33\x44\xE7"


class SGP41Tests(unittest.TestCase):
    def wrapper(self):
        adapter = FakeAdapter()
        device = mock.Mock(name="Air sensor")
        device.name = "Air sensor"
        device.id = 7
        device.states = {}
        plugin = types.SimpleNamespace(
            activePhidgets={42: adapter},
            getDeviceStateDictForNumberType=lambda *args: args,
            getDeviceStateDictForStringType=lambda *args: args)
        wrapper = sgp41.SGP41Phidget(
            42, indigo_plugin=plugin, indigoDevice=device,
            logger=mock.Mock())
        return wrapper, adapter, device

    def test_crc_and_default_compensation_match_datasheet(self):
        wrapper, _, _ = self.wrapper()
        self.assertEqual(wrapper.crc(b"\x80\x00"), 0xA2)
        self.assertEqual(wrapper.crc(b"\x66\x66"), 0x93)
        self.assertEqual(wrapper._compensation(), b"\x80\x00\xA2\x66\x66\x93")

    def test_initialization_reads_and_validates_serial_number(self):
        wrapper, adapter, _ = self.wrapper()
        wrapper._initialize()
        self.assertEqual(wrapper.serialNumber, "123456789ABC")
        self.assertEqual(adapter.calls[0], (0x59, b"\x36\x82", 0.001, 9))

    def test_conditions_ten_times_before_voc_nox_measurement(self):
        wrapper, adapter, _ = self.wrapper()
        wrapper.adapter = adapter
        samples = [wrapper._sample() for _ in range(11)]
        self.assertEqual(samples[:10], [(0x1122, None)] * 10)
        self.assertEqual(samples[10], (0x1122, 0x3344))
        self.assertTrue(all(call[1].startswith(b"\x26\x12")
                            for call in adapter.calls[:10]))
        self.assertTrue(adapter.calls[10][1].startswith(b"\x26\x19"))

    def test_bad_crc_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "invalid CRC"):
            sgp41.SGP41Phidget._decode_words(b"\x12\x34\x00", 1)

    def test_configured_display_state_is_returned(self):
        wrapper, _, _ = self.wrapper()
        wrapper.displayState = "rawNox"
        self.assertEqual(wrapper.getDeviceDisplayStateId(), "rawNox")

    def test_defined_but_absent_sensor_stays_active_and_retries(self):
        wrapper, adapter, device = self.wrapper()
        adapter.i2cCommandResponse = mock.Mock(
            side_effect=PhidgetException(ErrorCode.EPHIDGET_NACK))

        with mock.patch.object(sgp41.threading, "Timer") as timer:
            wrapper.start()

        self.assertEqual(wrapper._state, "attached")
        self.assertIsNone(wrapper.serialNumber)
        device.setErrorStateOnServer.assert_called_with("No response at 0x59")
        timer.assert_called_once_with(1.0, wrapper._poll, (wrapper._generation,))

    def test_state_list_is_rebuilt_before_first_state_update(self):
        wrapper, _, device = self.wrapper()

        with mock.patch.object(sgp41.threading, "Timer"):
            wrapper.start()

        refresh_index = device.mock_calls.index(
            mock.call.stateListOrDisplayStateIdChanged())
        first_update_index = next(
            index for index, call in enumerate(device.mock_calls)
            if call == mock.call.updateStateOnServer(
                "connectionPath", value="Mac→I2C Adapter→SGP41 0x59"))
        self.assertLess(refresh_index, first_update_index)


if __name__ == "__main__":
    unittest.main()
