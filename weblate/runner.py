#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import os
import sys


def main(argv=None, developer_mode: bool = False):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")

    from weblate.utils.management import WeblateManagementUtility

    if argv is None:
        argv = sys.argv
    try:
        # This is essentially Django's execute_from_command_line
        utility = WeblateManagementUtility(argv=argv, developer_mode=developer_mode)
        utility.execute()
    except Exception:
        from weblate.utils.errors import report_error

        report_error()
        raise


if __name__ == "__main__":
    main()
