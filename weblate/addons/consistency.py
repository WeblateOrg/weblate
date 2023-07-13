# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.models import Q
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_DAILY, EVENT_POST_ADD
from weblate.addons.tasks import language_consistency
from weblate.lang.models import Language


class LangaugeConsistencyAddon(BaseAddon):
    events = (EVENT_DAILY, EVENT_POST_ADD)
    name = "weblate.consistency.languages"
    verbose = gettext_lazy("Add missing languages")
    description = gettext_lazy(
        "Ensures a consistent set of languages is used for all components "
        "within a project."
    )
    icon = "language.svg"
    project_scope = True

    def daily(self, component):
        language_consistency.delay(
            component.project_id,
            list(
                Language.objects.filter(
                    Q(translation__component=component) | Q(component=component)
                ).values_list("pk", flat=True)
            ),
        )

    def post_add(self, translation):
        language_consistency.delay(
            translation.component.project_id,
            [translation.language_id],
        )
