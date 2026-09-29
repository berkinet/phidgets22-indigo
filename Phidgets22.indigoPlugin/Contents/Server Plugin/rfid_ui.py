# -*- coding: utf-8 -*-
"""Per-reader RFID tag management in the Indigo device configuration."""
import json

import indigo
import rfid_tags
from runtime_registry import registry_for


class RFIDManagementMixin(object):
    def initializeRFIDManagement(self, values):
        values["rfidEditOperation"] = str(values.get("rfidEditOperation", "addAllowed")).replace(":", "")
        values["rfidPendingEdits"] = "[]"
        values["rfidEditStatus"] = "No pending list edits."
        values["rfidRecentTag"] = "none"
        for side in rfid_tags.SIDES:
            values["rfid" + side + "Variable"] = rfid_tags.selected_variable(values, side) or "none"
        values["rfidEditTag"] = ""
        values["rfidMembership"] = "Select a recent tag or enter an ID."
        return values

    def getRFIDVariableList(self, filter="", valuesDict=None, typeId="", targetId=0):
        try:
            return [("none", "Select a variable")] + sorted(
                [(str(var.id), var.name) for var in indigo.variables
                 if not getattr(var, "readOnly", False)], key=lambda row: row[1].lower())
        except Exception as error:
            self.logger.error("Unable to list RFID variables: %s", str(error).replace("\n", " "))
            return [("none", "Variables unavailable; see Indigo log")]

    def getRFIDRecentTags(self, filter="", valuesDict=None, typeId="", targetId=0):
        try:
            rows = rfid_tags.recent(self, targetId)
            return [("none", "Select a recent tag" if rows else "No recent tags for this reader")] + [
                (rfid_tags.history_token(row["tag"], row["protocol"]), "%s | %s | %s" %
                 (row["tag"], rfid_tags.PROTOCOLS.get(row["protocol"], str(row["protocol"])), row["seen"]))
                for row in rows]
        except Exception as error:
            self.logger.error("Unable to read RFID history for device %s: %s", targetId, str(error).replace("\n", " "))
            return [("none", "History unavailable; see Indigo log")]

    def rfidRecentTagSelected(self, valuesDict, typeId, devId):
        try:
            if valuesDict.get("rfidRecentTag") not in (None, "", "none"):
                valuesDict["rfidEditTag"] = rfid_tags.history_selection(valuesDict["rfidRecentTag"])[0]
            return self.rfidRefreshTags(valuesDict, typeId, devId)
        except Exception as error:
            valuesDict["rfidEditStatus"] = str(error)
            return valuesDict

    def rfidRefreshTags(self, valuesDict, typeId, devId):
        try:
            tag = str(valuesDict.get("rfidEditTag", "")).strip()
            memberships = []
            with rfid_tags.LOCK:
                projected = {str(var.id): rfid_tags.entries(value)
                             for var, value in rfid_tags.build_edits(valuesDict)}
                for side in rfid_tags.SIDES:
                    var_id = rfid_tags.selected_variable(valuesDict, side)
                    if var_id:
                        var = rfid_tags.variable(var_id)
                        contents = projected.get(var_id, rfid_tags.entries(var.value))
                        memberships.append("%s (%s): %s" %
                                           (side, var.name, "listed" if tag in contents else "not listed"))
            valuesDict["rfidMembership"] = "; ".join(memberships) or "Select list variables above."
        except Exception as error:
            valuesDict["rfidMembership"] = str(error)
        return valuesDict

    def rfidStageEdit(self, valuesDict, typeId, devId):
        try:
            operations = {kind + side: (kind, side)
                          for kind in ("add", "remove", "move") for side in rfid_tags.SIDES}
            operation = valuesDict.get("rfidEditOperation", "addAllowed").replace(":", "")
            if operation not in operations:
                raise ValueError("Select a list edit operation.")
            kind, side = operations[operation]
            tag = rfid_tags.tag_id(valuesDict.get("rfidEditTag", ""))
            opposite = "Denied" if side == "Allowed" else "Allowed"
            var_id = rfid_tags.selected_variable(valuesDict, side)
            rfid_tags.variable(var_id)
            edits = rfid_tags.pending(valuesDict)
            edits.append({"kind": kind, "side": side, "tag": tag, "variable": var_id,
                          "opposite": rfid_tags.selected_variable(valuesDict, opposite)})
            proposed = indigo.Dict(valuesDict)
            proposed["rfidPendingEdits"] = json.dumps(edits)
            with rfid_tags.LOCK:
                rfid_tags.build_edits(proposed)
            valuesDict["rfidPendingEdits"] = proposed["rfidPendingEdits"]
            valuesDict["rfidEditStatus"] = "; ".join(
                "%s %s: %s → variable %s" % (item["kind"].capitalize(), item["side"].lower(),
                                              item["tag"], rfid_tags.variable(item["variable"]).name)
                for item in edits) + ". Pending — Save applies; Cancel discards."
        except Exception as error:
            errors = indigo.Dict()
            errors["showAlertText"] = str(error)
            return (valuesDict, errors)
        return self.rfidRefreshTags(valuesDict, typeId, devId)

    def rfidClearEdits(self, valuesDict, typeId, devId):
        valuesDict["rfidPendingEdits"] = "[]"
        valuesDict["rfidEditStatus"] = "No pending list edits."
        return self.rfidRefreshTags(valuesDict, typeId, devId)

    def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):
        if userCancelled or typeId != "rfid":
            return
        try:
            errors = rfid_tags.validate(valuesDict)
            if errors:
                raise ValueError("; ".join(str(value) for value in errors.values()))
            rfid_tags.apply_edits(valuesDict)
        except Exception as error:
            self.logger.error("RFID tag list save failed for device %s: %s", devId, str(error).replace("\n", " "))
            try:
                indigo.devices[devId].setErrorStateOnServer("RFID list save failed; see log")
            except Exception as state_error:
                self.logger.error("Unable to report RFID list save error: %s", str(state_error).replace("\n", " "))

    def didDeviceCommPropertyChange(self, origDev, newDev):
        try:
            if origDev.deviceTypeId == newDev.deviceTypeId == "rfid":
                reader = registry_for(self).get(newDev.id)
                if reader is not None:
                    reader.rfidPolicyProps = dict(newDev.pluginProps)
                keys = ("rfidSimulation", "antennaEnabled", "serialNumber", "channel",
                        "hubPort", "isVintHub", "isVintDevice", "serverName")
                return any(origDev.pluginProps.get(key) != newDev.pluginProps.get(key) for key in keys)
            return super(RFIDManagementMixin, self).didDeviceCommPropertyChange(origDev, newDev)
        except Exception as error:
            self.logger.error("Unable to apply device configuration for %s: %s",
                              getattr(newDev, "id", "unknown"), str(error).replace("\n", " "))
            return True
