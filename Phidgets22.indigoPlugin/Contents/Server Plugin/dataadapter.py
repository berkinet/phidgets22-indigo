# -*- coding: utf-8 -*-

"""Shared Phidget DataAdapter transport for I2C peripheral devices."""

import threading

import indigo

from Phidget22.Devices.DataAdapter import DataAdapter

from phidget import PhidgetBase


class DataAdapterPhidget(PhidgetBase):
    """Own one physical DataAdapter channel and serialize access to its bus."""

    def __init__(self, voltage, frequency, *args, **kwargs):
        super(DataAdapterPhidget, self).__init__(
            phidget=DataAdapter(), *args, **kwargs)
        self.voltage = int(voltage)
        self.frequency = int(frequency)
        self._transaction_lock = threading.RLock()

    def addPhidgetHandlers(self):
        self.phidget.setOnErrorHandler(self.onErrorHandler)
        self.phidget.setOnAttachHandler(self.onAttachHandler)
        self.phidget.setOnDetachHandler(self.onDetachHandler)

    def configureAttachedPhidget(self, ph):
        """Apply the settings shared by every peripheral on this I2C bus."""
        ph.setDataAdapterVoltage(self.voltage)
        ph.setFrequency(self.frequency)
        ph.getDataAdapterVoltage()
        ph.getFrequency()
        ph.getMaxSendPacketLength()
        ph.getMaxReceivePacketLength()
        for key, value in (
                ("adapterStatus", "I2C ready"),
                ("dataAdapterVoltage", int(ph.getDataAdapterVoltage())),
                ("dataAdapterFrequency", int(ph.getFrequency())),
                ("maxSendPacketLength", int(ph.getMaxSendPacketLength())),
                ("maxReceivePacketLength", int(ph.getMaxReceivePacketLength()))):
            self.indigoDevice.updateStateOnServer(key, value=value)

    def _validate_transaction(self, address, data, receive_length=None):
        if self._state != "attached":
            raise RuntimeError("I2C adapter '%s' is not attached" %
                               self.indigoDevice.name)
        address = int(address)
        if address < 0 or address > 0x7f:
            raise ValueError("I2C address must be a 7-bit value from 0x00 to 0x7F")
        payload = bytes(bytearray(data or ()))
        if len(payload) > int(self.phidget.getMaxSendPacketLength()):
            raise ValueError("I2C write exceeds the adapter's maximum packet length")
        if receive_length is not None:
            receive_length = int(receive_length)
            if receive_length < 0:
                raise ValueError("I2C receive length cannot be negative")
            if receive_length > int(self.phidget.getMaxReceivePacketLength()):
                raise ValueError("I2C read exceeds the adapter's maximum packet length")
        return address, payload, receive_length

    def i2cSendReceive(self, address, data=None, receiveLength=0):
        """Perform one atomic I2C write/read for a logical child device."""
        with self._transaction_lock:
            address, payload, receive_length = self._validate_transaction(
                address, data, receiveLength)
            return self.phidget.i2cSendReceive(
                address, payload, receive_length)

    def i2cComplexTransaction(self, address, packetString, data=None):
        """Perform a Phidget22 complex I2C transaction under the bus lock."""
        if not isinstance(packetString, str) or not packetString:
            raise ValueError("I2C packet description cannot be empty")
        with self._transaction_lock:
            address, payload, _ = self._validate_transaction(address, data)
            return self.phidget.i2cComplexTransaction(
                address, packetString, payload)

    def getDeviceStateList(self):
        states = indigo.List()
        states.append(self.indigo_plugin.getDeviceStateDictForStringType(
            "adapterStatus", "Adapter status", "adapterStatus"))
        for state_id, label in (
                ("dataAdapterVoltage", "Data adapter voltage"),
                ("dataAdapterFrequency", "Data adapter frequency"),
                ("maxSendPacketLength", "Maximum send packet length"),
                ("maxReceivePacketLength", "Maximum receive packet length")):
            states.append(self.indigo_plugin.getDeviceStateDictForNumberType(
                state_id, label, state_id))
        return states

    def getDeviceDisplayStateId(self):
        return "adapterStatus"
