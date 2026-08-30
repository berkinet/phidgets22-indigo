# -*- coding: utf-8 -*-

"""Common lifecycle and metadata behavior for logical I2C peripherals."""

import threading


class I2CPeripheralBase(object):
    def _resolveAdapter(self):
        adapter = self.indigo_plugin.activePhidgets.get(self.adapterDeviceId)
        if adapter is None or not adapter.supportsFunction(self.PROVIDER_FUNCTION):
            raise RuntimeError("The selected I2C adapter is not active")
        self.adapter = adapter
        self.channelInfo = adapter.channelInfo
        return adapter

    def _publishI2CMetadata(self, model, address, extra=None):
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
                (base_path, model, int(address)))
        publish("sensorModel", model)
        publish("i2cAddress", "0x%02X" % int(address))
        for state_id, value in (extra or {}).items():
            publish(state_id, value)

    def _schedulePoll(self, generation, interval):
        timer = threading.Timer(float(interval), self._poll, (generation,))
        timer.daemon = True
        self._timer = timer
        timer.start()

    def providerStopping(self):
        with self._lock:
            self._generation += 1
            self._state = "detached"
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def _pollInterruptedByProviderDetach(self):
        """Quiesce a poll that raced the physical adapter detach callback."""
        if (self.adapter is None or
                getattr(self.adapter, "_state", None) == "attached"):
            return False
        self.providerStopping()
        return True

    def serverKey(self):
        return self.adapter.serverKey() if self.adapter is not None else "local"

    def serverDisplayName(self):
        return (self.adapter.serverDisplayName()
                if self.adapter is not None else "I2C adapter")
