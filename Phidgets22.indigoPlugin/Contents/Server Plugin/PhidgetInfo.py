# -*- coding: utf-8 -*-

"""Build Indigo enum menus from the installed Phidget22 SDK."""

from Phidget22.FilterType import FilterType
from Phidget22.InputMode import InputMode
from Phidget22.PowerSupply import PowerSupply
from Phidget22.ThermocoupleType import ThermocoupleType
from Phidget22.VoltageRatioSensorType import VoltageRatioSensorType
from Phidget22.VoltageSensorType import VoltageSensorType

from phidget_enum_labels import LABEL_OVERRIDES


ENUM_TYPES = {
    "VoltageSensorType": VoltageSensorType,
    "VoltageRatioSensorType": VoltageRatioSensorType,
    "ThermocoupleType": ThermocoupleType,
    "FilterType": FilterType,
    "InputMode": InputMode,
    "PowerSupply": PowerSupply,
}
ENUM_PREFIXES = (
    "SENSOR_TYPE_", "THERMOCOUPLE_TYPE_", "FILTER_TYPE_",
    "INPUT_MODE_", "POWER_SUPPLY_",
)


def _fallbackLabel(enum_name):
    label = str(enum_name)
    for prefix in ENUM_PREFIXES:
        if label.startswith(prefix):
            label = label[len(prefix):]
            break
    words = []
    for word in label.split("_"):
        words.append(word if (any(character.isdigit() for character in word) or
                              len(word) <= 3) else word.title())
    return " ".join(words)


class PhidgetInfo(object):
    def getPhidgetTypeMenu(self, classes):
        menu = []
        for class_name in classes:
            enum_type = ENUM_TYPES.get(class_name)
            if enum_type is None:
                continue
            overrides = LABEL_OVERRIDES.get(class_name, {})
            seen_values = set()
            for enum_name, member in enum_type.__members__.items():
                value = int(member.value)
                if value in seen_values:
                    continue
                seen_values.add(value)
                menu.append((value, overrides.get(
                    enum_name, _fallbackLabel(enum_name))))
        return sorted(menu, key=lambda item: (
            item[1][0].isdigit(), item[1]))
