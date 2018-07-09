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

"""
Django settings for running testsuite using django-nose.
Django-nose have some advantages over default django test suite, most notable
are:
- It will testing just your weblate by default, not all the standard things
  that happen to be in INSTALLED_APPS. On my installation many django tests
  fail for unrelated to weblate reasons.
- It will let more precise specification of what tests to run.
"""

from weblate.settings_test import *  # noqa

INSTALLED_APPS = INSTALLED_APPS + ('django_nose', )

TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'

# Override default test match regexp (?:^|[\\b_\\.-])[Tt]est.
# It will match things like get_test_file which is not a test.
NOSE_ARGS = [r'--match=(?:^|[\b_\./-])^[Tt]est', ]
