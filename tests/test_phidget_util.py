import pathlib
import sys
import types
import unittest
from unittest import mock


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))

import phidget_util


class LogicalLCDChannel(object):
    pass


class PhidgetUtilTests(unittest.TestCase):
    def test_log_event_supports_logical_channel_without_sdk_diagnostics(self):
        channel = LogicalLCDChannel()
        channel.parent = types.SimpleNamespace(channelInfo=types.SimpleNamespace(
            serialNumber=729035, channel=0, hubPort=-1))
        logger = mock.Mock()

        phidget_util.logPhidgetEvent(channel, logger, "Attached 'I2C LCD'")

        logger.assert_called_once_with(
            "Attached 'I2C LCD' event: -> Channel Class: LogicalLCDChannel "
            "-> Serial Number: 729035 -> Channel:  0")


if __name__ == "__main__":
    unittest.main()
