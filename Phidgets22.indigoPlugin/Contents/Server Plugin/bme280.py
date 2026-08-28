# -*- coding: utf-8 -*-

"""BME280/BMP280 environmental sensor on a shared ADP0001 I2C bus."""

import struct
import threading
import time
import traceback

import indigo

from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException
from phidget import PeripheralUnavailableError


class BME280Phidget(object):
    CHIP_IDS = {0x60: "BME280", 0x58: "BMP280"}

    def __init__(self, adapterDeviceId, i2cAddress=0x76, pollInterval=2.0,
                 indigo_plugin=None, indigoDevice=None, logger=None,
                 decimalPlaces=2, channelInfo=None, **kwargs):
        self.adapterDeviceId = int(adapterDeviceId)
        self.address = int(i2cAddress)
        self.pollInterval = float(pollInterval)
        self.indigo_plugin = indigo_plugin
        self.indigoDevice = indigoDevice
        self.logger = logger
        self.decimalPlaces = int(decimalPlaces)
        self.channelInfo = channelInfo
        self.adapter = None
        self.chipId = None
        self.chipModel = "Unknown"
        self.calibration = {}
        self._state = "stopped"
        self._timer = None
        self._generation = 0
        self._lock = threading.RLock()
        self._offline_message = None

    def _resolveAdapter(self):
        adapter = self.indigo_plugin.activePhidgets.get(self.adapterDeviceId)
        if adapter is None or not adapter.supportsFunction("bme280"):
            raise RuntimeError("The selected I2C adapter is not active")
        self.adapter = adapter
        self.channelInfo = adapter.channelInfo
        return adapter

    def _read(self, register, length):
        try:
            return bytes(self.adapter.i2cSendReceive(
                self.address, bytes((register,)), length))
        except PhidgetException as error:
            if error.code == ErrorCode.EPHIDGET_NACK:
                raise PeripheralUnavailableError(
                    "No BME280/BMP280 responded at 0x%02X" % self.address
                ) from None
            raise

    def _write(self, register, value):
        try:
            self.adapter.i2cSendReceive(
                self.address, bytes((register, value)), 0)
        except PhidgetException as error:
            if error.code == ErrorCode.EPHIDGET_NACK:
                raise PeripheralUnavailableError(
                    "No BME280/BMP280 responded at 0x%02X" % self.address
                ) from None
            raise

    @staticmethod
    def _signed12(value):
        return value - 4096 if value & 0x800 else value

    def _readCalibration(self):
        block = self._read(0x88, 24)
        humidity_one = self._read(0xA1, 1)[0]
        humidity = self._read(0xE1, 7)
        if len(block) != 24 or len(humidity) != 7:
            raise RuntimeError("The sensor returned incomplete calibration data")
        values = struct.unpack("<HhhHhhhhhhhh", block)
        keys = ("T1", "T2", "T3", "P1", "P2", "P3", "P4",
                "P5", "P6", "P7", "P8", "P9")
        calibration = dict(zip(keys, values))
        calibration.update({
            "H1": humidity_one,
            "H2": struct.unpack("<h", humidity[0:2])[0],
            "H3": humidity[2],
            "H4": self._signed12((humidity[3] << 4) | (humidity[4] & 0x0F)),
            "H5": self._signed12((humidity[5] << 4) | (humidity[4] >> 4)),
            "H6": struct.unpack("b", humidity[6:7])[0],
        })
        if not calibration["T1"] or not calibration["P1"]:
            raise RuntimeError("The sensor returned invalid calibration data")
        self.calibration = calibration

    def _initialize(self):
        self._resolveAdapter()
        response = self._read(0xD0, 1)
        if len(response) != 1 or response[0] not in self.CHIP_IDS:
            found = "no response" if not response else "chip ID 0x%02X" % response[0]
            raise PeripheralUnavailableError(
                "No BME280/BMP280 responded at 0x%02X (%s)" %
                (self.address, found))
        self.chipId = response[0]
        self.chipModel = self.CHIP_IDS[self.chipId]
        self._readCalibration()
        if self.chipModel == "BME280":
            self._write(0xF2, 0x01)  # humidity oversampling ×1
        self._write(0xF5, 0xA0)      # 1000 ms standby, filter off
        self._write(0xF4, 0x27)      # temperature/pressure ×1, normal mode
        time.sleep(0.02)              # allow the first conversion to complete
        self._offline_message = None

    def _publishMetadata(self):
        adapter_states = getattr(self.adapter.indigoDevice, "states", {})
        device_states = getattr(self.indigoDevice, "states", {})

        def publish(state_id, value):
            value = str(value or "")
            if str(device_states.get(state_id, "") or "") != value:
                self.indigoDevice.updateStateOnServer(state_id, value=value)

        for state_id in ("connectionType", "serverName", "serverUniqueName",
                         "serverHost", "serverPeer", "connection"):
            publish(state_id, adapter_states.get(state_id, ""))
        base_path = (adapter_states.get("connectionPath") or
                     adapter_states.get("connection") or
                     self.adapter.indigoDevice.name)
        publish("connectionPath", "%s→%s 0x%02X" %
                (base_path, self.chipModel, self.address))
        publish("sensorModel", self.chipModel)
        publish("i2cAddress", "0x%02X" % self.address)

    def _compensate(self, data):
        if len(data) != 8:
            raise RuntimeError("The sensor returned an incomplete measurement")
        adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        adc_h = (data[6] << 8) | data[7]
        c = self.calibration

        var1 = (adc_t / 16384.0 - c["T1"] / 1024.0) * c["T2"]
        var2 = ((adc_t / 131072.0 - c["T1"] / 8192.0) ** 2) * c["T3"]
        t_fine = var1 + var2
        temperature = t_fine / 5120.0

        var1 = t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * c["P6"] / 32768.0
        var2 += var1 * c["P5"] * 2.0
        var2 = var2 / 4.0 + c["P4"] * 65536.0
        var1 = (c["P3"] * var1 * var1 / 524288.0 + c["P2"] * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * c["P1"]
        if var1 == 0:
            raise RuntimeError("The sensor pressure calibration is invalid")
        pressure = 1048576.0 - adc_p
        pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
        pressure += (c["P9"] * pressure * pressure / 2147483648.0 +
                     pressure * c["P8"] / 32768.0 + c["P7"]) / 16.0

        humidity = None
        if self.chipModel == "BME280":
            h = t_fine - 76800.0
            h = ((adc_h - (c["H4"] * 64.0 + c["H5"] / 16384.0 * h)) *
                 (c["H2"] / 65536.0 *
                  (1.0 + c["H6"] / 67108864.0 * h *
                   (1.0 + c["H3"] / 67108864.0 * h))))
            humidity = max(0.0, min(100.0, h * (1.0 - c["H1"] * h / 524288.0)))
        return temperature, pressure / 100.0, humidity

    def _poll(self, generation):
        with self._lock:
            if generation != self._generation or self._state != "attached":
                return
            try:
                self._publishMetadata()
                temperature, pressure, humidity = self._compensate(
                    self._read(0xF7, 8))
                self.indigoDevice.updateStateOnServer(
                    "temperature", value=temperature,
                    decimalPlaces=self.decimalPlaces)
                self.indigoDevice.updateStateOnServer(
                    "pressure", value=pressure,
                    decimalPlaces=self.decimalPlaces)
                if humidity is not None:
                    self.indigoDevice.updateStateOnServer(
                        "humidity", value=humidity,
                        decimalPlaces=self.decimalPlaces)
                if self._offline_message is not None:
                    self.logger.info(
                        "I2C environmental sensor recovered: device='%s' "
                        "address=0x%02X", self.indigoDevice.name, self.address)
                    self._offline_message = None
                self.indigoDevice.setErrorStateOnServer(None)
            except PeripheralUnavailableError as error:
                message = str(error)
                if message != self._offline_message:
                    self.logger.error(
                        "Configured peripheral unavailable: device='%s': %s",
                        self.indigoDevice.name, message)
                    self._offline_message = message
                self.indigoDevice.setErrorStateOnServer(
                    "No response at 0x%02X" % self.address)
            except Exception:
                self.logger.error(
                    "BME280/BMP280 poll failed: device='%s'\n%s",
                    self.indigoDevice.name, traceback.format_exc())
                self.indigoDevice.setErrorStateOnServer("I2C read failed")
            if generation == self._generation and self._state == "attached":
                timer = threading.Timer(self.pollInterval, self._poll, (generation,))
                timer.daemon = True
                self._timer = timer
                timer.start()

    def start(self):
        with self._lock:
            self._initialize()
            self._generation += 1
            generation = self._generation
            self._state = "attached"
            self._poll(generation)

    def providerReattached(self):
        with self._lock:
            self._initialize()
            self._generation += 1
            generation = self._generation
            self._state = "attached"
            self._poll(generation)

    def serverKey(self):
        return self.adapter.serverKey() if self.adapter is not None else "local"

    def serverDisplayName(self):
        return (self.adapter.serverDisplayName()
                if self.adapter is not None else "I2C adapter")

    def _identity(self):
        return "device='%s' id=%s type=%s adapter=%s address=0x%02X" % (
            self.indigoDevice.name, self.indigoDevice.id, self.chipModel,
            self.adapterDeviceId, self.address)

    def providerStopping(self):
        with self._lock:
            self._generation += 1
            self._state = "detached"
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def stop(self):
        self.providerStopping()
        self._state = "stopped"

    def getDeviceStateList(self):
        states = indigo.List()
        measurements = [
            ("temperature", "Temperature (°C)"),
            ("pressure", "Barometric pressure (hPa)"),
        ]
        if self.chipModel == "BME280":
            measurements.append(("humidity", "Relative humidity (%RH)"))
        for state_id, label in measurements:
            states.append(self.indigo_plugin.getDeviceStateDictForNumberType(
                state_id, label, state_id))
        for state_id, label in (("sensorModel", "Sensor model"),
                                ("i2cAddress", "I2C address")):
            states.append(self.indigo_plugin.getDeviceStateDictForStringType(
                state_id, label, state_id))
        return states

    def getDeviceDisplayStateId(self):
        return "pressure"
