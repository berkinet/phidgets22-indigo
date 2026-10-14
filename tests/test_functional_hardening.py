import pathlib
import sys
import types
import unittest
from unittest import mock
SERVER = pathlib.Path(__file__).parents[1] / 'Phidgets22.indigoPlugin/Contents/Server Plugin'
sys.path.insert(0, str(SERVER))
sys.modules.setdefault('indigo', types.ModuleType('indigo'))
from formula import Formula
from connection_identity import ChannelIdentity, ServerIdentity, same_phidget
from config_util import saved_positive_int


class FunctionalHardeningTests(unittest.TestCase):
    def test_formula_arity_is_checked_before_sampling(self):
        for expression in ('sin()', 'sin(1,2)', 'max()', 'max(1)', 'sqrt(1,2)', 'log(1,2,3)'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                Formula(expression)
        self.assertEqual(Formula('max(x,2)').evaluate(1), 2)
        self.assertEqual(Formula('log(8,2)').evaluate(0), 3)

    def test_fahrenheit_change_is_converted_to_sdk_celsius(self):
        import temperaturesensor
        channel = mock.Mock()
        device = types.SimpleNamespace(name='Temperature', id=1)
        plugin = types.SimpleNamespace(pluginPrefs={})
        with mock.patch.object(temperaturesensor, 'TemperatureSensor', return_value=channel):
            sensor = temperaturesensor.TemperatureSensorPhidget(
                None, 1000, 9, 'F', indigo_plugin=plugin, indigoDevice=device,
                logger=mock.Mock())
        self.assertEqual(sensor.temperatureChangeTrigger, 5)

    def test_vcp_sensor_types_publish_current_units(self):
        import sensortypes
        from Phidget22.VoltageSensorType import VoltageSensorType
        from Phidget22.Unit import Unit
        for name in ('SENSOR_TYPE_VCP4114', 'SENSOR_TYPE_VCP4115', 'SENSOR_TYPE_VCP4116'):
            value = getattr(VoltageSensorType, name, None)
            if value is not None:
                self.assertEqual(sensortypes.getVoltageSensorUnit(value), Unit.PHIDUNIT_AMPERE)

    def test_local_description_and_runtime_identity_agree(self):
        description = dict(serialNumber=100, hubPort=-1, isRemote=False,
                           channel=0, channelClass=5)
        wrapper = types.SimpleNamespace(channelInfo=types.SimpleNamespace(
            serialNumber=100, hubPort=-1, isHubPortDevice=False, channel=0,
            netInfo=types.SimpleNamespace(isRemote=False, serverName=None)))
        self.assertEqual(ChannelIdentity.from_description(description),
                         ChannelIdentity.from_wrapper(wrapper, 5))
        self.assertNotEqual(ServerIdentity(remote=True).key, ServerIdentity().key)

    def test_wildcard_and_named_definition_match_same_phidget_port(self):
        def wrapper(server, port):
            return types.SimpleNamespace(channelInfo=types.SimpleNamespace(
                serialNumber=623318, hubPort=port,
                netInfo=types.SimpleNamespace(isRemote=True, serverName=server)))
        self.assertTrue(same_phidget(wrapper(None, 1), wrapper('CM-Vin', 1)))
        self.assertFalse(same_phidget(wrapper(None, 0), wrapper('CM-Vin', 1)))
        self.assertFalse(same_phidget(wrapper('Other', 1), wrapper('CM-Vin', 1)))

    def test_malformed_saved_intervals_have_safe_nonzero_defaults(self):
        log = mock.Mock()
        for value in ('bad', '-1', '0', None):
            self.assertEqual(saved_positive_int({'interval':value}, 'interval', 3600, logger=log), 3600)
        self.assertEqual(saved_positive_int({'interval':'7200'}, 'interval', 3600), 7200)

    def test_legacy_local_channel_selection_is_normalized(self):
        import base64, json
        import discovery
        token = base64.urlsafe_b64encode(json.dumps(['channel',[None,100,-1,False,0,5]]).encode()).decode().rstrip('=')
        self.assertEqual(discovery._untoken(token, 'channel')[0], 'local')
