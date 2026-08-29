# -*- coding: utf-8 -*-

"""Sensirion SGP41 VOC/NOx sensor on a shared ADP0001 I2C bus."""

import threading
import traceback

import indigo

from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException
from phidget import PeripheralUnavailableError


class SGP41Phidget(object):
    ADDRESS = 0x59
    CONDITIONING_COMMAND = b"\x26\x12"
    MEASURE_COMMAND = b"\x26\x19"
    SERIAL_COMMAND = b"\x36\x82"
    HEATER_OFF_COMMAND = b"\x36\x15"
    CONDITIONING_SECONDS = 10

    def __init__(self, adapterDeviceId, relativeHumidity=50.0,
                 temperature=25.0, indigo_plugin=None, indigoDevice=None,
                 logger=None, channelInfo=None, **kwargs):
        self.adapterDeviceId = int(adapterDeviceId)
        self.relativeHumidity = float(relativeHumidity)
        self.temperature = float(temperature)
        self.indigo_plugin = indigo_plugin
        self.indigoDevice = indigoDevice
        self.logger = logger
        self.channelInfo = channelInfo
        self.adapter = None
        self.serialNumber = None
        self._conditioning_count = 0
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

    def _resolveAdapter(self):
        adapter = self.indigo_plugin.activePhidgets.get(self.adapterDeviceId)
        if adapter is None or not adapter.supportsFunction("sgp41"):
            raise RuntimeError("The selected I2C adapter is not active")
        self.adapter = adapter
        self.channelInfo = adapter.channelInfo
        return adapter

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

    def _compensation(self):
        humidity = round(max(0.0, min(100.0, self.relativeHumidity)) * 65535.0 / 100.0)
        temperature = round((max(-45.0, min(130.0, self.temperature)) + 45.0) *
                            65535.0 / 175.0)
        return self._word(humidity) + self._word(temperature)

    def _initialize(self):
        self._resolveAdapter()
        serial = self._command(self.SERIAL_COMMAND, delay=0.001, words=3)
        self.serialNumber = "%04X%04X%04X" % tuple(serial)
        self._conditioning_count = 0
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
                     adapter_states.get("connection") or self.adapter.indigoDevice.name)
        publish("connectionPath", "%s→SGP41 0x59" % base_path)
        publish("sensorModel", "SGP41")
        publish("i2cAddress", "0x59")
        publish("sensorSerialNumber", self.serialNumber)

    def _sample(self):
        arguments = self._compensation()
        if self._conditioning_count < self.CONDITIONING_SECONDS:
            voc = self._command(self.CONDITIONING_COMMAND, arguments)[0]
            self._conditioning_count += 1
            return voc, None
        return tuple(self._command(self.MEASURE_COMMAND, arguments, words=2))

    def _poll(self, generation):
        with self._lock:
            if generation != self._generation or self._state != "attached":
                return
            try:
                if self.serialNumber is None:
                    self._initialize()
                self._publishMetadata()
                voc, nox = self._sample()
                self.indigoDevice.updateStateOnServer("rawVoc", value=voc)
                self.indigoDevice.updateStateOnServer(
                    "conditioning", value=nox is None,
                    uiValue=("conditioning (%d/10)" % self._conditioning_count
                             if nox is None else "ready"))
                if nox is not None:
                    self.indigoDevice.updateStateOnServer("rawNox", value=nox)
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
                timer = threading.Timer(1.0, self._poll, (generation,))
                timer.daemon = True
                self._timer = timer
                timer.start()

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

    def providerStopping(self):
        with self._lock:
            self._generation += 1
            self._state = "detached"
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def stop(self):
        self.providerStopping()
        if self.adapter is not None and getattr(self.adapter, "_state", None) == "attached":
            try:
                self.adapter.i2cSendReceive(self.ADDRESS, self.HEATER_OFF_COMMAND, 0)
            except Exception:
                self.logger.debug("Unable to turn off SGP41 heater during shutdown")
        self._state = "stopped"

    def serverKey(self):
        return self.adapter.serverKey() if self.adapter is not None else "local"

    def serverDisplayName(self):
        return self.adapter.serverDisplayName() if self.adapter is not None else "I2C adapter"

    def _identity(self):
        return "device='%s' id=%s type=SGP41 adapter=%s address=0x59" % (
            self.indigoDevice.name, self.indigoDevice.id, self.adapterDeviceId)

    def getDeviceStateList(self):
        states = indigo.List()
        for state_id, label in (("rawVoc", "Raw VOC signal"),
                                ("rawNox", "Raw NOx signal")):
            states.append(self.indigo_plugin.getDeviceStateDictForNumberType(
                state_id, label, state_id))
        states.append(self.indigo_plugin.getDeviceStateDictForStringType(
            "conditioning", "NOx conditioning", "conditioning"))
        for state_id, label in (("sensorModel", "Sensor model"),
                                ("i2cAddress", "I2C address"),
                                ("sensorSerialNumber", "Sensor serial number")):
            states.append(self.indigo_plugin.getDeviceStateDictForStringType(
                state_id, label, state_id))
        return states

    def getDeviceDisplayStateId(self):
        return "rawVoc"
