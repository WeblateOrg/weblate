"""Simple quality check example."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.checks.base import TargetCheck

if TYPE_CHECKING:
    from weblate.trans.models import Unit


class FooCheck(TargetCheck):
    # Used as identifier for check, should be unique
    # Has to be shorter than 50 characters
    check_id = "foo"

    # Short name used to display failing check
    # Might be localized using gettext_lazy
    name = "Foo check"

    # Description for failing check
    description = gettext_lazy("Your translation is foo")

    # Real check code
    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        return "foo" in target
