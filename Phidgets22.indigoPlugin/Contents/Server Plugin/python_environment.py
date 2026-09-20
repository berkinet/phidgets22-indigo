"""Dependency advice for the Python runtime actually hosting this plugin."""
import os
import sys


def phidget_install_advice():
    version = "%s.%s" % sys.version_info[:2]
    executable = "/Library/Frameworks/Python.framework/Versions/{0}/bin/python{0}".format(version)
    if not os.access(executable, os.X_OK):
        return (
            "Indigo is running Python {0}, but its expected interpreter was not "
            "found at {1}. Verify or repair the Python installation supplied with "
            "your Indigo version before installing Phidget22."
        ).format(version, executable)
    return (
        'On the Mac running Indigo Server, open Terminal and run:\n'
        '"{0}" -m pip install --upgrade phidget22\n'
        'Then reload Phidgets 22 in Indigo. This command targets Indigo Python {1}.'
    ).format(executable, version)
