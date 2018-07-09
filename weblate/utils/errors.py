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
from __future__ import unicode_literals

import sys
import traceback

from django.conf import settings
from django.utils.encoding import force_text

from weblate.logger import LOGGER

try:
    import rollbar
    HAS_ROLLBAR = True
except ImportError:
    HAS_ROLLBAR = False


def report_error(error, exc_info, request=None, extra_data=None, level=None):
    """Wrapper for error reporting

    This can be used for store exceptions in error reporting solutions as
    rollbar while handling error gracefully and giving user cleaner message.
    """
    if HAS_ROLLBAR and hasattr(settings, 'ROLLBAR'):
        rollbar.report_exc_info(
            exc_info, request, extra_data=extra_data, level=level
        )

    LOGGER.error(
        'Handled exception %s: %s',
        error.__class__.__name__,
        force_text(error).encode('utf-8')
    )

    # Print error when running testsuite
    if sys.argv[1:2] == ['test']:
        traceback.print_exc()
