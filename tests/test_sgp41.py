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
import i2c_peripheral
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

    def test_compensation_can_follow_independent_indigo_device_states(self):
        wrapper, _, _ = self.wrapper()
        wrapper.humiditySource = "device"
        wrapper.humidityDeviceId = "91"
        wrapper.humidityState = "humidity"
        wrapper.temperatureSource = "device"
        wrapper.temperatureDeviceId = "92"
        wrapper.temperatureState = "temperature"
        devices = {
            91: types.SimpleNamespace(states={"humidity": 61.5}),
            92: types.SimpleNamespace(states={"temperature": 21.25}),
        }

        with mock.patch.object(indigo, "devices", devices, create=True):
            wrapper._compensation()

        self.assertEqual(wrapper._actual_humidity, 61.5)
        self.assertEqual(wrapper._actual_temperature, 21.25)
        self.assertIsNone(wrapper._compensation_issue)

    def test_missing_compensation_state_logs_once_and_uses_fallback(self):
        wrapper, _, _ = self.wrapper()
        wrapper.humiditySource = "device"
        wrapper.humidityDeviceId = "91"
        wrapper.humidityState = "humidity"

        with mock.patch.object(indigo, "devices", {}, create=True):
            first = wrapper._compensation()
            second = wrapper._compensation()

        self.assertEqual(first, b"\x80\x00\xA2\x66\x66\x93")
        self.assertEqual(second, first)
        wrapper.logger.warning.assert_called_once()

        devices = {91: types.SimpleNamespace(states={"humidity": 60.0})}
        with mock.patch.object(indigo, "devices", devices, create=True):
            wrapper._compensation()
        wrapper.logger.info.assert_called_once()

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

        with mock.patch.object(i2c_peripheral.threading, "Timer") as timer:
            with mock.patch.object(
                    sgp41.time, "monotonic", side_effect=(100.0, 100.05)):
                wrapper.start()

        self.assertEqual(wrapper._state, "attached")
        self.assertIsNone(wrapper.serialNumber)
        device.setErrorStateOnServer.assert_called_with("No response at 0x59")
        delay, callback, args = timer.call_args.args
        self.assertAlmostEqual(delay, 0.95)
        self.assertEqual(callback, wrapper._poll)
        self.assertEqual(args, (wrapper._generation,))

    def test_detach_during_poll_stops_quietly(self):
        wrapper, adapter, device = self.wrapper()

        def detached_sample():
            adapter._state = "detached"
            raise RuntimeError("I2C adapter is not attached")

        wrapper._sample = detached_sample
        wrapper.start()

        self.assertEqual(wrapper._state, "detached")
        wrapper.logger.error.assert_not_called()
        device.setErrorStateOnServer.assert_not_called()

    def test_poll_interval_accounts_for_sensor_transaction_time(self):
        wrapper, _, _ = self.wrapper()

        with mock.patch.object(i2c_peripheral.threading, "Timer") as timer:
            with mock.patch.object(
                    sgp41.time, "monotonic", side_effect=(20.0, 20.05)):
                wrapper.start()

        delay, callback, args = timer.call_args.args
        self.assertAlmostEqual(delay, 0.95)
        self.assertEqual(callback, wrapper._poll)
        self.assertEqual(args, (wrapper._generation,))

    def test_state_list_is_rebuilt_before_first_state_update(self):
        wrapper, _, device = self.wrapper()

        with mock.patch.object(i2c_peripheral.threading, "Timer"):
            wrapper.start()

        refresh_index = device.mock_calls.index(
            mock.call.stateListOrDisplayStateIdChanged())
        first_update_index = next(
            index for index, call in enumerate(device.mock_calls)
            if call == mock.call.updateStateOnServer(
                "connectionPath", value="Mac→I2C Adapter→SGP41 0x59"))
        self.assertLess(refresh_index, first_update_index)

    def test_first_poll_publishes_warming_indices_and_compensation(self):
        wrapper, _, device = self.wrapper()

        with mock.patch.object(i2c_peripheral.threading, "Timer"):
            wrapper.start()

        device.updateStateOnServer.assert_any_call("vocIndex", value=0)
        device.updateStateOnServer.assert_any_call("noxIndex", value=0)
        device.updateStateOnServer.assert_any_call(
            "indexStatus", value="warming up", uiValue="warming up (1 s)")
        device.updateStateOnServer.assert_any_call(
            "compensationHumidity", value=50.0)
        device.updateStateOnServer.assert_any_call(
            "compensationTemperature", value=25.0)


if __name__ == "__main__":
    unittest.main()
