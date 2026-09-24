# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Kotlin SDK CDN add-on configuration and event adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django import forms
from django.utils.translation import gettext_lazy

from weblate.addons.cdn import CDNBaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import BaseAddonForm
from weblate.kotlin_sdk.api import get_api_urls
from weblate.kotlin_sdk.publication import Publication

if TYPE_CHECKING:
    from django.urls.resolvers import URLPattern

    from weblate.trans.models import Component, Translation


class KotlinSDKForm(BaseAddonForm):
    public_configuration_fields = frozenset({"maximum_age", "maximum_versions"})
    maximum_age = forms.IntegerField(
        label=gettext_lazy("Maximum build age (days)"),
        min_value=1,
        max_value=730,
        initial=365,
    )
    maximum_versions = forms.IntegerField(
        label=gettext_lazy("Maximum retained versions"),
        min_value=1,
        max_value=100,
        initial=20,
    )


class KotlinSDKAddon(CDNBaseAddon):
    name = "weblate.cdn.kotlin"
    api_name = "kotlin-sdk"
    verbose = gettext_lazy("Kotlin SDK CDN")
    description = gettext_lazy(
        "Publishes Android string and plural resources for registered Kotlin SDK builds."
    )
    version_added = "2026.10"
    needs_component = True
    compat: ClassVar = {"file_format": {"aresource"}}
    settings_form = KotlinSDKForm
    events: ClassVar = {
        AddonEvent.EVENT_POST_COMMIT,
        AddonEvent.EVENT_POST_UPDATE,
        AddonEvent.EVENT_POST_REMOVE,
        AddonEvent.EVENT_COMPONENT_UPDATE,
        AddonEvent.EVENT_DAILY,
    }

    @classmethod
    def get_api_urls(cls) -> tuple[URLPattern, ...]:
        return get_api_urls()

    def schedule(self) -> None:
        Publication(self.instance).schedule()

    def post_commit(
        self, component: Component, store_hash: bool, activity_log_id: int | None = None
    ) -> None:
        self.schedule()

    def post_update(
        self,
        component: Component,
        previous_head: str,
        skip_push: bool,
        changed_files: list[str],
        parse_after_update: bool = False,
        activity_log_id: int | None = None,
    ) -> None:
        self.schedule()

    def post_remove(
        self, translation: Translation, activity_log_id: int | None = None
    ) -> None:
        self.schedule()

    def component_update(
        self, component: Component, activity_log_id: int | None = None
    ) -> None:
        self.schedule()

    def daily_component(
        self, component: Component, activity_log_id: int | None = None
    ) -> None:
        self.schedule()
