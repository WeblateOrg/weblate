# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys


def main(argv=None, developer_mode: bool = False) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")

    from weblate.utils.management import WeblateManagementUtility

    if argv is None:
        argv = sys.argv
    try:
        # This is essentially Django's execute_from_command_line
        utility = WeblateManagementUtility(argv=argv, developer_mode=developer_mode)
        utility.execute()
    except Exception:
        try:
            from weblate.utils.errors import report_error

            report_error("Command failed")
        except ImportError:
            pass
        raise


if __name__ == "__main__":
    main()
