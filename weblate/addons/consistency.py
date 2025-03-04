# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.tasks import language_consistency

if TYPE_CHECKING:
    from weblate.addons.models import Addon


class LanguageConsistencyAddon(BaseAddon):
    events: set[AddonEvent] = {AddonEvent.EVENT_DAILY, AddonEvent.EVENT_POST_ADD}
    name = "weblate.consistency.languages"
    verbose = gettext_lazy("Add missing languages")
    description = gettext_lazy(
        "Ensures a consistent set of languages is used for all components "
        "within a project."
    )
    icon = "language.svg"
    project_scope = True
    user_name = "languages"
    user_verbose = "Languages add-on"

    def daily(self, component) -> None:
        language_consistency.delay_on_commit(
            self.instance.id,
            [language.id for language in component.project.languages],
            component.project_id,
        )

    def post_add(self, translation) -> None:
        language_consistency.delay_on_commit(
            self.instance.id,
            [translation.language_id],
            translation.component.project_id,
        )


class LangaugeConsistencyAddon(LanguageConsistencyAddon):
    def __init__(self, storage: Addon) -> None:
        super().__init__(storage)
        warnings.warn(
            "LangaugeConsistencyAddon is deprecated, use LanguageConsistencyAddon",
            DeprecationWarning,
            stacklevel=1,
        )
