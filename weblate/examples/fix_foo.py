from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.trans.autofixes.base import AutoFix

if TYPE_CHECKING:
    from weblate.trans.models import Unit


class ReplaceFooWithBar(AutoFix):
    """Replace foo with bar."""

    # Might be localized using gettext_lazy
    name = "Foobar"

    def fix_single_target(
        self, target: str, source: str, unit: Unit
    ) -> tuple[str, bool]:
        if "foo" in target:
            return target.replace("foo", "bar"), True
        return target, False
