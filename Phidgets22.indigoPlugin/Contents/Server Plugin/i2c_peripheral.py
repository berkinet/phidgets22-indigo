from Phidget22.PhidgetException import PhidgetException
from phidget import PeripheralUnavailableError
# -*- coding: utf-8 -*-

"""Common lifecycle and metadata behavior for logical I2C peripherals."""

import threading

from error_reporting import log_error, runtime_boundary, set_device_error, clear_faults, concise_error, reporter

from state_publisher import update_indigo_state
from runtime_registry import registry_for


class I2CPeripheralBase(object):
    def updateStateOnServer(self, key, value, **kwargs):
        update_indigo_state(self, key, value, **kwargs)

    def _resolveAdapter(self):
        adapter = registry_for(self.indigo_plugin).get(self.adapterDeviceId)
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
                self.updateStateOnServer(state_id, value=value)

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

    def _pollRecovered(self):
        if not set_device_error(self, None):
            return
        if self._offline_message is not None:
            if self.POLL_LABEL == 'SGP41':
                self.logger.info("SGP41 recovered: device='%s'", self.indigoDevice.name)
            else:
                self.logger.info("I2C environmental sensor recovered: device='%s' address=0x%02X",
                                 self.indigoDevice.name, self.address)
            self._offline_message = None
        if self._transport_error_count:
            self.logger.info(self.POLL_LABEL + " polling recovered after a transport error: device='%s'",
                             self.indigoDevice.name)
            self._transport_error_count = 0
            self._transport_error_code = None
        if getattr(self, '_unexpected_poll_error', False):
            self.logger.info("I2C polling recovered after an unexpected failure: device='%s'", self.indigoDevice.name)
            self._unexpected_poll_error = False
        clear_faults(self)

    def _handlePollFailure(self, error):
        if self._pollInterruptedByProviderDetach():
            return
        if isinstance(error, PeripheralUnavailableError):
            message = concise_error(error)
            log_error(self, "Configured peripheral unavailable: device='%s': %s",
                      self.indigoDevice.name, message)
            self._offline_message = message
            set_device_error(self, "No response at 0x%02X" % getattr(self, "address", getattr(self, "ADDRESS", 0)))
        elif isinstance(error, PhidgetException):
            code = int(error.code)
            if code != self._transport_error_code:
                self._transport_error_count = 0
                self._transport_error_code = code
            self._transport_error_count += 1
            detail = str(getattr(error, 'details', '')).strip() or str(error).strip()
            detail = detail.splitlines()[0] if detail else 'Phidget transport error'
            if self._transport_error_count == 1:
                self.logger.warning(self.POLL_LABEL +
                    " transport error 0x%02x; retrying on the next poll: device='%s' (%s)",
                    code, self.indigoDevice.name, detail)
            elif self._transport_error_count >= 3:
                reporter(self).report('error', ('poll-transport', code), self.POLL_LABEL +
                    " transport error 0x%02x on %d consecutive polls; retries remain active: device='%s' (%s)",
                    code, self._transport_error_count, self.indigoDevice.name, detail)
            set_device_error(self, "I2C transport error; retrying")
        else:
            self._unexpected_poll_error = True
            log_error(self, self.POLL_LABEL + " poll failed: device='%s': %s",
                      self.indigoDevice.name, error)
            set_device_error(self, "I2C read failed")

    def _schedulePoll(self, generation, interval):
        timer = threading.Timer(float(interval), self._pollSafely, (generation,))
        timer.daemon = True
        self._timer = timer
        timer.start()

    @runtime_boundary("I2C polling")
    def _pollSafely(self, generation):
        with self._lock:
            if generation != self._generation or self._state != "attached":
                return
            self._timer = None
        try:
            self._poll(generation)
        except Exception as error:
            log_error(self, "I2C poll callback failed: device='%s'; %s",
                      self.indigoDevice.name, error)
        finally:
            with self._lock:
                if (generation == self._generation and self._state == "attached" and
                        self._timer is None):
                    self._schedulePoll(generation, getattr(self, 'pollInterval', 1.0))

    def providerStopping(self):
        with self._lock:
            self._generation += 1
            self._state = "detached"
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()
        if getattr(self.indigo_plugin, "_shutting_down", False) is not True:
            set_device_error(self, "Provider unavailable")

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
