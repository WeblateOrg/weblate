# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Kotlin SDK CDN add-on configuration and event adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy

from weblate.addons.cdn import CDNBaseAddon, CDNFilesAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import BaseAddonForm
from weblate.kotlin_sdk.api import get_api_urls
from weblate.kotlin_sdk.publication import Publication
from weblate.utils.change_origin import get_acting_user
from weblate.utils.site import get_site_url

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.urls.resolvers import URLPattern

    from weblate.addons.models import Addon
    from weblate.auth.models import User
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

    install_translation_files = forms.BooleanField(
        label=gettext_lazy("Install Translation files CDN"),
        required=False,
        initial=True,
        help_text=gettext_lazy(
            "Publishes original translation files publicly, including files from private components."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:  # ruff: ignore[missing-type-args, missing-type-kwargs]
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(Field("maximum_age"), Field("maximum_versions"))
        if self._addon.instance.pk is None and not self._addon.documentation_build:
            self.helper.layout.append(Field("install_translation_files"))
        else:
            del self.fields["install_translation_files"]

    def serialize_form(self) -> dict[str, int | bool]:
        data = dict(super().serialize_form())
        install = data.pop("install_translation_files", False)
        if self._addon.instance.pk is None and install:
            data["_install_translation_files"] = True
        return data


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

    def get_translation_files_addon(self) -> Addon | None:
        from weblate.addons.models import Addon  # ruff: ignore[import-outside-top-level]

        return Addon.objects.filter(
            component=self.instance.component, name=CDNFilesAddon.name
        ).first()

    def post_configure(self, run: bool = True) -> None:
        if self.instance.configuration.pop("_install_translation_files", False):
            component = self.instance.component
            if component is not None and self.get_translation_files_addon() is None:
                if not CDNFilesAddon.can_install(component=component):
                    raise ValidationError(
                        gettext_lazy(
                            "Translation files CDN cannot be installed on this component."
                        )
                    )
                CDNFilesAddon.create(
                    component=component, acting_user=get_acting_user(), run=run
                )
                component.drop_addons_cache()
            self.instance.save(update_fields=["configuration"])
        super().post_configure(run=run)

    def get_integration_instructions(
        self, user: User, request: HttpRequest | None = None
    ) -> str:
        component = self.instance.component
        if not self.instance.pk or component is None:
            return ""
        component_path = "%2F".join(component.get_url_path()[1:])
        files_addon = self.get_translation_files_addon()
        snippet = (
            "weblate {\n"
            f'    serverUrl = "{get_site_url()}"\n'
            '    authToken = "INSERT_TOKEN_HERE"\n'
            f'    project = "{component.project.slug}"\n'
            f'    component = "{component_path}"\n'
        )
        if files_addon is not None:
            snippet += (
                "\n    translationFiles {\n"
                f'        cdnUrl = "{CDNFilesAddon(files_addon).cdn_base_url}"\n'
                "    }\n"
            )
        snippet += (
            f'\n    kotlinSdk {{\n        cdnUrl = "{self.cdn_base_url}"\n    }}\n}}'
        )
        return render_to_string(
            "addons/kotlin.html",
            {
                "snippet": snippet,
                "project": component.project,
                "user": user,
                "component": component,
                "files_addon_missing": files_addon is None,
                "can_install_files": request is not None
                and files_addon is None
                and user.has_perm("component.edit", component)
                and CDNFilesAddon.can_install(component=component),
            },
            request=request,
        )

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
