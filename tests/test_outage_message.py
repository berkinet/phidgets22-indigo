import unittest
from test_phidget_lifecycle import phidget_module
from outage_message import outage_duration, reminder_cadence


class OutageMessageTests(unittest.TestCase):
    def test_elapsed_hours_do_not_wrap_at_one_day(self):
        self.assertEqual(outage_duration(10800), "03:00 hours/minutes")
        self.assertEqual(outage_duration(90060), "25:01 hours/minutes")

    def test_daily_transition_is_explicit(self):
        self.assertEqual(reminder_cadence(86399, True), "")
        self.assertIn("First daily reminder", reminder_cadence(86400, True))
        self.assertTrue(reminder_cadence(172800).startswith("Daily reminder"))
