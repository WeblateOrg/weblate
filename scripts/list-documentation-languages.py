#!/usr/bin/env python

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "weblate-language-data==2025.2",
# ]
# ///

import json

from weblate_language_data.docs import DOCUMENTATION_LANGUAGES

languages = list(DOCUMENTATION_LANGUAGES.values())

print(f"languages={json.dumps(languages)}")
