"""Simple quality check example."""

from django.utils.translation import gettext_lazy

from weblate.checks.base import TargetCheck


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
    def check_single(self, source, target, unit):
        return "foo" in target
