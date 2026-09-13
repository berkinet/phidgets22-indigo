# -*- coding: utf-8 -*-

import logging
import pathlib
import sys
import types
import unittest
from unittest import mock

SERVER_PLUGIN = (pathlib.Path(__file__).parents[1] /
                 "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin")
sys.path.insert(0, str(SERVER_PLUGIN))

from state_publisher import update_indigo_state, update_indigo_states


class StatePublisherTests(unittest.TestCase):
    def test_first_value_is_silent_and_later_values_can_trigger(self):
        device = mock.Mock()
        owner = types.SimpleNamespace(indigoDevice=device)

        update_indigo_state(owner, "availability", "Online")
        update_indigo_state(owner, "availability", "Offline")

        self.assertEqual(device.updateStateOnServer.call_args_list, [
            mock.call("availability", value="Online", triggerEvents=False),
            mock.call("availability", value="Offline", triggerEvents=True),
        ])

    def test_bulk_publication_applies_ui_values_and_isolates_failures(self):
        device = mock.Mock(name="Device")
        device.name = "Device"
        device.id = 42
        device.updateStateOnServer.side_effect = [RuntimeError("missing"), None]
        owner = types.SimpleNamespace(indigoDevice=device)
        logger = mock.Mock(spec=logging.Logger)

        update_indigo_states(
            owner, {"missing": 1, "available": False}, logger,
            ui_values={"available": lambda value: "Yes" if value else "No"})

        device.updateStateOnServer.assert_has_calls([
            mock.call("missing", value=1, triggerEvents=False),
            mock.call("available", value=False, uiValue="No",
                      triggerEvents=False),
        ])
        logger.debug.assert_called_once()


if __name__ == "__main__":
    unittest.main()
