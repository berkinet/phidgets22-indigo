import copy
import json
import pathlib
import sys
import types
import unittest
from unittest import mock
from xml.etree import ElementTree

SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
sys.modules.setdefault("indigo", types.ModuleType("indigo"))
import indigo
import rfid_tags
from rfid import SimulatedRFIDPhidget
from rfid_ui import RFIDManagementMixin
from runtime_registry import RuntimeDeviceRegistry


class Collection(dict):
    def __iter__(self):
        return iter(self.values())


class TagManagementTests(unittest.TestCase):
    def setUp(self):
        self.variables = Collection({
            1: types.SimpleNamespace(id=1, name="Feeder A allowed", value="0001\n0002", readOnly=False),
            2: types.SimpleNamespace(id=2, name="Feeder A denied", value="0002\n0003", readOnly=False),
            3: types.SimpleNamespace(id=3, name="Feeder B allowed", value="0003", readOnly=False),
            4: types.SimpleNamespace(id=4, name="Feeder B denied", value="0001", readOnly=False),
        })
        self.api = mock.Mock()
        self.api.updateValue.side_effect = lambda var_id, value: setattr(self.variables[var_id], "value", value)
        self.patches = [mock.patch.object(indigo, "Dict", dict, create=True),
                        mock.patch.object(indigo, "variables", self.variables, create=True),
                        mock.patch.object(indigo, "variable", self.api, create=True),
                        mock.patch.object(indigo, "devices", Collection(), create=True)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.ui = RFIDManagementMixin()
        self.ui.pluginPrefs = {}
        self.ui.logger = mock.Mock()
        self.ui.runtimeRegistry = RuntimeDeviceRegistry()
        self.values = self.ui.initializeRFIDManagement({
            "rfidCheckAllowed": True, "rfidCheckDenied": True,
            "rfidAllowedVariable": "1", "rfidDeniedVariable": "2"})

    def stage(self, tag, operation="addAllowed", values=None):
        values = self.values if values is None else values
        values["rfidEditTag"], values["rfidEditOperation"] = tag, operation
        return self.ui.rfidStageEdit(values, "rfid", 10)

    def reader(self, device_id=10, props=None):
        device = types.SimpleNamespace(id=device_id, name="Reader %s" % device_id,
                                       pluginProps=props or {}, states={},
                                       setErrorStateOnServer=mock.Mock())
        indigo.devices[device_id] = device
        plugin = types.SimpleNamespace(pluginPrefs=self.ui.pluginPrefs, triggerEvent=mock.Mock())
        reader = SimulatedRFIDPhidget(indigoDevice=device, indigo_plugin=plugin, logger=mock.Mock())
        reader.updateStateOnServer = lambda key, value, **kwargs: device.states.__setitem__(key, value)
        reader.start()
        return reader

    def test_policy_truth_table_and_denial_wins(self):
        for allowed in (False, True):
            for denied in (False, True):
                props = dict(self.values, rfidCheckAllowed=allowed, rfidCheckDenied=denied)
                for tag in ("0001", "0002", "0003", "0004"):
                    with self.subTest(allowed=allowed, denied=denied, tag=tag):
                        expected = (not allowed or tag in ("0001", "0002")) and (not denied or tag not in ("0002", "0003"))
                        self.assertEqual(rfid_tags.evaluate(props, tag), expected)

    def test_empty_allow_list_denies_and_empty_deny_list_accepts(self):
        self.variables[1].value = ""
        self.variables[2].value = ""
        self.assertFalse(rfid_tags.evaluate(self.values, "0001"))
        self.assertTrue(rfid_tags.evaluate(dict(self.values, rfidCheckAllowed=False), "0001"))

    def test_exact_strings_and_live_variable_reads(self):
        self.assertFalse(rfid_tags.evaluate(self.values, "1"))
        self.assertTrue(rfid_tags.evaluate(self.values, "0001"))
        self.variables[2].value += "\n0001"
        self.assertFalse(rfid_tags.evaluate(self.values, "0001"))
        self.variables[1].value = "CaseSensitive"
        self.assertFalse(rfid_tags.evaluate(self.values, "casesensitive"))

    def test_independent_reader_policies(self):
        second = dict(self.values, rfidAllowedVariable="3", rfidDeniedVariable="4")
        self.assertTrue(rfid_tags.evaluate(self.values, "0001"))
        self.assertFalse(rfid_tags.evaluate(second, "0001"))
        self.assertFalse(rfid_tags.evaluate(self.values, "0003"))
        self.assertTrue(rfid_tags.evaluate(second, "0003"))

    def test_policy_events_see_complete_states_and_not_on_loss(self):
        reader = self.reader(props=self.values)
        observed = []
        reader.indigo_plugin.triggerEvent.side_effect = lambda source, event: observed.append((event, dict(source.indigoDevice.states)))
        reader.simulateTag("0001", 1)
        self.assertEqual([event for event, _ in observed], ["rfidTagDetected", "rfidAllowedTagDetected"])
        for _, states in observed:
            self.assertEqual(states["lastTag"], "0001")
            self.assertTrue(states["lastTagAllowed"])
            self.assertTrue(states["tagPresent"])
        reader.simulateTag()
        self.assertEqual(observed[-1][0], "rfidTagLost")
        self.assertTrue(reader.indigoDevice.states["lastTagAllowed"])
        reader.simulateTag("0002", 1)
        self.assertEqual(observed[-1][0], "rfidDeniedTagDetected")

    def test_missing_variable_fails_closed_but_raw_event_and_history_survive(self):
        reader = self.reader(props=self.values)
        del self.variables[1]
        reader.simulateTag("0001", 1)
        self.assertFalse(reader.indigoDevice.states["lastTagAllowed"])
        self.assertEqual(reader.indigoDevice.states["tagPolicyResult"], "Error")
        self.assertIn("missing", reader.indigoDevice.states["tagPolicyError"])
        reader.indigo_plugin.triggerEvent.assert_called_once_with(reader, "rfidTagDetected")
        self.assertEqual(rfid_tags.recent(self.ui, 10)[0]["tag"], "0001")
        self.assertFalse(reader.indigoDevice.states["presenceActive"])
        reader.logger.warning.assert_not_called()
        reader.logger.error.assert_called_once()
        message = reader.logger.error.call_args.args[0] % reader.logger.error.call_args.args[1:]
        for detail in ("RFID list check failed", "Reader 10", "0001", "EM4100", "missing"):
            self.assertIn(detail, message)

    def test_disabled_checks_ignore_missing_variable(self):
        self.assertTrue(rfid_tags.evaluate({"rfidAllowedVariable": "999"}, "0001"))

    def test_recent_history_is_bounded_unique_per_protocol_and_per_reader(self):
        for index in range(55):
            rfid_tags.remember(self.ui, 10, "%04d" % index, 1, "first")
        rfid_tags.remember(self.ui, 10, "0054", 1, "again")
        rfid_tags.remember(self.ui, 11, "other-reader", 3, "now")
        rows = rfid_tags.recent(self.ui, 10)
        self.assertEqual(len(rows), 50)
        self.assertEqual(rows[0]["seen"], "again")
        self.assertEqual(rows[-1]["tag"], "0005")
        rfid_tags.remember(self.ui, 10, "0054", 3, "different protocol")
        rows = rfid_tags.recent(self.ui, 10)
        self.assertEqual(len(rows), 50)
        self.assertEqual([(row["tag"], row["protocol"]) for row in rows[:2]],
                         [("0054", 3), ("0054", 1)])
        self.assertEqual(rows[1]["seen"], "again")
        restarted = types.SimpleNamespace(pluginPrefs=copy.deepcopy(self.ui.pluginPrefs))
        self.assertEqual(rfid_tags.recent(restarted, 10), rows)
        self.assertEqual(rfid_tags.recent(restarted, 11)[0]["tag"], "other-reader")

    def test_history_failure_does_not_suppress_detection(self):
        reader = self.reader(props=self.values)
        self.ui.pluginPrefs[rfid_tags.HISTORY_KEY] = "not json"
        reader.simulateTag("0001", 1)
        reader.indigo_plugin.triggerEvent.assert_called_with(reader, "rfidAllowedTagDetected")
        reader.logger.error.assert_called_once()

    def test_staging_and_validation_never_mutate_variables(self):
        self.stage("0009")
        self.assertEqual(rfid_tags.validate(self.values), {})
        self.api.updateValue.assert_not_called()
        self.assertNotIn("0009", self.variables[1].value)
        self.assertIn("Feeder A allowed", self.values["rfidEditStatus"])

    def test_cancel_discards_and_reopening_clears_pending(self):
        self.stage("0009")
        self.ui.closedDeviceConfigUi(self.values, True, "rfid", 10)
        self.api.updateValue.assert_not_called()
        reopened = self.ui.initializeRFIDManagement(dict(self.values))
        self.assertEqual(rfid_tags.pending(reopened), [])

    def test_save_merges_live_edits_preserves_zeroes_and_other_reader(self):
        self.stage("0009")
        self.variables[1].value += "\nnew-external-entry"
        self.ui.closedDeviceConfigUi(self.values, False, "rfid", 10)
        self.assertEqual(self.variables[1].value, "0001\n0002\nnew-external-entry\n0009")
        self.assertEqual(self.variables[3].value, "0003")
        self.api.updateValue.assert_called_once()

    def test_duplicate_add_does_not_write_or_normalize_other_list(self):
        self.variables[2].value = "0002\n0003\n\n"
        self.stage("0001")
        self.ui.closedDeviceConfigUi(self.values, False, "rfid", 10)
        self.api.updateValue.assert_not_called()

    def test_conflict_requires_explicit_move(self):
        result = self.stage("0003")
        self.assertIsInstance(result, tuple)
        self.assertIn("Move", result[1]["showAlertText"])
        self.assertEqual(rfid_tags.pending(self.values), [])
        self.stage("0003", "moveAllowed")
        self.ui.closedDeviceConfigUi(self.values, False, "rfid", 10)
        self.assertIn("0003", rfid_tags.entries(self.variables[1].value))
        self.assertNotIn("0003", rfid_tags.entries(self.variables[2].value))

    def test_remove_and_clear_pending_edits(self):
        self.stage("0001", "removeAllowed")
        self.ui.rfidClearEdits(self.values, "rfid", 10)
        self.ui.closedDeviceConfigUi(self.values, False, "rfid", 10)
        self.assertIn("0001", self.variables[1].value)
        self.stage("0001", "removeAllowed")
        self.ui.closedDeviceConfigUi(self.values, False, "rfid", 10)
        self.assertNotIn("0001", self.variables[1].value)

    def test_changed_destination_cannot_silently_redirect_pending_edits(self):
        self.stage("0009")
        self.values["rfidAllowedVariable"] = "3"
        errors = rfid_tags.validate(self.values)
        self.assertIn("selections changed", errors["showAlertText"])
        self.api.updateValue.assert_not_called()

    def test_invalid_settings_reject_same_missing_and_readonly_variables(self):
        for changes in ({"rfidDeniedVariable": "1"}, {"rfidAllowedVariable": "999"}):
            self.assertTrue(rfid_tags.validate(dict(self.values, **changes)))
        self.variables[1].readOnly = True
        self.assertTrue(rfid_tags.validate(self.values))
        self.assertNotIn(("1", "Feeder A allowed"), self.ui.getRFIDVariableList())

    def test_variable_deleted_before_save_reports_failure_without_writes(self):
        reader = self.reader(props=self.values)
        self.stage("0009")
        del self.variables[1]
        self.ui.closedDeviceConfigUi(self.values, False, "rfid", 10)
        self.api.updateValue.assert_not_called()
        self.ui.logger.error.assert_called_once()
        reader.indigoDevice.setErrorStateOnServer.assert_called_with("RFID list save failed; see log")

    def test_api_write_failure_reports_destination_and_possible_partial_save(self):
        reader = self.reader(props=self.values)
        # A move writes both lists. Exercise failure after one successful write,
        # since Indigo cannot update two variables as an atomic transaction.
        self.stage("0003", "moveAllowed")
        saved = []
        def write_then_fail(var_id, value):
            if saved:
                raise RuntimeError("server unavailable")
            saved.append(var_id)
            self.variables[var_id].value = value
        original = {key: var.value for key, var in self.variables.items()}
        self.api.updateValue.side_effect = write_then_fail
        self.ui.closedDeviceConfigUi(self.values, False, "rfid", 10)
        self.assertEqual(len(saved), 1)
        failed_id = self.api.updateValue.call_args.args[0]
        self.assertNotEqual(saved[0], failed_id)
        self.assertNotEqual(self.variables[saved[0]].value, original[saved[0]])
        self.assertEqual(self.variables[failed_id].value, original[failed_id])
        self.ui.logger.error.assert_called_once()
        message = self.ui.logger.error.call_args.args[0] % self.ui.logger.error.call_args.args[1:]
        self.assertIn(self.variables[failed_id].name, message)
        self.assertIn("Earlier list edits may have saved; review both variables", message)
        reader.indigoDevice.setErrorStateOnServer.assert_called_with("RFID list save failed; see log")

    def test_recent_menu_scopes_and_copies_id(self):
        rfid_tags.remember(self.ui, 10, "0001", 1, "today")
        rfid_tags.remember(self.ui, 11, "0009", 3, "today")
        menu = self.ui.getRFIDRecentTags(targetId=10)
        self.assertEqual(len(menu), 2)
        self.assertNotIn("0009", menu[1][1])
        self.values["rfidRecentTag"] = menu[1][0]
        self.ui.rfidRecentTagSelected(self.values, "rfid", 10)
        self.assertEqual(self.values["rfidEditTag"], "0001")
        self.assertIn("Allowed (Feeder A allowed): listed", self.values["rfidMembership"])

    def test_policy_save_does_not_restart_or_fire_events(self):
        reader = self.reader(props=self.values)
        reader.simulateTag("0001", 1)
        self.ui.runtimeRegistry.register(10, reader)
        before = types.SimpleNamespace(deviceTypeId="rfid", id=10, pluginProps=dict(self.values))
        after = types.SimpleNamespace(deviceTypeId="rfid", id=10, pluginProps=dict(self.values, rfidAllowedVariable="3"))
        reader.indigo_plugin.triggerEvent.reset_mock()
        self.assertFalse(self.ui.didDeviceCommPropertyChange(before, after))
        reader.indigo_plugin.triggerEvent.assert_not_called()
        self.assertTrue(reader.indigoDevice.states["tagPresent"])
        reader.simulateTag()
        reader.simulateTag("0001", 1)
        self.assertFalse(reader.indigoDevice.states["lastTagAllowed"])
        after.pluginProps["rfidSimulation"] = True
        self.assertTrue(self.ui.didDeviceCommPropertyChange(before, after))

    def test_all_buttons_have_indigo_titles_and_callbacks(self):
        root = ElementTree.parse(SERVER_PLUGIN / "Devices.xml")
        for field in root.findall("./Device[@id='rfid']/ConfigUI/Field[@type='button']"):
            self.assertTrue(field.findtext("Title"))
            self.assertTrue(hasattr(self.ui, field.findtext("CallbackMethod")))

    def test_recent_menu_ids_are_indigo_safe_and_round_trip_tag_text(self):
        # Indigo rejected the previous raw JSON IDs at runtime, despite a valid
        # history lookup. Include punctuation and Unicode to protect PhidgetTAG.
        for tag, protocol in (("0000123456", 1), ('hen "A" / é', 3)):
            rfid_tags.remember(self.ui, 10, tag, protocol, "today")
        menu = self.ui.getRFIDRecentTags(targetId=10)
        for token, _ in menu:
            self.assertRegex(token, r"^[A-Za-z0-9_]+$")
        for token, _ in menu[1:]:
            self.values["rfidRecentTag"] = token
            result = self.ui.rfidRecentTagSelected(self.values, "rfid", 10)
            self.assertEqual(result["rfidEditTag"], rfid_tags.history_selection(token)[0])
        self.assertEqual({rfid_tags.history_selection(token) for token, _ in menu[1:]},
                         {("0000123456", 1), ('hen "A" / é', 3)})

    def test_placeholders_are_valid_for_empty_and_failed_menus(self):
        menus = [self.ui.getRFIDRecentTags(targetId=99), self.ui.getRFIDVariableList()]
        self.ui.pluginPrefs[rfid_tags.HISTORY_KEY] = "broken"
        menus.append(self.ui.getRFIDRecentTags(targetId=10))
        with mock.patch.object(indigo, "variables", None):
            menus.append(self.ui.getRFIDVariableList())
        for menu in menus:
            for token, _ in menu:
                self.assertRegex(token, r"^[A-Za-z0-9_]+$")

    def test_unselected_variables_are_not_looked_up_or_treated_as_equal_lists(self):
        values = self.ui.initializeRFIDManagement({})
        self.assertEqual(values["rfidAllowedVariable"], "none")
        self.assertEqual(values["rfidDeniedVariable"], "none")
        self.assertEqual(rfid_tags.validate(values), {})
        self.assertTrue(rfid_tags.evaluate(values, "0001"))
        values["rfidCheckAllowed"] = True
        self.assertIn("rfidAllowedVariable", rfid_tags.validate(values))
        with self.assertRaises(ValueError):
            rfid_tags.evaluate(values, "0001")

    def test_stage_with_one_selected_variable_ignores_opposite_placeholder(self):
        values = self.ui.initializeRFIDManagement({"rfidAllowedVariable": "1"})
        self.stage("0009", "addAllowed", values)
        self.assertEqual(rfid_tags.validate(values), {})
        self.ui.closedDeviceConfigUi(values, False, "rfid", 10)
        self.assertIn("0009", self.variables[1].value)
        self.api.updateValue.assert_called_once()

    def test_rfid_static_menu_values_and_defaults_are_indigo_safe(self):
        root = ElementTree.parse(SERVER_PLUGIN / "Devices.xml")
        for field in root.findall("./Device[@id='rfid']/ConfigUI/Field[@type='menu']"):
            if field.get("id").startswith("rfid"):
                self.assertRegex(field.get("defaultValue"), r"^[A-Za-z0-9_]+$")
                for option in field.findall("./List/Option"):
                    self.assertRegex(option.get("value"), r"^[A-Za-z0-9_]+$")

    def test_old_saved_operation_is_migrated_to_valid_menu_id(self):
        values = self.ui.initializeRFIDManagement({"rfidEditOperation": "move:Denied"})
        self.assertEqual(values["rfidEditOperation"], "moveDenied")

    def test_denied_detection_logs_reader_tag_protocol_and_reason_once_per_visit(self):
        reader = self.reader(props=self.values)
        reader.simulateTag("0002", 1)
        reader.simulateTag("0002", 1)
        reader.logger.warning.assert_called_once()
        message = reader.logger.warning.call_args.args[0] % reader.logger.warning.call_args.args[1:]
        for detail in ("RFID tag denied", "Reader 10", "id=10", "0002", "EM4100", "listed in denied variable 'Feeder A denied'"):
            self.assertIn(detail, message)
        reader.simulateTag()
        self.assertEqual(reader.logger.warning.call_count, 1)
        reader.simulateTag("0002", 1)
        self.assertEqual(reader.logger.warning.call_count, 2)
        self.assertEqual(reader.indigoDevice.states["tagPolicyResult"], "Denied")
        reader.indigo_plugin.triggerEvent.assert_called_with(reader, "rfidDeniedTagDetected")
        reader.logger.error.assert_not_called()

    def test_not_allowlisted_logs_reason_and_allowed_tags_do_not_warn(self):
        reader = self.reader(props=self.values)
        reader.simulateTag("0001", 1)
        reader.logger.warning.assert_not_called()
        reader.simulateTag("0009", 3)
        reader.logger.warning.assert_called_once()
        message = reader.logger.warning.call_args.args[0] % reader.logger.warning.call_args.args[1:]
        self.assertIn("not listed in allowed variable 'Feeder A allowed'", message)
        self.assertIn("PhidgetTAG", message)
        self.assertIn("0009", message)

    def test_denial_reason_prioritizes_denied_list(self):
        allowed, reason = rfid_tags.evaluate_with_reason(self.values, "0003")
        self.assertFalse(allowed)
        self.assertEqual(reason, "listed in denied variable 'Feeder A denied'")
