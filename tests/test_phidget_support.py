import pathlib
import sys
import unittest


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))


class PhidgetSupportTests(unittest.TestCase):
    def test_plugin_does_not_vendor_phidget22(self):
        self.assertFalse((SERVER_PLUGIN / "Phidget22").exists())

    def test_indigo_python_package_is_version_1_26(self):
        import Phidget22
        from Phidget22.Phidget import Phidget
        self.assertNotIn(str(SERVER_PLUGIN), str(Phidget22.__file__))
        self.assertIn("Version 1.26", Phidget.getLibraryVersion())


if __name__ == "__main__":
    unittest.main()
