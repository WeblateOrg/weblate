# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File format specific behavior."""

import os.path

from weblate.formats.tests.test_formats import BaseFormatTest
from weblate.formats.txt import AppStoreFormat
from weblate.trans.tests.utils import get_test_file

APPSTORE_FILE = get_test_file("short_description.txt")


class AppStoreFormatTest(BaseFormatTest):
    format_class = AppStoreFormat
    FILE = APPSTORE_FILE
    MIME = "text/plain"
    EXT = "txt"
    COUNT = 2
    MASK = "market/*"
    EXPECTED_PATH = "market/cs-CZ"
    FIND = "Hello world"
    FIND_CONTEXT = "short_description.txt:1"
    FIND_MATCH = "Hello world"
    MATCH = None
    BASE = os.path.dirname(APPSTORE_FILE)
    EXPECTED_FLAGS = "max-length:80"

    def parse_file(self, filename):
        if not os.path.isdir(filename):
            filename = os.path.dirname(filename)
        return self.format_class(filename)
