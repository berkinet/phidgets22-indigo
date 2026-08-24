import logging
import pathlib
import sys
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))

indigo = sys.modules.setdefault("indigo", types.ModuleType("indigo"))
indigo.List = list

import lcd
from Phidget22.ChannelSubclass import ChannelSubclass
from Phidget22.LCDFont import LCDFont
from Phidget22.LCDScreenSize import LCDScreenSize


class FakeLCD(object):
    dimensions = {
        LCDScreenSize.SCREEN_SIZE_1x8: (8, 1),
        LCDScreenSize.SCREEN_SIZE_2x16: (16, 2),
        LCDScreenSize.SCREEN_SIZE_4x20: (20, 4),
        LCDScreenSize.SCREEN_SIZE_64x128: (128, 64),
    }

    def __init__(self, subclass=ChannelSubclass.PHIDCHSUBCLASS_LCD_TEXT,
                 screen_size=LCDScreenSize.SCREEN_SIZE_NONE,
                 supports_sleeping=False):
        self.parent = None
        self.subclass = subclass
        self.screen_size = screen_size
        self.width, self.height = self.dimensions.get(screen_size, (0, 0))
        self.supports_sleeping = supports_sleeping
        self.sleeping = False
        self.auto_flush = True
        self.backlight = 0.0
        self.contrast = 0.0
        self.handlers = {}
        self.writes = []
        self.operations = []
        self.clear_count = 0
        self.flush_count = 0
        self.set_screen_sizes = []
        self.initialize_count = 0

    def __getattr__(self, name):
        if name.startswith("setOn") and name.endswith("Handler"):
            return lambda handler: self.handlers.__setitem__(name, handler)
        raise AttributeError(name)

    def getChannelSubclass(self):
        return self.subclass

    def getScreenSize(self):
        return self.screen_size

    def setScreenSize(self, value):
        self.screen_size = value
        self.width, self.height = self.dimensions[value]
        self.set_screen_sizes.append(value)

    def getWidth(self):
        return self.width

    def getHeight(self):
        return self.height

    def initialize(self):
        self.initialize_count += 1

    def setAutoFlush(self, value):
        self.auto_flush = value

    def getMinBacklight(self):
        return 0.0

    def getMaxBacklight(self):
        return 1.0

    def getBacklight(self):
        return self.backlight

    def setBacklight(self, value):
        self.backlight = value

    def getMinContrast(self):
        return 0.0

    def getMaxContrast(self):
        return 1.0

    def getContrast(self):
        return self.contrast

    def setContrast(self, value):
        self.contrast = value

    def getSleeping(self):
        if not self.supports_sleeping:
            raise RuntimeError("unsupported")
        return self.sleeping

    def setSleeping(self, value):
        if not self.supports_sleeping:
            raise RuntimeError("unsupported")
        self.sleeping = value

    def writeText(self, font, x, y, text):
        self.writes.append((font, x, y, text))
        self.operations.append(("write", x, y, text))

    def clear(self):
        self.clear_count += 1
        self.operations.append(("clear",))

    def flush(self):
        self.flush_count += 1
        self.operations.append(("flush",))


class FakePlugin(object):
    pluginPrefs = {"attachTimeout": "5", "suppressErrors": False}


class FakeTimer(object):
    instances = []

    def __init__(self, interval, callback, args=()):
        self.interval = interval
        self.callback = callback
        self.args = args
        self.daemon = False
        self.started = False
        self.cancelled = False
        self.__class__.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback(*self.args)


def make_wrapper(native, **overrides):
    settings = {
        "screenSize": LCDScreenSize.SCREEN_SIZE_NONE,
        "backlight": 0.75,
        "contrast": 0.4,
        "restoreInitialText": False,
        "initialText": "",
        "initialLines": [],
        "initialX": 0,
        "initialY": 0,
        "indigo_plugin": FakePlugin(),
        "indigoDevice": mock.Mock(name="indigoDevice", id=42),
        "logger": logging.getLogger("test.lcd"),
    }
    settings.update(overrides)
    with mock.patch.object(lcd, "LCD", return_value=native):
        return lcd.LCDPhidget(**settings)


