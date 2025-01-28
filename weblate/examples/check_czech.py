# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Quality check example for Czech plurals."""

from django.utils.translation import gettext_lazy

from weblate.checks.base import TargetCheck


class PluralCzechCheck(TargetCheck):
    # Used as identifier for check, should be unique
    # Has to be shorter than 50 characters
    check_id = "foo"

    # Short name used to display failing check
    name = gettext_lazy("Foo check")

    # Description for failing check
    description = gettext_lazy("Your translation is foo")

    # Real check code
    def check_target_unit(self, sources, targets, unit):
        if unit.translation.language.is_base({"cs"}):
            return targets[1] == targets[2]
        return False

    def check_single(self, source, target, unit) -> bool:
        """We don't check target strings here."""
        return False
