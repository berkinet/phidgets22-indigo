# -*- coding: utf-8 -*-

"""Sensirion SGP41 VOC/NOx sensor on a shared ADP0001 I2C bus."""

import threading
import time
import traceback

import indigo

from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException
from phidget import PeripheralUnavailableError
from i2c_peripheral import I2CPeripheralBase
from sensirion_gas_index_algorithm import (
    ALGORITHM_TYPE_NOX, ALGORITHM_TYPE_VOC, GasIndexAlgorithm)


class SGP41Phidget(I2CPeripheralBase):
    PROVIDER_FUNCTION = "sgp41"
    ADDRESS = 0x59
    CONDITIONING_COMMAND = b"\x26\x12"
    MEASURE_COMMAND = b"\x26\x19"
    SERIAL_COMMAND = b"\x36\x82"
    HEATER_OFF_COMMAND = b"\x36\x15"
    CONDITIONING_SECONDS = 10

    def __init__(self, adapterDeviceId, relativeHumidity=50.0,
                 temperature=25.0, indigo_plugin=None, indigoDevice=None,
                 logger=None, displayState="vocIndex", channelInfo=None,
                 humiditySource="fixed", humidityDeviceId="",
                 humidityState="", temperatureSource="fixed",
                 temperatureDeviceId="", temperatureState="", **kwargs):
        self.adapterDeviceId = int(adapterDeviceId)
        self.relativeHumidity = float(relativeHumidity)
        self.temperature = float(temperature)
        self.humiditySource = str(humiditySource)
        self.humidityDeviceId = str(humidityDeviceId)
        self.humidityState = str(humidityState)
        self.temperatureSource = str(temperatureSource)
        self.temperatureDeviceId = str(temperatureDeviceId)
        self.temperatureState = str(temperatureState)
        self.displayState = str(displayState)
        self.indigo_plugin = indigo_plugin
        self.indigoDevice = indigoDevice
        self.logger = logger
        self.channelInfo = channelInfo
        self.adapter = None
        self.serialNumber = None
        self._conditioning_count = 0
        self._algorithm_sample_count = 0
        self._voc_algorithm = None
        self._nox_algorithm = None
        self._actual_humidity = self.relativeHumidity
        self._actual_temperature = self.temperature
        self._compensation_issue = None
        self._state = "stopped"
        self._timer = None
        self._generation = 0
        self._lock = threading.RLock()
        self._offline_message = None

    @staticmethod
    def crc(data):
        value = 0xFF
        for byte in bytearray(data):
            value ^= byte
            for _ in range(8):
                value = ((value << 1) ^ 0x31) & 0xFF if value & 0x80 else (value << 1) & 0xFF
        return value

    @classmethod
    def _word(cls, value):
        data = bytes(((int(value) >> 8) & 0xFF, int(value) & 0xFF))
        return data + bytes((cls.crc(data),))

    @classmethod
    def _decode_words(cls, response, count):
        if len(response) != count * 3:
            raise RuntimeError("The SGP41 returned an incomplete response")
        words = []
        for offset in range(0, len(response), 3):
            data = response[offset:offset + 2]
            if response[offset + 2] != cls.crc(data):
                raise RuntimeError("The SGP41 returned an invalid CRC")
            words.append((data[0] << 8) | data[1])
        return words

    def _command(self, command, arguments=b"", delay=0.05, words=1):
        try:
            response = self.adapter.i2cCommandResponse(
                self.ADDRESS, command + arguments, delay, words * 3)
            return self._decode_words(bytes(response), words)
        except PhidgetException as error:
            if error.code == ErrorCode.EPHIDGET_NACK:
                raise PeripheralUnavailableError(
                    "No SGP41 responded at 0x59") from None
            raise

    def _source_value(self, source, device_id, state_id, fallback,
                      label, minimum, maximum):
        if source != "device":
            return fallback, None
        try:
            source_device = indigo.devices[int(device_id)]
            value = float(source_device.states[state_id])
            if value < minimum or value > maximum:
                raise ValueError("value %s is outside %g through %g" % (
                    value, minimum, maximum))
            return value, None
        except Exception as error:
            return fallback, (
                "%s source device=%s state='%s' unavailable (%s); using %s" %
                (label, device_id, state_id, error, fallback))

    def _compensation(self):
        humidity, humidity_issue = self._source_value(
            self.humiditySource, self.humidityDeviceId, self.humidityState,
            self.relativeHumidity, "humidity", 0.0, 100.0)
        temperature, temperature_issue = self._source_value(
            self.temperatureSource, self.temperatureDeviceId,
            self.temperatureState, self.temperature,
            "temperature", -45.0, 130.0)
        issues = [issue for issue in (humidity_issue, temperature_issue) if issue]
        issue = "; ".join(issues) if issues else None
        if issue != self._compensation_issue:
            if issue:
                self.logger.warning(
                    "SGP41 compensation fallback: device='%s': %s",
                    self.indigoDevice.name, issue)
            elif self._compensation_issue:
                self.logger.info(
                    "SGP41 compensation source recovered: device='%s'",
                    self.indigoDevice.name)
            self._compensation_issue = issue
        self._actual_humidity = humidity
        self._actual_temperature = temperature
        humidity = round(max(0.0, min(100.0, humidity)) * 65535.0 / 100.0)
        temperature = round((max(-45.0, min(130.0, temperature)) + 45.0) *
                            65535.0 / 175.0)
        return self._word(humidity) + self._word(temperature)

    def _reset_algorithms(self):
        self._voc_algorithm = GasIndexAlgorithm(ALGORITHM_TYPE_VOC)
        self._nox_algorithm = GasIndexAlgorithm(ALGORITHM_TYPE_NOX)
        self._algorithm_sample_count = 0

    def _initialize(self):
        self._resolveAdapter()
        serial = self._command(self.SERIAL_COMMAND, delay=0.001, words=3)
        self.serialNumber = "%04X%04X%04X" % tuple(serial)
        self._conditioning_count = 0
        self._reset_algorithms()
        self._offline_message = None

    def _publishMetadata(self):
        self._publishI2CMetadata(
            "SGP41", self.ADDRESS,
            {"sensorSerialNumber": self.serialNumber})

    def _sample(self):
        arguments = self._compensation()
        if self._conditioning_count < self.CONDITIONING_SECONDS:
            voc = self._command(self.CONDITIONING_COMMAND, arguments)[0]
            self._conditioning_count += 1
            return voc, None
        return tuple(self._command(self.MEASURE_COMMAND, arguments, words=2))

    def _poll(self, generation):
        poll_started = time.monotonic()
        with self._lock:
            if generation != self._generation or self._state != "attached":
                return
            try:
                if self.serialNumber is None:
                    self._initialize()
                self._publishMetadata()
                voc, nox = self._sample()
                voc_index = self._voc_algorithm.process(voc)
                nox_index = self._nox_algorithm.process(
                    nox if nox is not None else 0)
                self._algorithm_sample_count += 1
                self.indigoDevice.updateStateOnServer("rawVoc", value=voc)
                self.indigoDevice.updateStateOnServer(
                    "vocIndex", value=voc_index)
                self.indigoDevice.updateStateOnServer(
                    "noxIndex", value=nox_index)
                self.indigoDevice.updateStateOnServer(
                    "conditioning", value=nox is None,
                    uiValue=("conditioning (%d/10)" % self._conditioning_count
                             if nox is None else "ready"))
                if nox is not None:
                    self.indigoDevice.updateStateOnServer("rawNox", value=nox)
                self.indigoDevice.updateStateOnServer(
                    "indexStatus",
                    value=("ready" if voc_index or nox_index else "warming up"),
                    uiValue=("ready" if voc_index or nox_index else
                             "warming up (%d s)" % self._algorithm_sample_count))
                self.indigoDevice.updateStateOnServer(
                    "compensationHumidity", value=self._actual_humidity)
                self.indigoDevice.updateStateOnServer(
                    "compensationTemperature", value=self._actual_temperature)
                self.indigoDevice.updateStateOnServer(
                    "compensationStatus",
                    value=("fallback" if self._compensation_issue else "configured"))
                if self._offline_message is not None:
                    self.logger.info("SGP41 recovered: device='%s'", self.indigoDevice.name)
                    self._offline_message = None
                self.indigoDevice.setErrorStateOnServer(None)
            except PeripheralUnavailableError as error:
                message = str(error)
                if message != self._offline_message:
                    self.logger.error("Configured peripheral unavailable: device='%s': %s",
                                      self.indigoDevice.name, message)
                    self._offline_message = message
                self.indigoDevice.setErrorStateOnServer("No response at 0x59")
            except Exception:
                self.logger.error("SGP41 poll failed: device='%s'\n%s",
                                  self.indigoDevice.name, traceback.format_exc())
                self.indigoDevice.setErrorStateOnServer("I2C read failed")
            if generation == self._generation and self._state == "attached":
                elapsed = time.monotonic() - poll_started
                self._schedulePoll(generation, max(0.0, 1.0 - elapsed))

    def start(self):
        with self._lock:
            adapter = self._resolveAdapter()
            if getattr(adapter, "_state", None) != "attached":
                self._state = "starting"
                return
            # Indigo may retain the previous device type's dynamic states while
            # a copied device is being saved. Install the SGP41 state list before
            # the synchronous first poll publishes any values.
            self.indigoDevice.stateListOrDisplayStateIdChanged()
            self._generation += 1
            self._state = "attached"
            self._poll(self._generation)

    def providerReattached(self):
        with self._lock:
            self.serialNumber = None
            self._conditioning_count = 0
            self.indigoDevice.stateListOrDisplayStateIdChanged()
            self._generation += 1
            self._state = "attached"
            self._poll(self._generation)

    def stop(self):
        self.providerStopping()
        if self.adapter is not None and getattr(self.adapter, "_state", None) == "attached":
            try:
                self.adapter.i2cSendReceive(self.ADDRESS, self.HEATER_OFF_COMMAND, 0)
            except Exception:
                self.logger.debug("Unable to turn off SGP41 heater during shutdown")
        self._state = "stopped"

    def _identity(self):
        return "device='%s' id=%s type=SGP41 adapter=%s address=0x59" % (
            self.indigoDevice.name, self.indigoDevice.id, self.adapterDeviceId)

    def getDeviceStateList(self):
        states = indigo.List()
        for state_id, label in (("vocIndex", "VOC Index"),
                                ("noxIndex", "NOx Index"),
                                ("rawVoc", "Raw VOC signal"),
                                ("rawNox", "Raw NOx signal"),
                                ("compensationHumidity", "Compensation humidity"),
                                ("compensationTemperature", "Compensation temperature")):
            states.append(self.indigo_plugin.getDeviceStateDictForNumberType(
                state_id, label, state_id))
        for state_id, label in (
                ("conditioning", "NOx conditioning"),
                ("indexStatus", "Gas index status"),
                ("compensationStatus", "Compensation status")):
            states.append(self.indigo_plugin.getDeviceStateDictForStringType(
                state_id, label, state_id))
        for state_id, label in (("sensorModel", "Sensor model"),
                                ("i2cAddress", "I2C address"),
                                ("sensorSerialNumber", "Sensor serial number")):
            states.append(self.indigo_plugin.getDeviceStateDictForStringType(
                state_id, label, state_id))
        return states

    def getDeviceDisplayStateId(self):
        return self.displayState
