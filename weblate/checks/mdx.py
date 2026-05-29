# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.checks.base import TargetCheck

if TYPE_CHECKING:
    from weblate.trans.models import Unit


class SafeMDXCheck(TargetCheck):
    """Check for unsafe MDX content."""

    check_id = "safe-mdx"
    name = gettext_lazy("Safe MDX")
    description = gettext_lazy("The MDX content is safe.")
    version_added = "2026.7"

    def get_jsx_expression_matches(self, text: str):
        # matches expressions like {props.name.toUpperCase()}
        jsx_expression_pattern = r"\{[^{}]+\}"
        for match in re.finditer(jsx_expression_pattern, text):
            yield match.group()

    def check_single(self, source: str, target: str, unit: Unit):
        """Check if the target string contains the same JSX expressions as the source string."""
        expected = set(self.get_jsx_expression_matches(source))
        found = set(self.get_jsx_expression_matches(target))
        return found != expected
