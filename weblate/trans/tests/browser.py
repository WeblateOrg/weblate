# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared local Chrome setup for Selenium tests and development diagnostics."""

from __future__ import annotations

import os
from unittest.mock import patch

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def create_browser() -> webdriver.Chrome:
    options = Options()
    # Run headless
    options.add_argument("--headless=new")
    # Seems to help in some corner cases, see
    # https://stackoverflow.com/a/50642913/225718
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    # Force Chrome in English
    options.add_argument("--lang=en")
    # Accept English as primary language, this does not seem to work
    options.add_experimental_option("prefs", {"intl.accept_languages": "en,en_US"})

    if binary := os.environ.get("WEBLATE_TEST_CHROME_BINARY"):
        options.binary_location = binary
    service = Service(executable_path=os.environ.get("WEBLATE_TEST_CHROMEDRIVER"))
    # Force English locales, the --lang and accept_language settings does not
    # work in some cases. Restore the original locale even if startup fails.
    with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}):
        return webdriver.Chrome(options=options, service=service)
