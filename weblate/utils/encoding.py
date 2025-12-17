# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import locale
import sys


def get_filesystem_encoding() -> str:
    return sys.getfilesystemencoding()


def get_python_encoding() -> str:
    return sys.getdefaultencoding()


def get_locale_encoding() -> str:
    encoding = locale.getlocale()[1]
    if not encoding:
        return ""
    return encoding.lower()


def get_encoding_list() -> list[str]:
    return [get_filesystem_encoding(), get_locale_encoding()]
