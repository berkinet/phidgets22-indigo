# -*- coding: utf-8 -*-

"""Asynchronous, read-only access to the bundled Phidget22 Admin Tool."""

import pathlib
import subprocess
import threading


class AdminToolRunner(object):
    def __init__(self, logger, run_command=subprocess.run,
                 thread_factory=threading.Thread):
        self.logger = logger
        self._run_command = run_command
        self._thread_factory = thread_factory
        self._lock = threading.RLock()
        self._running = False
        self.executable = (pathlib.Path(__file__).resolve().parent.parent /
                           "Resources" / "phidget22admin" /
                           "phidget22admin")

    def list_devices(self):
        with self._lock:
            if self._running:
                self.logger.warning(
                    "A Phidget22 Admin Tool device listing is already running")
                return False
            self._running = True
        thread = self._thread_factory(target=self._list_devices_worker)
        thread.daemon = True
        thread.start()
        return True

    def _list_devices_worker(self):
        try:
            if not self.executable.is_file():
                raise RuntimeError(
                    "Bundled phidget22admin executable was not found")
            result = self._run_command(
                [str(self.executable), "-d"],
                cwd=str(self.executable.parent),
                capture_output=True,
                text=True,
                timeout=30,
                check=False)
            output = (result.stdout or "").rstrip()
            error_output = (result.stderr or "").rstrip()
            if result.returncode != 0:
                details = error_output or output or "No diagnostic output"
                self.logger.error(
                    "Phidget22 Admin Tool device listing failed (exit %d):\n%s",
                    result.returncode, details)
                return
            if error_output:
                output = "%s\n%s" % (output, error_output) if output else error_output
            self.logger.info(
                "Visible Phidgets reported by phidget22admin -d:\n%s",
                output or "(no visible Phidgets)")
        except subprocess.TimeoutExpired:
            self.logger.error(
                "Phidget22 Admin Tool device listing timed out after 30 seconds")
        except Exception as error:
            self.logger.error(
                "Unable to list visible Phidgets with phidget22admin -d: %s",
                error)
        finally:
            with self._lock:
                self._running = False
