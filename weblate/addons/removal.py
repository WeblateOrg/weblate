# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta

from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import RemoveForm, RemoveSuggestionForm
from weblate.trans.models import Comment, Suggestion


class RemovalAddon(BaseAddon):
    project_scope = True
    events: set[AddonEvent] = {
        AddonEvent.EVENT_DAILY,
    }
    settings_form = RemoveForm
    icon = "delete.svg"

    def get_cutoff(self):
        age = self.instance.configuration["age"]
        return timezone.now() - timedelta(days=age)

    def delete_older(self, objects, component) -> None:
        count = objects.filter(timestamp__lt=self.get_cutoff()).delete()[0]
        if count:
            component.invalidate_cache()


class RemoveComments(RemovalAddon):
    name = "weblate.removal.comments"
    verbose = gettext_lazy("Stale comment removal")
    description = gettext_lazy("Set a timeframe for removal of comments.")

    def daily(self, component) -> None:
        self.delete_older(
            Comment.objects.filter(
                unit__translation__component__project=component.project
            ),
            component,
        )


class RemoveSuggestions(RemovalAddon):
    name = "weblate.removal.suggestions"
    verbose = gettext_lazy("Stale suggestion removal")
    description = gettext_lazy("Set a timeframe for removal of suggestions.")
    settings_form = RemoveSuggestionForm

    def daily(self, component) -> None:
        self.delete_older(
            Suggestion.objects.filter(
                unit__translation__component__project=component.project
            )
            .annotate(Sum("vote__value"))
            .filter(
                Q(vote__value__sum__lte=self.instance.configuration.get("votes", 0))
                | Q(vote__value__sum=None)
            ),
            component,
        )
