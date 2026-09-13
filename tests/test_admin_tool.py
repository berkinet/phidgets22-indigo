# -*- coding: utf-8 -*-

import pathlib
import subprocess
import sys
import unittest
from unittest import mock


SERVER_PLUGIN = (pathlib.Path(__file__).parents[1] /
                 "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin")
sys.path.insert(0, str(SERVER_PLUGIN))

from admin_tool import AdminToolRunner


class ImmediateThread(object):
    def __init__(self, target):
        self.target = target
        self.daemon = False

    def start(self):
        self.target()


class AdminToolRunnerTests(unittest.TestCase):
    def test_device_listing_runs_dash_d_and_logs_complete_output(self):
        logger = mock.Mock()
        command = mock.Mock(return_value=subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="Device 123\n  Digital Input 0\n", stderr=""))
        runner = AdminToolRunner(
            logger, run_command=command, thread_factory=ImmediateThread)

        self.assertTrue(runner.list_devices())

        arguments, options = command.call_args
        self.assertEqual(arguments[0], [str(runner.executable), "-d"])
        self.assertEqual(options["cwd"], str(runner.executable.parent))
        self.assertEqual(options["timeout"], 30)
        logger.info.assert_called_once_with(
            "Visible Phidgets reported by phidget22admin -d:\n%s",
            "Device 123\n  Digital Input 0")
        self.assertFalse(runner._running)

    def test_overlapping_listing_is_rejected(self):
        logger = mock.Mock()
        runner = AdminToolRunner(logger)
        runner._running = True

        self.assertFalse(runner.list_devices())

        logger.warning.assert_called_once()

    def test_nonzero_exit_is_logged_as_error(self):
        logger = mock.Mock()
        command = mock.Mock(return_value=subprocess.CompletedProcess(
            args=[], returncode=2, stdout="", stderr="cannot connect\n"))
        runner = AdminToolRunner(
            logger, run_command=command, thread_factory=ImmediateThread)

        runner.list_devices()

        logger.error.assert_called_once_with(
            "Phidget22 Admin Tool device listing failed (exit %d):\n%s",
            2, "cannot connect")


if __name__ == "__main__":
    unittest.main()
