# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.filter import FILTERS


class TranslationChecklist(list):
    """Simple list wrapper for translation checklist."""

    def add_if(self, stats, name, level) -> None:
        """Add to list if there are matches."""
        if getattr(stats, name) > 0:
            self.add(stats, name, level)

    def add(self, stats, name, level) -> None:
        """Add item to the list."""
        self.append(
            (
                FILTERS.get_filter_query(name),
                FILTERS.get_filter_name(name),
                getattr(stats, name),
                level,
                getattr(stats, f"{name}_words"),
                getattr(stats, f"{name}_chars"),
            )
        )
