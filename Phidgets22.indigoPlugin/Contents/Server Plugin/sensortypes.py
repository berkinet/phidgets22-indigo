# -*- coding: utf-8 -*-

# Helper functions to figure out what type of data will be returned from various sensor types.
# This data comes from libphidget22 in `src/analogsensor.c`.
#
# Unfortunately, `PhidgetAnalogSensor_getVoltageSensorUnit` and `PhidgetAnalogSensor_getVoltageRatioSensorUnit` are NOT accessible from python.

from Phidget22.Unit import Unit
from Phidget22.VoltageRatioSensorType import VoltageRatioSensorType
from Phidget22.VoltageSensorType import VoltageSensorType


sensorUnits = {
    Unit.PHIDUNIT_NONE: ("value", ""), # Modifed from None
    Unit.PHIDUNIT_BOOLEAN: ("boolean", ""),
    Unit.PHIDUNIT_PERCENT: ("percent", "%"),
    Unit.PHIDUNIT_DECIBEL: ("decibel", "dB"),
    Unit.PHIDUNIT_MILLIMETER: ("millimeter", "mm"),
    Unit.PHIDUNIT_CENTIMETER: ("centimeter", "cm"),
    Unit.PHIDUNIT_METER: ("meter", "m"),
    Unit.PHIDUNIT_GRAM: ("gram", "g"),
    Unit.PHIDUNIT_KILOGRAM: ("kilogram", "kg"),
    Unit.PHIDUNIT_MILLIAMPERE: ("milliampere", "mA"),
    Unit.PHIDUNIT_AMPERE: ("ampere", "A"),
    Unit.PHIDUNIT_KILOPASCAL: ("kilopascal", "kPa"),
    Unit.PHIDUNIT_VOLT: ("volt", "V"),
    Unit.PHIDUNIT_DEGREE_CELCIUS: ("tempC", "°C"), # Modified from "degrees Celsius"
    Unit.PHIDUNIT_LUX: ("lux", "lx"),
    Unit.PHIDUNIT_GAUSS: ("gauss", "G"),
    Unit.PHIDUNIT_PH: ("pH", ""),
    Unit.PHIDUNIT_WATT: ("watt", "W"),
}

def getNameAndSymbol(unitType):
    if unitType in sensorUnits:
        return sensorUnits[unitType]
    else:
        return (None, None)

ratioSensorUnitTypes = {
    Unit.PHIDUNIT_MILLIMETER : [VoltageRatioSensorType.SENSOR_TYPE_1146],
    Unit.PHIDUNIT_CENTIMETER : [VoltageRatioSensorType.SENSOR_TYPE_1101_SHARP_2D120X, VoltageRatioSensorType.SENSOR_TYPE_1101_SHARP_2Y0A21,
                                VoltageRatioSensorType.SENSOR_TYPE_1101_SHARP_2Y0A02, VoltageRatioSensorType.SENSOR_TYPE_1128,
                                VoltageRatioSensorType.SENSOR_TYPE_3520, VoltageRatioSensorType.SENSOR_TYPE_3521, VoltageRatioSensorType.SENSOR_TYPE_3522],
    Unit.PHIDUNIT_BOOLEAN : [VoltageRatioSensorType.SENSOR_TYPE_1102, VoltageRatioSensorType.SENSOR_TYPE_1103,
                             VoltageRatioSensorType.SENSOR_TYPE_1110, VoltageRatioSensorType.SENSOR_TYPE_1129],
    Unit.PHIDUNIT_PERCENT : [VoltageRatioSensorType.SENSOR_TYPE_1107, VoltageRatioSensorType.SENSOR_TYPE_1125_HUMIDITY, VoltageRatioSensorType.SENSOR_TYPE_3130],
    Unit.PHIDUNIT_GAUSS : [VoltageRatioSensorType.SENSOR_TYPE_1108],
    Unit.PHIDUNIT_KILOPASCAL : [VoltageRatioSensorType.SENSOR_TYPE_1115, VoltageRatioSensorType.SENSOR_TYPE_1126, VoltageRatioSensorType.SENSOR_TYPE_1136,
                                VoltageRatioSensorType.SENSOR_TYPE_1137, VoltageRatioSensorType.SENSOR_TYPE_1138, VoltageRatioSensorType.SENSOR_TYPE_1139,
                                VoltageRatioSensorType.SENSOR_TYPE_1140, VoltageRatioSensorType.SENSOR_TYPE_1141],
    Unit.PHIDUNIT_AMPERE : [VoltageRatioSensorType.SENSOR_TYPE_1118_AC, VoltageRatioSensorType.SENSOR_TYPE_1119_AC, VoltageRatioSensorType.SENSOR_TYPE_1122_AC,
                            VoltageRatioSensorType.SENSOR_TYPE_1118_DC, VoltageRatioSensorType.SENSOR_TYPE_1119_DC, VoltageRatioSensorType.SENSOR_TYPE_1122_DC],
    Unit.PHIDUNIT_DEGREE_CELCIUS : [VoltageRatioSensorType.SENSOR_TYPE_1124, VoltageRatioSensorType.SENSOR_TYPE_1125_TEMPERATURE],
    Unit.PHIDUNIT_GRAM : [VoltageRatioSensorType.SENSOR_TYPE_1131],
    Unit.PHIDUNIT_KILOGRAM : [VoltageRatioSensorType.SENSOR_TYPE_3120, VoltageRatioSensorType.SENSOR_TYPE_3121,
                              VoltageRatioSensorType.SENSOR_TYPE_3122, VoltageRatioSensorType.SENSOR_TYPE_3123],
    Unit.PHIDUNIT_NONE : [VoltageRatioSensorType.SENSOR_TYPE_VOLTAGERATIO, VoltageRatioSensorType.SENSOR_TYPE_1104, VoltageRatioSensorType.SENSOR_TYPE_1111,
                          VoltageRatioSensorType.SENSOR_TYPE_1113, VoltageRatioSensorType.SENSOR_TYPE_1105, VoltageRatioSensorType.SENSOR_TYPE_1106,
                          VoltageRatioSensorType.SENSOR_TYPE_1109, VoltageRatioSensorType.SENSOR_TYPE_1112, VoltageRatioSensorType.SENSOR_TYPE_1116,
                          VoltageRatioSensorType.SENSOR_TYPE_1120, VoltageRatioSensorType.SENSOR_TYPE_1121, VoltageRatioSensorType.SENSOR_TYPE_1134],
}

