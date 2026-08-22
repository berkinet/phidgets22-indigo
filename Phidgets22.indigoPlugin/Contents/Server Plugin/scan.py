#! /usr/env/python

#
# Utility to scan for available phidgets
#

import time

import argparse

from Phidget22.Devices.Manager import Manager
from Phidget22.Net import Net, PhidgetServerType
from Phidget22.ChannelClass import ChannelClass
from Phidget22.ChannelSubclass import ChannelSubclass
from Phidget22.DeviceClass import DeviceClass
from Phidget22.DeviceID import DeviceID
from Phidget22.Phidget import Phidget

# setup argparse
parser = argparse.ArgumentParser(description='Scan netwiork for Phidget devices',
    formatter_class=argparse.RawTextHelpFormatter)
group = parser.add_mutually_exclusive_group()
group.add_argument('-d', type=int, default=None,
    help="Phidget device class", metavar=('<device class>'))
group.add_argument('-s', type=int, default=None,
    help="Phidget serial number", metavar=('<serial number>'))
group.add_argument('-c', type=str, default=None,
    help="Phidget Channel class", metavar=('<channel class>'))

# save the args received by argparse into variables
args = parser.parse_args()
scanDevice = args.d
scanSerial = args.s
scanChannel = args.c

class PhidgetDevice():
    def __init__(self, channel):
        # device
        self.serialNumber = channel.getDeviceSerialNumber()
        self.deviceClass = channel.getDeviceClass()
        self.deviceName = channel.getDeviceName()
        self.deviceId = channel.getDeviceID()
        self.deviceLabel = channel.getDeviceLabel()
        self.deviceSku = channel.getDeviceSKU()
        # channel
        self.sku = channel.getDeviceSKU()
        self.channel = channel.getChannel()
        self.channelClass = channel.getChannelClass()
        self.channelSubClass = channel.getChannelSubclass()
        self.channelName = channel.getChannelName()
        self.deviceParent = channel.getParent()
        if channel.getDeviceClass() == DeviceClass.PHIDCLASS_INTERFACEKIT:
            self.devicePort = channel.getChannel()
        else:
            self.devicePort = channel.getHubPort()
        if channel.getIsRemote():
            self.serverPeerName = channel.getServerPeerName()
            self.serverHostname = channel.getServerHostname()
            self.serverName = channel.getServerName()
            self.serverIpAddr = channel.getServerPeerName()
            self.serverUniqueName = channel.getServerUniqueName()
        else:
            self.serverPeerName = "Local"
            self.serverHostname = "Local"
            self.serverName = "Local"
            self.serverIpAddr = "Local"
            self.serverUniqueName = "Local"

        try:
            if self.deviceClass in [DeviceClass.PHIDCLASS_VINT, DeviceClass.PHIDCLASS_HUB]:  # 8, 21
                self.channelCount = "Hub Port Count: %s" % channel.getHubPortCount()
            else:
                self.channelCount = channel.getDeviceChannelCount(ChannelClass.PHIDCHCLASS_NOTHING)
                self.channelCountDO = channel.getDeviceChannelCount(ChannelClass.PHIDCHCLASS_DIGITALOUTPUT)
                self.channelCountDI = channel.getDeviceChannelCount(ChannelClass.PHIDCHCLASS_DIGITALINPUT)
                self.channelCountVI = channel.getDeviceChannelCount(ChannelClass.PHIDCHCLASS_VOLTAGEINPUT)
                self.channelCountVR = channel.getDeviceChannelCount(ChannelClass.PHIDCHCLASS_VOLTAGERATIOINPUT)
        except Exception as e:
                print('Error reading hub/channel count for serial number: %s. e = %s' % (channel.serialNumber, e))

        # hub
        self.hubPort = channel.getHubPort()

    def __str__(self):
        return '<device ' + ' '.join(['%s=%s' % (x, getattr(self, x)) for x in vars(self)]) + '>'


class PhidgetFinder():
    def __init__(self, use_network=True):
        if use_network:
            Net.enableServerDiscovery(PhidgetServerType.PHIDGETSERVER_DEVICEREMOTE)
        self.manager = Manager()
        self.devices = set()

    def open(self):
        self.manager.open()
        self.manager.setOnAttachHandler(self.AttachHandler)
        self.manager.setOnDetachHandler(self.DetachHandler)

    def AttachHandler(self, manager, channel):
        newPh = PhidgetDevice(channel)
        self.devices.add(newPh)

    def DetachHandler(self, manager, channel):
        detachedDevice = channel
        serialNumber = detachedDevice.getDeviceSerialNumber()
        deviceName = detachedDevice.getDeviceName()
        print("Goodbye Device " + str(deviceName) + ", Serial Number: " + str(serialNumber))

    def getSerialNumbers(self, channelClass=None):
        numbers = set()
        for device in self.devices:
            if channelClass and device.channelClass != channelClass:
                continue

            numbers.add(device.serialNumber)
        return numbers

    def close(self):
        self.manager.close()

    def __del__(self):
        self.close()


