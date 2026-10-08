import pathlib
import sys
import types
import unittest
from unittest import mock

SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / 'Phidgets22.indigoPlugin' / 'Contents' / 'Server Plugin'
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault('indigo', types.ModuleType('indigo'))
import voltageratioinput
from Phidget22.DeviceID import DeviceID
from Phidget22.BridgeGain import BridgeGain


class BridgeTests(unittest.TestCase):
    def wrapper(self, gain=128):
        channel = mock.Mock()
        channel.getDeviceID.return_value = DeviceID.PHIDID_DAQ1500
        channel.getMinDataInterval.return_value = 20
        channel.getMaxDataInterval.return_value = 60000
        channel.getMinVoltageRatioChangeTrigger.return_value = 0
        channel.getMaxVoltageRatioChangeTrigger.return_value = 1
        with mock.patch.object(voltageratioinput, 'VoltageRatioInput', return_value=channel):
            wrapper = voltageratioinput.VoltageRatioInputPhidget(
                sensorType=0, dataInterval=1000, voltageRatioChangeTrigger=0,
                sensorValueChangeTrigger=0, customState=None, customFormula=None,
                bridgeGain=gain, indigoDevice=mock.Mock(pluginProps={}),
                indigo_plugin=mock.Mock(pluginPrefs={}), logger=mock.Mock())
        return wrapper, channel

    def test_supported_gains_and_reconnect(self):
        for gain, expected in ((1, BridgeGain.BRIDGE_GAIN_1), (2, BridgeGain.BRIDGE_GAIN_2),
                               (64, BridgeGain.BRIDGE_GAIN_64), (128, BridgeGain.BRIDGE_GAIN_128)):
            with self.subTest(gain=gain):
                wrapper, channel = self.wrapper(gain)
                wrapper.configureAttachedPhidget(channel)
                wrapper.configureAttachedPhidget(channel)
                self.assertEqual(channel.setBridgeGain.call_args_list, [mock.call(expected)] * 2)
                channel.setSensorType.assert_not_called()
                channel.setSensorValueChangeTrigger.assert_not_called()
                channel.setDataInterval.assert_called_with(1000)
                channel.setVoltageRatioChangeTrigger.assert_called_with(0)

    def test_other_hardware_keeps_existing_configuration(self):
        wrapper, channel = self.wrapper()
        channel.getDeviceID.return_value = -1
        wrapper.configureAttachedPhidget(channel)
        channel.setBridgeGain.assert_not_called()
        channel.setSensorType.assert_called_once_with(0)
        channel.setSensorValueChangeTrigger.assert_called_once_with(0)

    def test_bad_gain_or_sensor_fails_before_hardware_configuration(self):
        for gain, sensor in ((4, 0), (128, 1101)):
            wrapper, channel = self.wrapper(gain)
            wrapper.sensorType = sensor
            with self.assertRaises(ValueError):
                wrapper.configureAttachedPhidget(channel)
            channel.setBridgeGain.assert_not_called()
            channel.setDataInterval.assert_not_called()

    def test_gain_failure_is_reported_at_attach_boundary(self):
        wrapper, channel = self.wrapper()
        channel.setBridgeGain.side_effect = RuntimeError('gain write failed')
        wrapper._state = "starting"
        wrapper.onAttachHandler(channel)
        wrapper.indigoDevice.setErrorStateOnServer.assert_called_with('Initialization failed')
        wrapper.logger.error.assert_called_once()
        self.assertIn('gain write failed', str(wrapper.logger.error.call_args))
        self.assertIn('setBridgeGain', str(wrapper.logger.error.call_args))
        wrapper.updateStateOnServer = mock.Mock()
        wrapper.setOnVoltageRatioChangeHandler(channel, 0.001)
        wrapper.updateStateOnServer.assert_not_called()
        channel.setDataInterval.assert_not_called()

    def calibrated_settings(self):
        import bridge
        values = dict(isDAQ1500=True, bridgeCalibrated=True, bridgeScale='10000',
                      bridgeOffset='-0.0001', bridgeUnits='kg', bridgeCalibrationUnits='kg',
                      serverName='ScaleServer', serialNumber='742134', hubPort='2',
                      channel='0', bridgeGain='128', bridgeEnabled=True)
        values['bridgeCalibrationSignature'] = bridge.signature(values)
        return values

    def test_calibration_math_and_invalid_points(self):
        import bridge
        scale, offset = bridge.calibration(0.0001, 0.0006, 5)
        self.assertAlmostEqual(scale, 10000)
        self.assertEqual(offset, -0.0001)
        scale, offset = bridge.calibration(0.0006, 0.0001, 5)
        self.assertAlmostEqual((0.0001 + offset) * scale, 5)
        for points in ((0, 0, 5), (0, 1, 0), (0, 1, -1), (float('nan'), 1, 1),
                       (0, float('inf'), 1), (0, 1e-320, 1e308)):
            with self.subTest(points=points), self.assertRaises(ValueError):
                bridge.calibration(*points)

    def test_calibration_validation_rejects_changed_identity_gain_units_and_formula(self):
        import bridge
        settings = self.calibrated_settings()
        self.assertEqual(bridge.validate(settings), {})
        for key, value in (('channel', '1'), ('hubPort', '3'), ('serverName', 'Other'),
                           ('bridgeGain', '64'), ('bridgeUnits', 'g'),
                           ('bridgeScale', '0'), ('bridgeOffset', 'nan'),
                           ('useCustomFormula', True), ('isDAQ1500', False)):
            with self.subTest(key=key):
                changed = dict(settings, **{key: value})
                self.assertTrue(bridge.validate(changed))

    def test_live_capture_calibration_and_tare_are_staged_until_save(self):
        import bridge
        from runtime_registry import RuntimeDeviceRegistry
        wrapper, channel = self.wrapper()
        saved = self.calibrated_settings()
        saved['bridgeCalibrated'] = False
        wrapper.indigoDevice.pluginProps = dict(saved)
        wrapper._state = 'attached'
        wrapper._isBridge = True
        wrapper._bridgeConfigured = True
        wrapper._bridgeReadingError = None
        channel.getBridgeEnabled.return_value = True
        channel.getBridgeGain.return_value = BridgeGain.BRIDGE_GAIN_128
        channel.getVoltageRatio.side_effect = [0.0001, 0.0006, 0.0002]
        host = bridge.BridgeUiMixin()
        host.runtimeRegistry = RuntimeDeviceRegistry()
        host.runtimeRegistry.register(42, wrapper)
        host.logger = mock.Mock()
        dialog = dict(saved, bridgeKnownWeight='5')
        host.bridgeCaptureZero(dialog, 'voltageRatioInput', 42)
        host.bridgeCalibrate(dialog, 'voltageRatioInput', 42)
        self.assertTrue(dialog['bridgeCalibrated'])
        self.assertEqual(bridge.validate(dialog), {})
        self.assertAlmostEqual(float(dialog['bridgeScale']), 10000)
        host.bridgeTare(dialog, 'voltageRatioInput', 42)
        self.assertEqual(float(dialog['bridgeOffset']), -0.0002)
        self.assertEqual(wrapper.indigoDevice.pluginProps, saved)
        wrapper.indigoDevice.replacePluginPropsOnServer.assert_not_called()
        host.logger.error.assert_not_called()
        host.bridgeClearCalibration(dialog, 'voltageRatioInput', 42)
        self.assertFalse(dialog['bridgeCalibrated'])

    def test_capture_rejects_unsaved_channel_and_preserves_calibration_on_error(self):
        import bridge
        from runtime_registry import RuntimeDeviceRegistry
        wrapper, channel = self.wrapper()
        saved = self.calibrated_settings()
        wrapper.indigoDevice.pluginProps = saved
        host = bridge.BridgeUiMixin()
        host.logger = mock.Mock()
        host.runtimeRegistry = RuntimeDeviceRegistry()
        host.runtimeRegistry.register(42, wrapper)
        dialog = dict(saved, channel='1')
        host.bridgeCaptureZero(dialog, 'voltageRatioInput', 42)
        self.assertIn('Save the channel', dialog['bridgeCalibrationStatus'])
        self.assertEqual(dialog['bridgeOffset'], saved['bridgeOffset'])
        channel.getVoltageRatio.assert_not_called()

    def test_reading_rejects_detach_disable_errors_and_external_gain_change(self):
        wrapper, channel = self.wrapper()
        wrapper._isBridge = True
        wrapper._bridgeConfigured = True
        wrapper._state = 'attached'
        wrapper._bridgeReadingError = None
        channel.getBridgeEnabled.return_value = True
        channel.getBridgeGain.return_value = BridgeGain.BRIDGE_GAIN_128
        channel.getVoltageRatio.return_value = 0.0001
        self.assertEqual(wrapper.readBridgeRatio(), 0.0001)
        wrapper._bridgeReadingError = 'Saturation'
        with self.assertRaisesRegex(ValueError, 'Saturation'):
            wrapper.readBridgeRatio()
        wrapper._bridgeReadingError = None
        channel.getBridgeGain.return_value = BridgeGain.BRIDGE_GAIN_64
        with self.assertRaisesRegex(ValueError, 'Hardware gain changed'):
            wrapper.readBridgeRatio()
        channel.getBridgeEnabled.return_value = False
        with self.assertRaisesRegex(ValueError, 'Enable'):
            wrapper.readBridgeRatio()
        wrapper._state = 'detached'
        with self.assertRaisesRegex(ValueError, 'attached'):
            wrapper.readBridgeRatio()

    def test_calibrated_weight_and_raw_ratio_are_published(self):
        wrapper, channel = self.wrapper()
        wrapper._isBridge = True
        wrapper._bridgeConfigured = True
        wrapper.bridgeCalibrated = True
        wrapper.bridgeScale = 10000
        wrapper.bridgeOffset = -0.0001
        wrapper.updateStateOnServer = mock.Mock()
        wrapper.setOnVoltageRatioChangeHandler(channel, 0.0006)
        self.assertAlmostEqual(wrapper.updateStateOnServer.call_args.kwargs['value'], 5)
        self.assertEqual(wrapper.updateStateOnServer.call_args.args, ('weight',))
        self.assertEqual(wrapper.updateStateOnServer.call_args_list[0].args, ('voltageRatio',))
        self.assertEqual(wrapper.getDeviceDisplayStateId(), 'weight')
        wrapper.setOnVoltageRatioChangeHandler(channel, 0)
        self.assertEqual(wrapper.updateStateOnServer.call_args.kwargs['value'], -1)
        wrapper.updateStateOnServer.reset_mock()
        wrapper.setOnVoltageRatioChangeHandler(channel, float('nan'))
        wrapper.updateStateOnServer.assert_not_called()
        wrapper.logger.error.assert_called_once()

    def test_disabled_bridge_is_restored_on_attach_and_does_not_publish(self):
        wrapper, channel = self.wrapper()
        wrapper.bridgeEnabled = False
        wrapper.configureAttachedPhidget(channel)
        channel.setBridgeEnabled.assert_called_once_with(False)
        wrapper.updateStateOnServer = mock.Mock()
        wrapper.setOnVoltageRatioChangeHandler(channel, 0.001)
        wrapper.updateStateOnServer.assert_not_called()

    def test_saved_calibration_is_loaded_by_factory(self):
        import device_factory
        settings = self.calibrated_settings()
        settings.update(isVintHub=True, isVintDevice=True, dataInterval='1000', decimalPlaces='3')
        device = mock.Mock(pluginProps=settings)
        host = mock.Mock(pluginPrefs={})
        channel = mock.Mock()
        with mock.patch.object(voltageratioinput, 'VoltageRatioInput', return_value=channel):
            common = device_factory._common(host, device)
            wrapper = device_factory._voltage_ratio_input(host, device, common)
        self.assertTrue(wrapper.bridgeCalibrated)
        self.assertEqual(wrapper.bridgeGain, 128)
        self.assertEqual(wrapper.bridgeScale, 10000)
        self.assertEqual(wrapper.bridgeOffset, -0.0001)
        self.assertEqual(wrapper.channelInfo.channel, 0)
        self.assertEqual(wrapper.channelInfo.hubPort, 2)
        self.assertEqual(wrapper.getDeviceDisplayStateId(), 'weight')

    def test_bridge_error_blocks_capture_until_next_valid_reading(self):
        wrapper, channel = self.wrapper()
        wrapper._state = 'attached'
        wrapper._isBridge = True
        wrapper._bridgeConfigured = True
        channel.getBridgeEnabled.return_value = True
        channel.getBridgeGain.return_value = BridgeGain.BRIDGE_GAIN_128
        channel.getVoltageRatio.return_value = 0.0001
        wrapper.onErrorHandler(channel, 4105, 'Saturation detected')
        with self.assertRaisesRegex(ValueError, 'Saturation'):
            wrapper.readBridgeRatio()
        wrapper.setOnVoltageRatioChangeHandler(channel, 0.0001)
        self.assertEqual(wrapper.readBridgeRatio(), 0.0001)

    def test_connection_change_save_error_targets_visible_control_and_explains_recovery(self):
        import indigo
        from discovery_ui import DiscoveryUiMixin
        import xml.etree.ElementTree as ET
        ui = object.__new__(DiscoveryUiMixin)
        ui.discoveryInventory = None
        ui._validateNativeSettings = mock.Mock(return_value={})
        fields = {field.get('id'): field for field in ET.parse(SERVER_PLUGIN / 'Devices.xml')
                  .findall(".//Device[@id='voltageRatioInput']/ConfigUI/Field")}
        for key, value in (('serverName', 'MovedServer'), ('hubPort', '4'),
                           ('channel', '1'), ('bridgeGain', '64')):
            with self.subTest(changed=key), mock.patch.object(indigo, 'Dict', dict, create=True):
                values = dict(self.calibrated_settings(), **{key: value})
                valid, returned, errors = ui._validateChannelConfig(values, 'voltageRatioInput', 42)
                self.assertFalse(valid)
                self.assertNotIn('bridgeCalibrated', errors)
                self.assertIn('bridgeGain', errors)
                self.assertNotEqual(fields['bridgeGain'].get('hidden'), 'true')
                self.assertEqual(fields['bridgeGain'].get('visibleBindingId'), 'isDAQ1500')
                self.assertTrue(returned['isDAQ1500'])
                self.assertIn('Keep calibration for moved scale', errors['showAlertText'])
                self.assertIn('different load cell', errors['showAlertText'])
                self.assertEqual(returned['bridgeCalibrationStatus'], errors['showAlertText'])
                self.assertTrue(returned['bridgeCalibrated'])

    def test_non_bridge_calibration_error_targets_unconditional_control(self):
        import bridge
        import xml.etree.ElementTree as ET
        values = dict(self.calibrated_settings(), isDAQ1500=False)
        errors = bridge.validate(values)
        self.assertIn('discoveredServer', errors)
        self.assertNotIn('bridgeCalibrated', errors)
        field = ET.parse(SERVER_PLUGIN / 'Devices.xml').find(
            ".//Device[@id='voltageRatioInput']/ConfigUI/Field[@id='discoveredServer']")
        self.assertIsNone(field.get('visibleBindingId'))
        self.assertNotEqual(field.get('hidden'), 'true')

    def test_moved_scale_keeps_calibration_and_tare_without_opening_hardware(self):
        import bridge
        saved = self.calibrated_settings()
        moved = dict(saved, serverName='Coop', serialNumber='744571', hubPort='4')
        host = bridge.BridgeUiMixin()
        host.logger = mock.Mock()
        host._bridgeReading = mock.Mock(side_effect=AssertionError('Must not open hardware'))
        host.bridgeKeepCalibration(moved, 'voltageRatioInput', 42)
        self.assertEqual(bridge.validate(moved), {})
        for field in ('bridgeScale', 'bridgeOffset', 'bridgeUnits', 'bridgeCalibrated'):
            self.assertEqual(moved[field], saved[field])
        self.assertNotEqual(moved['bridgeCalibrationSignature'], saved['bridgeCalibrationSignature'])
        self.assertEqual(moved['bridgeZeroSignature'], '')
        host._bridgeReading.assert_not_called()
        host.logger.error.assert_not_called()

    def test_keep_calibration_rejects_gain_units_and_invalid_calibration(self):
        import bridge
        host = bridge.BridgeUiMixin()
        host.logger = mock.Mock()
        for changes in (dict(bridgeGain='64'), dict(bridgeUnits='kg', bridgeCalibrationUnits='g'),
                        dict(bridgeScale='0'), dict(bridgeCalibrated=False),
                        dict(bridgeCalibrationSignature='bad'), dict(isDAQ1500=False)):
            with self.subTest(changes=changes):
                moved = dict(self.calibrated_settings(), serverName='Coop', **changes)
                previous = moved['bridgeCalibrationSignature']
                host.bridgeKeepCalibration(moved, 'voltageRatioInput', 42)
                self.assertEqual(moved['bridgeCalibrationSignature'], previous)
                self.assertNotIn('retained', moved['bridgeCalibrationStatus'])
