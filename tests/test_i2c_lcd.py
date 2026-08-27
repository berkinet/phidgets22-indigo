import pathlib
import sys
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))

import i2c_lcd
from phidget import ChannelInfo


class FakeAdapter(object):
    def __init__(self):
        self.transactions = []

    def supportsFunction(self, function_id):
        return function_id == "lcd"

    def i2cSendReceive(self, address, data=None, receiveLength=0):
        self.transactions.append((address, bytes(data or ()), receiveLength))
        return b""


class I2CLCDTests(unittest.TestCase):
    def channel(self):
        adapter = FakeAdapter()
        plugin = types.SimpleNamespace(activePhidgets={42: adapter})
        parent = types.SimpleNamespace(indigo_plugin=plugin)
        channel = i2c_lcd.FreenoveLCD2004Channel(42)
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


if __name__ == "__main__":
    unittest.main()
