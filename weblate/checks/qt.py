# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from django.utils.translation import gettext_lazy

from weblate.checks.format import BaseFormatCheck

QT_FORMAT_MATCH = re.compile(
    r"""
    %(                     # initial %
          L?               # optional localized representation of numbers
          (?P<ord>\d{1,2}) # variable order, like %1
    )""",
    re.VERBOSE,
)

QT_PLURAL_MATCH = re.compile(
    r"""
    %(                     # initial %
          L?               # optional localized representation of numbers
          (?P<type>n)      # plural: %n
    )""",
    re.VERBOSE,
)


class QtFormatCheck(BaseFormatCheck):
    """Check for Qt format string."""

    check_id = "qt_format"
    name = gettext_lazy("Qt format")
    description = gettext_lazy("Qt format string does not match source.")
    regexp = QT_FORMAT_MATCH

    def is_position_based(self, string: str) -> bool:
        # everything is numbered
        return False


class QtPluralCheck(BaseFormatCheck):
    """Check for Qt plural string."""

    check_id = "qt_plural_format"
    name = gettext_lazy("Qt plural format")
    description = gettext_lazy("Qt plural format string does not match source.")
    regexp = QT_PLURAL_MATCH

    def is_position_based(self, string: str) -> bool:
        return True
