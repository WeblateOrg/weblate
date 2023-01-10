#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys

if __name__ == "__main__":
    default = "weblate.settings"
    if len(sys.argv) >= 2 and sys.argv[1] == "test":
        default = "weblate.settings_test"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default)

    from weblate.runner import main

    main(developer_mode=True)
