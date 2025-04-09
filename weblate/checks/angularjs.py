# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Philipp Wolfer <ph.wolfer@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re

from django.utils.translation import gettext_lazy

from .format import BaseFormatCheck

ANGULARJS_INTERPOLATION_MATCH = re.compile(
    r"""
    {{              # start symbol
        \s*         # ignore whitespace
        ((.+?))
        \s*         # ignore whitespace
    }}              # end symbol
    """,
    re.VERBOSE,
)

WHITESPACE = re.compile(r"\s+")


class AngularJSInterpolationCheck(BaseFormatCheck):
    """Check for AngularJS interpolation string."""

    check_id = "angularjs_format"
    name = gettext_lazy("AngularJS interpolation string")
    description = gettext_lazy("AngularJS interpolation strings do not match source.")
    regexp = ANGULARJS_INTERPOLATION_MATCH

    def cleanup_string(self, text: str) -> str:
        return WHITESPACE.sub("", text)
