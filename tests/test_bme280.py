import logging
import pathlib
import struct
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

import bme280


class FakeAdapter(object):
    def __init__(self, registers):
        self.registers = registers
        self.writes = []
        self.channelInfo = mock.sentinel.channel_info
        self.indigoDevice = types.SimpleNamespace(
            name="I2C Adapter",
            states={
                "connectionType": "remote",
                "serverName": "CM-Library Mac",
                "connectionPath": "CM-Library Mac→I2C Adapter",
            })

    def supportsFunction(self, function_id):
        return function_id == "bme280"

    def i2cSendReceive(self, address, data=None, receiveLength=0):
        payload = bytes(data or ())
        if receiveLength:
            return self.registers[payload[0]][:receiveLength]
        self.writes.append((address, payload))
        return b""


class BME280Tests(unittest.TestCase):
    CALIBRATION = {
        "T1": 27504, "T2": 26435, "T3": -1000,
        "P1": 36477, "P2": -10685, "P3": 3024, "P4": 2855,
        "P5": 140, "P6": -7, "P7": 15500, "P8": -14600, "P9": 6000,
        "H1": 0, "H2": 0, "H3": 0, "H4": 0, "H5": 0, "H6": 0,
    }

    def wrapper(self, chip_id=0x58):
        block = struct.pack(
            "<HhhHhhhhhhhh", 27504, 26435, -1000, 36477, -10685,
            3024, 2855, 140, -7, 15500, -14600, 6000)
        registers = {
            0xD0: bytes((chip_id,)), 0x88: block, 0xA1: b"\x00",
            0xE1: b"\x00" * 7,
        }
        adapter = FakeAdapter(registers)
        device = mock.Mock(name="Weather sensor")
        device.name = "Weather sensor"
        device.states = {}
        plugin = types.SimpleNamespace(
            activePhidgets={42: adapter},
            getDeviceStateDictForNumberType=lambda *args: args,
            getDeviceStateDictForStringType=lambda *args: args,
        )
        wrapper = bme280.BME280Phidget(
            adapterDeviceId=42, indigo_plugin=plugin, indigoDevice=device,
            logger=logging.getLogger("test.bme280"), decimalPlaces=2)
        wrapper.adapter = adapter
        return wrapper, adapter, device

    def test_initialization_identifies_bmp_and_configures_measurement(self):
        wrapper, adapter, device = self.wrapper(0x58)

        wrapper._initialize()

        self.assertEqual(wrapper.chipModel, "BMP280")
        self.assertEqual(wrapper.calibration["T1"], 27504)
        self.assertEqual(adapter.writes, [
            (0x76, b"\xF5\xA0"), (0x76, b"\xF4\x27")])

    def test_bosch_reference_temperature_and_pressure_compensation(self):
        wrapper, _, _ = self.wrapper()
        wrapper.chipModel = "BMP280"
        wrapper.calibration = dict(self.CALIBRATION)
        adc_p, adc_t = 415148, 519888
        data = bytes((
            (adc_p >> 12) & 0xFF, (adc_p >> 4) & 0xFF, (adc_p & 0xF) << 4,
            (adc_t >> 12) & 0xFF, (adc_t >> 4) & 0xFF, (adc_t & 0xF) << 4,
            0, 0))

        temperature, pressure, humidity = wrapper._compensate(data)

        self.assertAlmostEqual(temperature, 25.08, places=2)
        self.assertAlmostEqual(pressure, 1006.53, places=2)
        self.assertIsNone(humidity)

    def test_bme_model_publishes_humidity_state(self):
        wrapper, _, device = self.wrapper(0x60)
        wrapper.chipModel = "BME280"
        wrapper.calibration = dict(self.CALIBRATION, H2=300)
        wrapper._state = "attached"
        wrapper._generation = 1
        wrapper._read = mock.Mock(return_value=b"\x65\x5A\xC0\x7E\xED\x00\x80\x00")

        with mock.patch.object(bme280.threading, "Timer"):
            wrapper._poll(1)

        state_ids = [call.args[0]
                     for call in device.updateStateOnServer.call_args_list]
        self.assertEqual(state_ids, [
            "connectionType", "serverName", "connectionPath", "sensorModel",
            "i2cAddress", "temperature", "pressure", "humidity"])
        device.updateStateOnServer.assert_any_call(
            "connectionPath",
            value="CM-Library Mac→I2C Adapter→BME280 0x76")
        device.updateStateOnServer.assert_any_call(
            "sensorModel", value="BME280")
        device.updateStateOnServer.assert_any_call(
            "i2cAddress", value="0x76")

    def test_state_list_omits_humidity_for_bmp(self):
        wrapper, _, _ = self.wrapper(0x58)
        wrapper.chipModel = "BMP280"

        states = wrapper.getDeviceStateList()

        self.assertNotIn("humidity", [state[0] for state in states])


if __name__ == "__main__":
    unittest.main()