class LCDTests(unittest.TestCase):
    def test_registers_lifecycle_handlers(self):
        native = FakeLCD()
        wrapper = make_wrapper(native)

        wrapper.addPhidgetHandlers()

        self.assertEqual(set(native.handlers), {
            "setOnErrorHandler", "setOnAttachHandler", "setOnDetachHandler"})

    def test_configures_text_adapter_and_restores_initial_text(self):
        native = FakeLCD()
        wrapper = make_wrapper(
            native,
            screenSize=LCDScreenSize.SCREEN_SIZE_2x16,
            restoreInitialText=True,
            initialText="Ready",
            initialX=1,
            initialY=0,
        )

        wrapper.configureAttachedPhidget(native)

        self.assertEqual(native.set_screen_sizes, [LCDScreenSize.SCREEN_SIZE_2x16])
        self.assertEqual(native.initialize_count, 1)
        self.assertFalse(native.auto_flush)
        self.assertEqual(native.backlight, 0.75)
        self.assertEqual(native.contrast, 0.4)
        self.assertEqual(native.writes, [(LCDFont.FONT_5x8, 1, 0, "Ready")])
        self.assertEqual(native.flush_count, 1)
        self.assertEqual(wrapper.lastText, "Ready")
        self.assertEqual((wrapper.screenWidth, wrapper.screenHeight), (16, 2))

    def test_writes_all_text_rows_and_clears_previous_contents(self):
        native = FakeLCD(screen_size=LCDScreenSize.SCREEN_SIZE_2x16)
        wrapper = make_wrapper(native)
        wrapper.configureAttachedPhidget(native)
        wrapper._state = "attached"

        wrapper.writeLines(["Flow 7.7 GPM", "38.6 gallons"])

        self.assertEqual(native.clear_count, 1)
        self.assertEqual(native.flush_count, 1)
        self.assertEqual(native.writes, [
            (LCDFont.FONT_5x8, 0, 0, "Flow 7.7 GPM"),
            (LCDFont.FONT_5x8, 0, 1, "38.6 gallons"),
        ])
        self.assertEqual(wrapper.lastText, "Flow 7.7 GPM\n38.6 gallons")

    def test_static_text_is_clipped_to_the_physical_row_width(self):
        native = FakeLCD(screen_size=LCDScreenSize.SCREEN_SIZE_2x16)
        logger = mock.Mock()
        wrapper = make_wrapper(native, logger=logger)
        wrapper.configureAttachedPhidget(native)
        wrapper._state = "attached"

        wrapper.writeLines(["This text is much too long", "Second row"])

        self.assertEqual(native.writes[-2:], [
            (LCDFont.FONT_5x8, 0, 0, "This text is muc"),
            (LCDFont.FONT_5x8, 0, 1, "Second row"),
        ])
        self.assertEqual(wrapper.lastText, "This text is muc\nSecond row")
        logger.warning.assert_called_once_with(
            "LCD %s text clipped: device='%s', line=%d, width=%d, "
            "original=%r, displayed=%r",
            "Static", wrapper.indigoDevice.name, 1, 16,
            "This text is much too long", "This text is muc")

    def test_marquee_scrolls_each_row_and_starting_again_replaces_it(self):
        native = FakeLCD(screen_size=LCDScreenSize.SCREEN_SIZE_2x16)
        wrapper = make_wrapper(native)
        wrapper.configureAttachedPhidget(native)
        wrapper._state = "attached"
        FakeTimer.instances = []

        with mock.patch.object(lcd.threading, "Timer", FakeTimer):
            wrapper.startAnimation(
                "marquee", ["ABCDEFGHIJKLMNOPQRSTUVWXYZ", "12345678901234567890"],
                interval=0.4, direction="left", gap=2)
            first_timer = FakeTimer.instances[-1]
            first_timer.fire()
            active_marquee_timer = FakeTimer.instances[-1]

            wrapper.startAnimation(
                "flash", ["Hello", "World"], ["Bye", "Now"], interval=1.0)
            writes_after_replacement = len(native.writes)
            active_marquee_timer.fire()

        self.assertTrue(first_timer.started)
        self.assertTrue(active_marquee_timer.cancelled)
        self.assertEqual(len(native.writes), writes_after_replacement)
        self.assertEqual(native.writes[:4], [
            (LCDFont.FONT_5x8, 0, 0, "ABCDEFGHIJKLMNOP"),
            (LCDFont.FONT_5x8, 0, 1, "1234567890123456"),
            (LCDFont.FONT_5x8, 0, 0, "BCDEFGHIJKLMNOPQ"),
            (LCDFont.FONT_5x8, 0, 1, "2345678901234567"),
        ])
        self.assertEqual(native.writes[-2:], [
            (LCDFont.FONT_5x8, 0, 0, "Hello           "),
            (LCDFont.FONT_5x8, 0, 1, "World           "),
        ])
        self.assertEqual(wrapper._animation_mode, "flash")

    def test_virtual_marquee_uses_all_rows_as_one_row_major_line(self):
        native = FakeLCD(screen_size=LCDScreenSize.SCREEN_SIZE_2x16)
        wrapper = make_wrapper(native)
        wrapper.configureAttachedPhidget(native)
        wrapper._state = "attached"
        FakeTimer.instances = []

        with mock.patch.object(lcd.threading, "Timer", FakeTimer):
            wrapper.startAnimation(
                "virtualMarquee", ["ABC"], interval=0.4,
                direction="left", gap=2)
            FakeTimer.instances[-1].fire()
            wrapper.startAnimation(
                "virtualMarquee", ["ABC"], interval=0.4,
                direction="right", gap=2)
            FakeTimer.instances[-1].fire()

        blank = " " * 16
        self.assertEqual(native.writes[:4], [
            (LCDFont.FONT_5x8, 0, 0, blank),
            (LCDFont.FONT_5x8, 0, 1, (" " * 15) + "A"),
            (LCDFont.FONT_5x8, 0, 0, blank),
            (LCDFont.FONT_5x8, 0, 1, (" " * 14) + "AB"),
        ])
        self.assertEqual(native.writes[-4:], [
            (LCDFont.FONT_5x8, 0, 0, "C" + (" " * 15)),
            (LCDFont.FONT_5x8, 0, 1, blank),
            (LCDFont.FONT_5x8, 0, 0, "BC" + (" " * 14)),
            (LCDFont.FONT_5x8, 0, 1, blank),
        ])
        self.assertEqual(
            wrapper._virtual_marquee_rows("ABC", 16, 2, 16, "left", 2),
            [(" " * 15) + "A", "BC" + (" " * 14)])
        self.assertEqual(
            wrapper._virtual_marquee_rows("ABC", 16, 2, 17, "right", 2),
            [(" " * 15) + "A", "BC" + (" " * 14)])
        self.assertEqual(native.clear_count, 4)
        self.assertEqual(native.flush_count, 4)
        self.assertEqual(
            [operation[0] for operation in native.operations],
            ["clear", "write", "write", "flush"] * 4)

    def test_flash_alternates_all_rows_together_and_stop_leaves_last_frame(self):
        native = FakeLCD(screen_size=LCDScreenSize.SCREEN_SIZE_2x16)
        logger = mock.Mock()
        wrapper = make_wrapper(native, logger=logger)
        wrapper.configureAttachedPhidget(native)
        wrapper._state = "attached"
        FakeTimer.instances = []

        with mock.patch.object(lcd.threading, "Timer", FakeTimer):
            wrapper.startAnimation(
                "flash", ["Temperature reading", "21 C"],
                ["Relative humidity reading", "48 percent"],
                interval=1.5)
            timer = FakeTimer.instances[-1]
            timer.fire()
            current_timer = FakeTimer.instances[-1]
            wrapper.stopAnimation()

        self.assertEqual(native.writes[:2], [
            (LCDFont.FONT_5x8, 0, 0, "Temperature read"),
            (LCDFont.FONT_5x8, 0, 1, "21 C            "),
        ])
        self.assertEqual(native.writes[-2:], [
            (LCDFont.FONT_5x8, 0, 0, "Relative humidit"),
            (LCDFont.FONT_5x8, 0, 1, "48 percent      "),
        ])
        self.assertTrue(current_timer.cancelled)
        self.assertEqual(wrapper._animation_mode, "off")
        self.assertEqual(logger.warning.call_count, 2)
        self.assertEqual(
            [call.args[1] for call in logger.warning.call_args_list],
            ["Flash set A", "Flash set B"])

    def test_graphic_lcd_uses_hardware_dimensions(self):
        native = FakeLCD(
            subclass=ChannelSubclass.PHIDCHSUBCLASS_LCD_GRAPHIC,
            screen_size=LCDScreenSize.SCREEN_SIZE_64x128,
            supports_sleeping=True,
        )
        wrapper = make_wrapper(native)

        wrapper.configureAttachedPhidget(native)

        self.assertEqual(native.set_screen_sizes, [])
        self.assertEqual(wrapper.lcdType, "graphic")
        self.assertEqual((wrapper.screenWidth, wrapper.screenHeight), (128, 64))
        self.assertTrue(wrapper._supportsSleeping)

    def test_write_clear_and_sleep_actions_update_hardware(self):
        native = FakeLCD(
            subclass=ChannelSubclass.PHIDCHSUBCLASS_LCD_GRAPHIC,
            screen_size=LCDScreenSize.SCREEN_SIZE_64x128,
            supports_sleeping=True,
        )
        wrapper = make_wrapper(native)
        wrapper.configureAttachedPhidget(native)
        wrapper._state = "attached"

        wrapper.writeText("Flow", 6, 10)
        wrapper.setSleeping(True)
        wrapper.clear()

        self.assertIn((LCDFont.FONT_5x8, 6, 10, "Flow"), native.writes)
        self.assertTrue(native.sleeping)
        self.assertEqual(native.clear_count, 1)
        self.assertEqual(wrapper.lastText, "")
        self.assertEqual(native.flush_count, 2)

    def test_write_rejects_coordinates_outside_screen(self):
        native = FakeLCD(screen_size=LCDScreenSize.SCREEN_SIZE_2x16)
        wrapper = make_wrapper(native)
        wrapper.configureAttachedPhidget(native)
        wrapper._state = "attached"

        with self.assertRaisesRegex(ValueError, "x position"):
            wrapper.writeText("No", 16, 0)
        with self.assertRaisesRegex(ValueError, "y position"):
            wrapper.writeText("No", 0, 2)

    def test_text_adapter_requires_screen_dimensions(self):
        native = FakeLCD()
        wrapper = make_wrapper(native)

        with self.assertRaisesRegex(ValueError, "Select the dimensions"):
            wrapper.configureAttachedPhidget(native)

    def test_sleep_action_falls_back_to_backlight_control(self):
        native = FakeLCD(screen_size=LCDScreenSize.SCREEN_SIZE_2x16)
        wrapper = make_wrapper(native)
        wrapper.configureAttachedPhidget(native)
        wrapper._state = "attached"

        wrapper.setSleeping(True)

        self.assertEqual(native.backlight, native.getMinBacklight())
        self.assertTrue(wrapper._emulatedSleeping)
        wrapper.indigoDevice.updateStateOnServer.assert_any_call(
            "sleeping", value=True)

        wrapper.setBacklight(0.6)
        wrapper.setSleeping(False)

        self.assertEqual(native.backlight, 0.6)
        self.assertFalse(wrapper._emulatedSleeping)
        wrapper.indigoDevice.updateStateOnServer.assert_any_call(
            "sleeping", value=False)


if __name__ == "__main__":
    unittest.main()
