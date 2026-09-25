# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Kotlin SDK CDN add-on configuration and event adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.utils.translation import gettext_lazy

from weblate.addons.cdn import CDNBaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import BaseAddonForm
from weblate.kotlin_sdk.api import get_api_urls
from weblate.kotlin_sdk.publication import Publication
from weblate.utils.forms import ContextDiv
from weblate.utils.site import get_site_url

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
        help_text=gettext_lazy(
            "Retires builds this many days after their first registration. "
            "Re-registering a build does not extend its age."
        ),
    )
    maximum_versions = forms.IntegerField(
        label=gettext_lazy("Maximum retained versions"),
        min_value=1,
        max_value=100,
        initial=20,
        help_text=gettext_lazy(
            "Limits retained builds across all package names. A build is retired "
            "when either this limit or the maximum age is reached."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:  # ruff: ignore[missing-type-args, missing-type-kwargs]
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(Field("maximum_age"), Field("maximum_versions"))
        if self.is_bound and self._addon.instance.pk:
            component = self._addon.instance.component
            if component is not None:
                component_path = "%2F".join(component.get_url_path()[1:])
                snippet = (
                    "weblate {\n"
                    f'    serverUrl = "{get_site_url()}"\n'
                    f'    cdnUrl = "{self._addon.cdn_base_url}"\n'
                    '    authToken = "INSERT_TOKEN_HERE"\n'
                    f'    project = "{component.project.slug}"\n'
                    f'    component = "{component_path}"\n'
                    "}"
                )
                self.helper.layout.insert(
                    0,
                    ContextDiv(
                        template="addons/kotlin.html",
                        context={
                            "snippet": snippet,
                            "project": component.project,
                            "user": self.user,
                        },
                    ),
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
