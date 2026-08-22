import importlib.util
import logging
import pathlib
import unittest


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
SPEC = importlib.util.spec_from_file_location("version_check", SERVER_PLUGIN / "version_check.py")
version_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(version_check)


class FakeResponse(object):
    def __init__(self, text):
        self.text = text
        self.closed = False

    def read(self):
        return self.text.encode("utf-8")

    def close(self):
        self.closed = True


class VersionCheckTests(unittest.TestCase):
    def test_installed_version_includes_build_date(self):
        actual = version_check.parse_installed_version(
            "Phidget22 - Version 1.23 - Built Oct  6 2025 09:06:56")
        self.assertEqual(actual, "1.23.20251006")

    def test_latest_package_version_comes_from_pypi_json(self):
        payload = '{"info": {"version": "1.25.20260408"}}'
        self.assertEqual(version_check.parse_latest_package_version(payload),
                         "1.25.20260408")

    def test_fetch_uses_timeout_and_closes_response(self):
        calls = []
        response = FakeResponse('{"info": {"version": "1.25.20260408"}}')

        def opener(request, timeout):
            calls.append((request.full_url, timeout))
            return response

        actual = version_check.fetch_latest_package_version(timeout=3, opener=opener)
        self.assertEqual(actual, "1.25.20260408")
        self.assertEqual(calls[0][1], 3)
        self.assertTrue(response.closed)

    def test_current_version_logs_info(self):
        logger = logging.getLogger("test.version.current")
        opener = lambda request, timeout: FakeResponse(
            '{"info": {"version": "1.25.20260408"}}')
        with self.assertLogs(logger, level="INFO") as captured:
            version_check.check_and_log(
                "Phidget22 - Version 1.25 - Built Apr  8 2026 09:00:00",
                logger, opener=opener)
        self.assertIn("up to date", captured.output[0])

    def test_older_version_logs_warning(self):
        logger = logging.getLogger("test.version.old")
        opener = lambda request, timeout: FakeResponse(
            '{"info": {"version": "1.25.20260408"}}')
        with self.assertLogs(logger, level="WARNING") as captured:
            version_check.check_and_log(
                "Phidget22 - Version 1.23 - Built Oct  6 2025 09:00:00",
                logger, opener=opener)
        self.assertIn("newer version 1.25.20260408", captured.output[0])
        self.assertIn("python3.13", captured.output[0])
        self.assertIn("pip install --upgrade phidget22", captured.output[0])

    def test_network_failure_logs_info_without_raising(self):
        logger = logging.getLogger("test.version.offline")

        def opener(request, timeout):
            raise TimeoutError("timed out")

        with self.assertLogs(logger, level="INFO") as captured:
            version_check.check_and_log(
                "Phidget22 - Version 1.23 - Built Oct  6 2025 09:00:00",
                logger, opener=opener)
        self.assertTrue(captured.output[0].startswith("INFO:"))
        self.assertIn("unable to reach Phidgets", captured.output[0])


if __name__ == "__main__":
    unittest.main()
