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

import re

from django.utils.translation import gettext_lazy as _

from weblate.checks.format import BaseFormatCheck

RUBY_FORMAT_MATCH = re.compile(
    r"""
    %(                                 # initial %
      (?:                              # classic printf style
        (?:(?P<ord>\d+)\$)?            # variable order, like %1$s
        (?P<fullvar>
          [ +#*-]*                     # flags
          (?:\d+)?                     # width
          (?:\.\d+)?                   # precision
          (?P<type>[a-zA-Z%])          # type (%s, %d, etc.)
        )
      )|(?:                            # template style
        (?P<t_fullvar>
          [ +#*-]*                     # flags
          (?:\d+)?                     # width
          (?:\.\d+)?                   # precision
          (?:
            (?:
              <(?P<t_field>[^> ]+)>      # named printf reference
              (?P<t_type>[a-zA-Z])       # type (%s, %d, etc.)
            )
          |
            (?:\{(?P<tt_field>[^} ]+)\}) # named reference (implicit %s)
          )
        )
      )
    )
    """,
    re.VERBOSE,
)


class RubyFormatCheck(BaseFormatCheck):
    """Check for Ruby format string.

    Ruby support various format strings (excluding string interpolation):
    - printf syntax: %s, %1$s
    - named printf syntax: %<variable>s
    - template style (implicit %s): %{variable}
    """

    check_id = "ruby_format"
    name = _("Ruby format")
    description = _("Ruby format string does not match source")
    regexp = RUBY_FORMAT_MATCH

    def is_position_based(self, string):
        return string != "%" and not re.search(r"[$<{]", string)
