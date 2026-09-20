"""Exercise entry-point import failures without an installed SDK or Indigo."""
import builtins
import pathlib
import runpy
import types
import sys
import unittest
from unittest import mock

SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))
import python_environment

ENTRY = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin" / "plugin.py"


class StartupDependencyTests(unittest.TestCase):
    def run_with_missing_module(self, missing):
        real_import = builtins.__import__

        def import_module(name, *args, **kwargs):
            if name.startswith("Phidget22."):
                raise ModuleNotFoundError("No module named " + missing, name=missing)
            return real_import(name, *args, **kwargs)

        log = mock.Mock()
        indigo = types.SimpleNamespace(server=types.SimpleNamespace(log=log))
        with mock.patch.dict("sys.modules", {"indigo": indigo}), \
                mock.patch("builtins.__import__", side_effect=import_module):
            with self.assertRaises(ImportError) as caught:
                runpy.run_path(str(ENTRY))
        return caught.exception, log

    def test_missing_sdk_gives_install_command_and_stops_initialization(self):
        error, log = self.run_with_missing_module("Phidget22")
        message = str(error)
        self.assertIn("Mac running Indigo Server", message)
        version = "%s.%s" % sys.version_info[:2]
        self.assertIn('"/Library/Frameworks/Python.framework/Versions/{0}/bin/python{0}" -m pip install --upgrade phidget22'.format(version), message)
        self.assertIn("Then reload Phidgets 22", message)
        log.assert_called_once_with(message, isError=True)
        self.assertTrue(error.__suppress_context__)

    def test_other_missing_modules_are_not_misdiagnosed(self):
        error, log = self.run_with_missing_module("another_dependency")
        self.assertIsInstance(error, ModuleNotFoundError)
        self.assertEqual(error.name, "another_dependency")
        log.assert_not_called()

    def test_advice_targets_each_host_runtime(self):
        for version in [(3, 10), (3, 13)]:
            with self.subTest(version=version), mock.patch.object(python_environment.sys, "version_info", version), mock.patch.object(python_environment.os, "access", return_value=True):
                advice = python_environment.phidget_install_advice()
                self.assertIn("Versions/%s.%s/bin/python%s.%s" % (version + version), advice)
                self.assertIn("-m pip install --upgrade phidget22", advice)

    def test_missing_interpreter_does_not_offer_broken_command(self):
        with mock.patch.object(python_environment.os, "access", return_value=False):
            advice = python_environment.phidget_install_advice()
        self.assertIn("Verify or repair", advice)
        self.assertNotIn("-m pip", advice)
