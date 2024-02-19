# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Simple quality check example."""

from django.utils.translation import gettext_lazy

from weblate.checks.base import TargetCheck


class FooCheck(TargetCheck):
    # Used as identifier for check, should be unique
    # Has to be shorter than 50 characters
    check_id = "foo"

    # Short name used to display failing check
    name = gettext_lazy("Foo check")

    # Description for failing check
    description = gettext_lazy("Your translation is foo")

    # Real check code
    def check_single(self, source, target, unit):
        return "foo" in target
