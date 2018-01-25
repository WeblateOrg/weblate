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
"""Wrapper to execute Django tests from setup.py."""

import os
import sys

os.environ['DJANGO_SETTINGS_MODULE'] = 'weblate.settings_test'
TEST_DIR = os.path.dirname(__file__)
sys.path.insert(0, TEST_DIR)

# pylint: disable=wrong-import-position
from django.core.management import execute_from_command_line  # noqa


def runtests():
    execute_from_command_line(['setup.py', 'test'])
    # We get here only if tests do not fail
    sys.exit(0)


if __name__ == '__main__':
    runtests()
