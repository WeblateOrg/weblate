# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from django.utils.translation import gettext_lazy

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
    """
    Check for Ruby format string.

    Ruby support various format strings (excluding string interpolation):
    - printf syntax: %s, %1$s
    - named printf syntax: %<variable>s
    - template style (implicit %s): %{variable}
    """

    check_id = "ruby_format"
    name = gettext_lazy("Ruby format")
    description = gettext_lazy("Ruby format string does not match source.")
    regexp = RUBY_FORMAT_MATCH

    def is_position_based(self, string: str):
        return string != "%" and not re.search(r"[$<{]", string)
