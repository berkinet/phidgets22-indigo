# -*- coding: utf-8 -*-
"""RFID list policy, bounded history, and staged variable edits."""
import json
import threading

import indigo
from config_util import saved_bool
from rfid_presence import clear_delay_seconds

LOCK = threading.RLock()
PROTOCOLS = {1: "EM4100", 2: "ISO11785 FDX-B", 3: "PhidgetTAG",
             4: "HID Generic", 5: "HID H10301"}
HISTORY_KEY = "rfidRecentTags"
SIDES = ("Allowed", "Denied")


def tag_id(value):
    value = str(value).strip()
    if not value or "\n" in value or "\r" in value:
        raise ValueError("Enter one non-empty tag ID, without line breaks.")
    return value


def variable(variable_id):
    try:
        result = indigo.variables[int(variable_id)]
    except (ValueError, TypeError, KeyError, IndexError):
        raise ValueError("Indigo variable %s is missing; select an existing variable." %
                         (variable_id or "(none)")) from None
    if getattr(result, "readOnly", False):
        raise ValueError("Variable '%s' is read-only." % result.name)
    return result


def entries(value):
    return list(dict.fromkeys(line.strip() for line in str(value).splitlines() if line.strip()))


def selected_variable(values, side):
    """Translate the Indigo menu placeholder without treating it as a variable."""
    value = str(values.get("rfid" + side + "Variable", "") or "")
    return "" if value == "none" else value


def history_token(tag, protocol):
    # Indigo menu IDs cannot contain JSON punctuation, spaces, or be empty.
    return "tag_" + json.dumps([tag, protocol], ensure_ascii=False).encode("utf-8").hex()


def history_selection(token):
    if not token.startswith("tag_"):
        raise ValueError("Select a recent tag again.")
    tag, protocol = json.loads(bytes.fromhex(token[4:]).decode("utf-8"))
    return tag_id(tag), int(protocol)


def evaluate(props, tag):
    """Return the policy decision; variable lookup failures propagate."""
    return evaluate_with_reason(props, tag)[0]


def evaluate_with_reason(props, tag):
    """Return the decision and denial reason from one snapshot of live lists."""
    lists, names = {}, {}
    with LOCK:
        for side in SIDES:
            if saved_bool(props.get("rfidCheck" + side, False)):
                source = variable(selected_variable(props, side))
                lists[side], names[side] = entries(source.value), source.name
    if "Denied" in lists and tag in lists["Denied"]:
        return False, "listed in denied variable %r" % names["Denied"]
    if "Allowed" in lists and tag not in lists["Allowed"]:
        return False, "not listed in allowed variable %r" % names["Allowed"]
    return True, ""


def recent(plugin, device_id):
    with LOCK:
        history = json.loads(plugin.pluginPrefs.get(HISTORY_KEY, "{}"))
        return list(history.get(str(device_id), []))


def remember(plugin, device_id, tag, protocol, timestamp):
    with LOCK:
        history = json.loads(plugin.pluginPrefs.get(HISTORY_KEY, "{}"))
        rows = history.get(str(device_id), [])
        rows = [row for row in rows if (row["tag"], row["protocol"]) != (tag, protocol)]
        history[str(device_id)] = ([{"tag": tag, "protocol": protocol, "seen": timestamp}] + rows)[:50]
        plugin.pluginPrefs[HISTORY_KEY] = json.dumps(history)


def pending(values):
    result = json.loads(values.get("rfidPendingEdits", "[]") or "[]")
    if not isinstance(result, list):
        raise ValueError("Invalid pending edits; reopen the device configuration.")
    return result


def build_edits(values):
    """Merge edits onto live variables without mutating any external state."""
    variables, contents = {}, {}
    changed = set()
    def get_contents(var_id):
        var_id = str(var_id)
        if var_id not in contents:
            variables[var_id] = variable(var_id)
            contents[var_id] = entries(variables[var_id].value)
        return contents[var_id]
    for operation in pending(values):
        side, kind, tag = operation["side"], operation["kind"], tag_id(operation["tag"])
        if side not in SIDES or kind not in ("add", "remove", "move"):
            raise ValueError("Invalid pending edit; clear pending edits and try again.")
        var_id = selected_variable(values, side)
        opposite = "Denied" if side == "Allowed" else "Allowed"
        other_id = selected_variable(values, opposite)
        if var_id != operation["variable"] or other_id != operation["opposite"]:
            raise ValueError("List selections changed. Clear pending edits before selecting different variables.")
        target = get_contents(var_id)
        if var_id == other_id:
            raise ValueError("Allowed and denied lists must use different variables.")
        if kind == "remove":
            if tag in target:
                target.remove(tag)
                changed.add(var_id)
        else:
            if other_id:
                other = get_contents(other_id)
                if tag in other and kind == "add":
                    raise ValueError("Tag is in the %s list. Choose Move to %s list instead." %
                                     (opposite.lower(), side.lower()))
                if kind == "move" and tag in other:
                    other.remove(tag)
                    changed.add(other_id)
            if tag not in target:
                target.append(tag)
                changed.add(var_id)
    return [(variables[key], "\n".join(value)) for key, value in contents.items() if key in changed]


def validate(values):
    errors = indigo.Dict()
    try:
        clear_delay_seconds(values)
    except (TypeError, ValueError, OverflowError):
        errors["rfidPresenceClearMinutes"] = "Enter a delay from 0 through 1440 minutes. Decimals are allowed."
    for side in SIDES:
        key = "rfid" + side + "Variable"
        if saved_bool(values.get("rfidCheck" + side, False)) or selected_variable(values, side):
            try:
                variable(selected_variable(values, side))
            except Exception as error:
                errors[key] = str(error)
    if (selected_variable(values, "Allowed") and
            selected_variable(values, "Allowed") == selected_variable(values, "Denied")):
        errors["rfidDeniedVariable"] = "Select a different variable for each list."
    try:
        with LOCK:
            build_edits(values)
    except Exception as error:
        errors["rfidEditStatus"] = str(error)
        errors["showAlertText"] = str(error)
    return errors


def apply_edits(values):
    with LOCK:
        # Preflight every operation before the first write. Indigo provides no
        # atomic multi-variable transaction; report the exact failed destination.
        changes = build_edits(values)
        for destination, value in changes:
            if str(destination.value) == value:
                continue
            try:
                indigo.variable.updateValue(destination.id, value=value)
            except Exception as error:
                raise ValueError("Could not update '%s': %s. Earlier list edits may have saved; review both variables." %
                                 (destination.name, str(error).replace("\n", " "))) from None