def main(scanSerial, scanDevice, scanChannel):
    # Example on how to use this class
    finder = PhidgetFinder()
    finder.open()

    toSleep = 3
    print("Phidget Simple Playground (plug and unplug devices)")
    libraryVersion = Phidget.getLibraryVersion()
    print("Library Version: " + str(libraryVersion))
    print("Waiting for " + str(toSleep) + " seconds")

    time.sleep(toSleep)

    if scanSerial:
        searchField = 'serialNumber'
        matchString = [scanSerial]
    elif scanDevice:
        searchField = 'deviceClass'
        matchString = [scanDevice]
    elif scanChannel:
        searchField = 'channelClass'
        if scanChannel == 'o':
            # everything except  PHIDCHCLASS_[DIGITALINPUT | DIGITALOUTPUT | HUB | VOLTAGEINPUT | VOLTAGERATIOINPUT | DICTIONARY]
            matchString = [
                ChannelClass.PHIDCHCLASS_NOTHING,
                ChannelClass.PHIDCHCLASS_ACCELEROMETER,
                ChannelClass.PHIDCHCLASS_CURRENTINPUT,
                ChannelClass.PHIDCHCLASS_DATAADAPTER,
                ChannelClass.PHIDCHCLASS_DCMOTOR,
                ChannelClass.PHIDCHCLASS_DISTANCESENSOR,
                ChannelClass.PHIDCHCLASS_ENCODER,
                ChannelClass.PHIDCHCLASS_FREQUENCYCOUNTER,
                ChannelClass.PHIDCHCLASS_GPS,
                ChannelClass.PHIDCHCLASS_LCD,
                ChannelClass.PHIDCHCLASS_GYROSCOPE,
                ChannelClass.PHIDCHCLASS_CAPACITIVETOUCH,
                ChannelClass.PHIDCHCLASS_HUMIDITYSENSOR,
                ChannelClass.PHIDCHCLASS_IR,
                ChannelClass.PHIDCHCLASS_LIGHTSENSOR,
                ChannelClass.PHIDCHCLASS_MAGNETOMETER,
                ChannelClass.PHIDCHCLASS_MESHDONGLE,
                ChannelClass.PHIDCHCLASS_PHSENSOR,
                ChannelClass.PHIDCHCLASS_POWERGUARD,
                ChannelClass.PHIDCHCLASS_PRESSURESENSOR,
                ChannelClass.PHIDCHCLASS_RCSERVO,
                ChannelClass.PHIDCHCLASS_RESISTANCEINPUT,
                ChannelClass.PHIDCHCLASS_RFID,
                ChannelClass.PHIDCHCLASS_SOUNDSENSOR,
                ChannelClass.PHIDCHCLASS_SPATIAL,
                ChannelClass.PHIDCHCLASS_STEPPER,
                ChannelClass.PHIDCHCLASS_TEMPERATURESENSOR,
                ChannelClass.PHIDCHCLASS_VOLTAGEOUTPUT,
                ChannelClass.PHIDCHCLASS_FIRMWAREUPGRADE,
                ChannelClass.PHIDCHCLASS_GENERIC,
                ChannelClass.PHIDCHCLASS_MOTORPOSITIONCONTROLLER,
                ChannelClass.PHIDCHCLASS_BLDCMOTOR,
                ChannelClass.PHIDCHCLASS_CURRENTOUTPUT
            ]  # [0, 1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 37, 20, 21, 22, 23, 24, 25, 26, 27, 28, 30, 32, 33, 34, 35, 38]
        else:
            matchString = [int(scanChannel)]
    else:
        matchString = None

    for device in sorted(finder.devices):
        if not matchString or getattr(device, searchField) in matchString:
            print('\nNew Device: ' + device.deviceName + ' - ' + device.serverName)
            for var in sorted(vars(device)):
                value = getattr(device, var)
                # Check if we have an enumeration for this var...
                if var == "channelClass":
                    print('    %s = %s (%s)' % (var, value, ChannelClass.getName(value)))
                elif var == "channelSubClass":
                    print('    %s = %s (%s)' % (var, value, ChannelSubclass.getName(value)))
                elif var == "deviceId":
                    print('    %s = %s (%s)' % (var, value, DeviceID.getName(value)))
                elif var == "deviceClass":
                    print('    %s = %s (%s)' % (var, value, DeviceClass.getName(value)))
                # ... now print everything else
                else:
                    print('    %s = %s' % (var, value))

    finder.close()


if __name__ == "__main__":
    main(scanSerial, scanDevice, scanChannel)
