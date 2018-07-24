# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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


def main(argv=None):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")
    os.environ['DJANGO_IS_MANAGEMENT_COMMAND'] = '1'

    from django.core.management import execute_from_command_line

    if argv is None:
        argv = sys.argv
    try:
        execute_from_command_line(argv)
    except Exception as error:
        from weblate.utils.errors import report_error
        report_error(error, sys.exc_info())
        raise


if __name__ == "__main__":
    main()