sensorUnitTypes = {
    Unit.PHIDUNIT_PH : [VoltageSensorType.SENSOR_TYPE_1130_PH],
    Unit.PHIDUNIT_DEGREE_CELCIUS : [VoltageSensorType.SENSOR_TYPE_1114],
    Unit.PHIDUNIT_LUX : [VoltageSensorType.SENSOR_TYPE_1127, VoltageSensorType.SENSOR_TYPE_1142, VoltageSensorType.SENSOR_TYPE_1143],
    Unit.PHIDUNIT_MILLIAMPERE : [VoltageSensorType.SENSOR_TYPE_1132, VoltageSensorType.SENSOR_TYPE_3511, VoltageSensorType.SENSOR_TYPE_3512, VoltageSensorType.SENSOR_TYPE_3513],
    Unit.PHIDUNIT_DECIBEL : [VoltageSensorType.SENSOR_TYPE_1133],
    Unit.PHIDUNIT_AMPERE : [VoltageSensorType.SENSOR_TYPE_3500, VoltageSensorType.SENSOR_TYPE_3501, VoltageSensorType.SENSOR_TYPE_3502,
                            VoltageSensorType.SENSOR_TYPE_3503, VoltageSensorType.SENSOR_TYPE_3584, VoltageSensorType.SENSOR_TYPE_3585,
                            VoltageSensorType.SENSOR_TYPE_3586, VoltageSensorType.SENSOR_TYPE_3587, VoltageSensorType.SENSOR_TYPE_3588,
                            VoltageSensorType.SENSOR_TYPE_3589, VoltageSensorType.SENSOR_TYPE_VCP4114],
    Unit.PHIDUNIT_WATT : [VoltageSensorType.SENSOR_TYPE_3514, VoltageSensorType.SENSOR_TYPE_3515, VoltageSensorType.SENSOR_TYPE_3516,
                          VoltageSensorType.SENSOR_TYPE_3517, VoltageSensorType.SENSOR_TYPE_3518, VoltageSensorType.SENSOR_TYPE_3519],
    Unit.PHIDUNIT_NONE : [VoltageSensorType.SENSOR_TYPE_MOT2002_LOW, VoltageSensorType.SENSOR_TYPE_MOT2002_MED, VoltageSensorType.SENSOR_TYPE_MOT2002_HIGH],
    Unit.PHIDUNIT_VOLT : [VoltageSensorType.SENSOR_TYPE_1117, VoltageSensorType.SENSOR_TYPE_1123, VoltageSensorType.SENSOR_TYPE_1130_ORP,
                          VoltageSensorType.SENSOR_TYPE_1135, VoltageSensorType.SENSOR_TYPE_3507, VoltageSensorType.SENSOR_TYPE_3508,
                          VoltageSensorType.SENSOR_TYPE_3509, VoltageSensorType.SENSOR_TYPE_3510, VoltageSensorType.SENSOR_TYPE_VOLTAGE],
}

def getVoltageSensorUnit(sensorType):
    for key, value in sensorUnitTypes.items():
        if sensorType in value:
            return key
    return Unit.PHIDUNIT_VOLT


def getVoltageRatioSensorUnit(sensorType):
    for key, value in ratioSensorUnitTypes.items():
        if sensorType in value:
            return key
    return Unit.PHIDUNIT_NONE
