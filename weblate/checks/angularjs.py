# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Philipp Wolfer <ph.wolfer@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from .format import BaseFormatCheck

if TYPE_CHECKING:
    from collections.abc import Iterable

ANGULARJS_INTERPOLATION_MATCH = re.compile(
    r"""
    {{              # start symbol
        (           # interpolation expression
            (?:
                (?!}})  # stop at the closing delimiter
                [\s\S]
            )+
        )
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

    def iter_matches(self, string: str) -> Iterable[re.Match[str]]:
        closing = string.rfind("}}")
        if closing == -1:
            return ()
        return ANGULARJS_INTERPOLATION_MATCH.finditer(string, 0, closing + 2)

    def cleanup_string(self, text: str) -> str:
        return WHITESPACE.sub("", text)
