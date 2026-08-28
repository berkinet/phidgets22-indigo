import pathlib
import sys
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))

import i2c_lcd
from Phidget22.ErrorCode import ErrorCode
from Phidget22.PhidgetException import PhidgetException
from phidget import ChannelInfo


class FakeAdapter(object):
    def __init__(self):
        self.transactions = []
        self._state = "attached"

    def supportsFunction(self, function_id):
        return function_id == "lcd"

    def i2cSendReceive(self, address, data=None, receiveLength=0):
        self.transactions.append((address, bytes(data or ()), receiveLength))
        return b""


class I2CLCDTests(unittest.TestCase):
    def channel(self, screen_size=8, address=0x27, pin_mapping=None):
        adapter = FakeAdapter()
        plugin = types.SimpleNamespace(activePhidgets={42: adapter})
        parent = types.SimpleNamespace(indigo_plugin=plugin)
        channel = i2c_lcd.HD44780PCF8574Channel(
            42, screen_size=screen_size, address=address,
            pin_mapping=pin_mapping)
        channel.parent = parent
        channel.setOnAttachHandler(mock.Mock())
        channel.open()
        return channel, adapter

    def test_profile_uses_verified_freenove_geometry_address_and_mapping(self):
        channel, adapter = self.channel()

        with mock.patch.object(i2c_lcd.time, "sleep"):
            channel.initialize()

        self.assertEqual(channel.getWidth(), 20)
        self.assertEqual(channel.getHeight(), 4)
        self.assertTrue(adapter.transactions)
        self.assertTrue(all(transaction[0] == 0x27
                            for transaction in adapter.transactions))
        # First initialization nibble is 0x3 with backlight, then enable high,
        # then enable low: P4-P7 data, P2 enable, P3 backlight.
        self.assertEqual(adapter.transactions[0][1], b"8<8")

    def test_initialization_translates_nack_into_actionable_address_error(self):
        channel, adapter = self.channel(screen_size=5, address=0x26)
        adapter.i2cSendReceive = mock.Mock(
            side_effect=PhidgetException(ErrorCode.EPHIDGET_NACK))

        with mock.patch.object(i2c_lcd.time, "sleep"):
            with self.assertRaisesRegex(
                    i2c_lcd.PeripheralUnavailableError,
                    "No I2C display responded at 0x26.*address jumpers"):
                channel.initialize()

    def test_1602_uses_same_freenove_mapping_with_16x2_geometry(self):
        channel, adapter = self.channel(screen_size=5)
        channel.writeText(None, 0, 0, "Sixteen columns")
        channel.writeText(None, 0, 1, "Second row")

        with mock.patch.object(i2c_lcd.time, "sleep"):
            channel.flush()

        self.assertEqual(channel.getWidth(), 16)
        self.assertEqual(channel.getHeight(), 2)
        payload = b"".join(transaction[1]
                           for transaction in adapter.transactions[2:])
        triples = [payload[offset:offset + 3]
                   for offset in range(0, len(payload), 3)]
        commands = []
        for index in range(len(triples) - 1):
            high = triples[index][0] & 0xf0
            low = triples[index + 1][0] & 0xf0
            commands.append(high | (low >> 4))
        self.assertIn(0x80, commands)
        self.assertIn(0xc0, commands)
        self.assertNotIn(0x94, commands)

    def test_address_and_advanced_pin_mapping_are_configurable(self):
        mapping = {
            "rs": 7, "rw": 6, "enable": 5, "backlight": 4,
            "d4": 0, "d5": 1, "d6": 2, "d7": 3,
        }
        channel, adapter = self.channel(
            screen_size=5, address=0x3f, pin_mapping=mapping)

        with mock.patch.object(i2c_lcd.time, "sleep"):
            channel.initialize()

        self.assertTrue(all(transaction[0] == 0x3f
                            for transaction in adapter.transactions))
        # Nibble 0x3 maps to D4/P0 + D5/P1, with backlight/P4 and E/P5.
        self.assertEqual(adapter.transactions[0][1], bytes((0x13, 0x33, 0x13)))

    def test_complete_frame_uses_20x4_ddram_row_addresses(self):
        channel, adapter = self.channel()
        channel.writeText(None, 0, 0, "One")
        channel.writeText(None, 0, 1, "Two")

        with mock.patch.object(i2c_lcd.time, "sleep"):
            channel.flush()

        payloads = [transaction[1] for transaction in adapter.transactions]
        frame_bytes = b"".join(payloads[2:])
        triples = [frame_bytes[offset:offset + 3]
                   for offset in range(0, len(frame_bytes), 3)]
        # Each command byte is emitted as two three-state nibble writes. Verify
        # the four set-DDRAM-address commands 0x80, 0xC0, 0x94, and 0xD4.
        command_starts = []
        for index in range(len(triples) - 1):
            if len(triples[index]) == 3 and len(triples[index + 1]) == 3:
                high = triples[index][0] & 0xf0
                low = triples[index + 1][0] & 0xf0
                command_starts.append(high | (low >> 4))
        for command in (0x80, 0xc0, 0x94, 0xd4):
            self.assertIn(command, command_starts)
        self.assertLessEqual(max(len(payload) for payload in payloads), 127)
        self.assertLessEqual(len(adapter.transactions), 6)

    def test_backlight_and_sleep_are_supported_by_the_backpack(self):
        channel, adapter = self.channel()

        channel.setBacklight(0)
        self.assertEqual(adapter.transactions[-1][1], b"\x00")
        channel.setBacklight(1)
        self.assertEqual(adapter.transactions[-1][1], b"\x08")
        channel.setSleeping(True)

        self.assertTrue(channel.getSleeping())
        self.assertEqual(adapter.transactions[-1][1], b"\x00")

    def test_i2c_profile_runs_through_existing_lcd_contract(self):
        adapter = FakeAdapter()
        plugin = types.SimpleNamespace(
            activePhidgets={42: adapter}, pluginPrefs={"attachTimeout": "1"},
            triggerEvent=mock.Mock(), phidgetAttachCompleted=mock.Mock())
        device = mock.Mock()
        device.name = "Kitchen LCD"
        device.id = 99
        device.pluginProps = {}
        logger = mock.Mock()
        lcd = i2c_lcd.I2CLCDPhidget(
            adapterDeviceId=42, screenSize=8, backlight=1.0, contrast=0.5,
            restoreInitialText=False, initialText="", initialLines=[],
            initialX=0, initialY=0, indigo_plugin=plugin,
            channelInfo=ChannelInfo(), indigoDevice=device, logger=logger)

        with mock.patch.object(i2c_lcd.time, "sleep"):
            lcd.start()
            lcd.writeLines(["One", "Two", "Three", "Four"])

        self.assertEqual(lcd._state, "attached")
        self.assertEqual(lcd.screenWidth, 20)
        self.assertEqual(lcd.screenHeight, 4)
        self.assertEqual(lcd.lastText, "One\nTwo\nThree\nFour")
        self.assertTrue(adapter.transactions)
        lcd.stop()
        self.assertEqual(lcd._state, "stopped")

    def test_lcd_waits_until_shared_adapter_is_fully_attached(self):
        adapter = FakeAdapter()
        adapter._state = "starting"
        plugin = types.SimpleNamespace(
            activePhidgets={42: adapter}, pluginPrefs={"attachTimeout": "60"},
            triggerEvent=mock.Mock(), phidgetAttachCompleted=mock.Mock())
        device = mock.Mock()
        device.name = "Deferred LCD"
        device.id = 100
        device.pluginProps = {}
        lcd = i2c_lcd.I2CLCDPhidget(
            adapterDeviceId=42, screenSize=8, backlight=1.0, contrast=0.5,
            restoreInitialText=False, initialText="", initialLines=[],
            initialX=0, initialY=0, indigo_plugin=plugin,
            channelInfo=ChannelInfo(), indigoDevice=device, logger=mock.Mock())

        lcd.start()
        self.assertEqual(lcd._state, "starting")
        self.assertEqual(adapter.transactions, [])

        adapter._state = "attached"
        with mock.patch.object(i2c_lcd.time, "sleep"):
            self.assertTrue(lcd.providerReattached())

        self.assertEqual(lcd._state, "attached")
        self.assertTrue(adapter.transactions)
        lcd.stop()


if __name__ == "__main__":
    unittest.main()
