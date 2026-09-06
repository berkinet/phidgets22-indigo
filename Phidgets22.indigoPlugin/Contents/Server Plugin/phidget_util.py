#
# Random utility functions relating to the Indigo phidget plugin.
#

from Phidget22.DeviceClass import DeviceClass


def _read(phidget, method_name, default=None):
    method = getattr(phidget, method_name, None)
    if method is None:
        return default
    try:
        return method()
    except Exception:
        return default


def logPhidgetEvent(ph, logger, eventType="UNKNOWN"):
    parent = getattr(ph, "parent", None)
    channel_info = getattr(parent, "channelInfo", None)
    channelClassName = _read(ph, "getChannelClassName", ph.__class__.__name__)
    serialNumber = _read(
        ph, "getDeviceSerialNumber",
        getattr(channel_info, "serialNumber", "unknown"))
    channel = _read(
        ph, "getChannel", getattr(channel_info, "channel", "unknown"))
    deviceClass = _read(ph, "getDeviceClass", DeviceClass.PHIDCLASS_NOTHING)

    if(deviceClass == DeviceClass.PHIDCLASS_VINT):
        hubPort = _read(
            ph, "getHubPort", getattr(channel_info, "hubPort", "unknown"))
        logger(eventType + " event: -> Channel Class: " + channelClassName + " -> Serial Number: " +
            str(serialNumber) + " -> Hub Port: " + str(hubPort) + " -> Channel:  " + str(channel))
    else:
        logger(eventType + " event: -> Channel Class: " + channelClassName + " -> Serial Number: " +
            str(serialNumber) + " -> Channel:  " + str(channel))

    return
