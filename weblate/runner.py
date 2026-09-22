# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import sys
from contextlib import suppress


def main(argv: list[str] | None = None, developer_mode: bool = False) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")

    # ruff: ignore[import-outside-top-level]
    from weblate.utils.management.utility import (
        WeblateManagementUtility,
    )

    if argv is None:
        argv = sys.argv
    try:
        # This is essentially Django's execute_from_command_line
        utility = WeblateManagementUtility(argv=argv, developer_mode=developer_mode)
        utility.execute()
    except Exception:
        with suppress(ImportError):
            # ruff: ignore[import-outside-top-level]
            from weblate.utils.errors import report_error

            report_error("Command failed")
        raise


if __name__ == "__main__":
    main()
