# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Readiness tests, run inside the development Python environment."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from django.db import DatabaseError
from doctor import check_browser, wait_for_services
from redis.exceptions import ConnectionError as RedisConnectionError
from selenium.common.exceptions import WebDriverException

from weblate.trans.tests.browser import create_browser


class ReadinessTests(unittest.TestCase):
    def test_database_startup_retry(self) -> None:
        cache = MagicMock()
        with (
            patch("doctor.connection") as database,
            patch("doctor.time.sleep") as sleep,
        ):
            database.cursor.side_effect = [DatabaseError("starting"), MagicMock()]
            wait_for_services(cache)
        database.close.assert_called_once()
        sleep.assert_called_once_with(1)
        cache.ping.assert_called_once()

    def test_valkey_timeout(self) -> None:
        cache = MagicMock()
        cache.ping.side_effect = RedisConnectionError("private diagnostic")
        with (
            patch("doctor.connection"),
            patch("doctor.time.monotonic", side_effect=[0, 61]),
            patch("doctor.time.sleep") as sleep,
            self.assertRaisesRegex(SystemExit, "unavailable after 60 seconds") as error,
        ):
            wait_for_services(cache)
        self.assertNotIn("private diagnostic", str(error.exception))
        sleep.assert_not_called()


class BrowserTests(unittest.TestCase):
    def test_explicit_executables_and_locale_restoration(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {
                    "LANG": "cs_CZ.UTF-8",
                    "WEBLATE_TEST_CHROME_BINARY": "/usr/bin/chromium",
                    "WEBLATE_TEST_CHROMEDRIVER": "/usr/bin/chromedriver",
                },
            ),
            patch(
                "weblate.trans.tests.browser.webdriver.Chrome",
                side_effect=WebDriverException("missing"),
            ) as chrome,
            self.assertRaises(WebDriverException),
        ):
            try:
                create_browser()
            finally:
                self.assertEqual(os.environ["LANG"], "cs_CZ.UTF-8")
                self.assertEqual(
                    chrome.call_args.kwargs["options"].binary_location,
                    "/usr/bin/chromium",
                )
                self.assertEqual(
                    chrome.call_args.kwargs["service"].path, "/usr/bin/chromedriver"
                )

    def test_browser_page_and_cleanup(self) -> None:
        for result in ("Ready", "Loading"):
            with (
                self.subTest(result=result),
                patch("doctor.ThreadingHTTPServer") as server_factory,
                patch("doctor.Thread") as thread_factory,
                patch("doctor.create_browser") as create,
            ):
                server = server_factory.return_value.__enter__.return_value
                server.server_port = 12345
                browser = create.return_value.__enter__.return_value
                browser.title = "Weblate browser check"
                browser.execute_script.return_value = result
                if result == "Ready":
                    check_browser()
                else:
                    with self.assertRaisesRegex(RuntimeError, "execute JavaScript"):
                        check_browser()
                browser.get.assert_called_once_with("http://127.0.0.1:12345/")
                create.return_value.__exit__.assert_called_once()
                server.shutdown.assert_called_once()
                thread_factory.return_value.join.assert_called_once()

    def test_browser_launch_failure_cleans_server(self) -> None:
        with (
            patch("doctor.ThreadingHTTPServer") as server_factory,
            patch("doctor.Thread"),
            patch("doctor.create_browser", side_effect=WebDriverException("missing")),
            self.assertRaises(WebDriverException),
        ):
            check_browser()
        server_factory.return_value.__enter__.return_value.shutdown.assert_called_once()


if __name__ == "__main__":
    unittest.main()
