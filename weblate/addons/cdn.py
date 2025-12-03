# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar
from uuid import uuid4

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import CDNJSForm
from weblate.addons.tasks import cdn_parse_html
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.addons.models import Addon
    from weblate.auth.models import User
    from weblate.trans.models import Component, Project


class CDNJSAddon(BaseAddon):
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_DAILY,
        AddonEvent.EVENT_POST_COMMIT,
        AddonEvent.EVENT_POST_UPDATE,
    }
    name = "weblate.cdn.cdnjs"
    verbose = gettext_lazy("JavaScript localization CDN")
    description = gettext_lazy(
        "Publishes translations into content delivery network "
        "for use in JavaScript or HTML localization."
    )
    user_name = "cdn"
    user_verbose = "CDN add-on"

    settings_form = CDNJSForm
    icon = "cloud-upload.svg"
    stay_on_create = True

    @classmethod
    def create_object(
        cls,
        *,
        component: Component | None = None,
        project: Project | None = None,
        acting_user: User | None = None,
        **kwargs,
    ) -> Addon:
        # Generate UUID for the CDN
        if "state" not in kwargs:
            kwargs["state"] = {"uuid": uuid4().hex}
        return super().create_object(
            component=component, project=project, acting_user=acting_user, **kwargs
        )

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        project: Project | None = None,
    ) -> bool:
        if (
            not settings.LOCALIZE_CDN_URL
            or not settings.LOCALIZE_CDN_PATH
            or (
                component is not None
                and (
                    not component.has_template()
                    or not component.translation_set.exists()
                )
            )
        ):
            return False
        return super().can_install(component=component, project=project)

    def cdn_path(self, filename: str) -> str:
        return os.path.join(
            settings.LOCALIZE_CDN_PATH, self.instance.state["uuid"], filename
        )

    @cached_property
    def cdn_js_url(self) -> str:
        return os.path.join(
            settings.LOCALIZE_CDN_URL, self.instance.state["uuid"], "weblate.js"
        )

    def post_commit(
        self, component: Component, store_hash: bool, activity_log_id: int | None = None
    ) -> None:
        # Get list of applicable translations
        threshold = self.instance.configuration["threshold"]
        translations = [
            translation
            for translation in component.translation_set.all()
            if (not translation.is_source or component.intermediate)
            and translation.stats.translated > threshold
        ]

        # Create output directory
        dirname = self.cdn_path("")
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        # Generate JavasScript loader
        Path(self.cdn_path("weblate.js")).write_text(
            render_to_string(
                "addons/js/weblate.js.template",
                {
                    "languages": sorted(
                        translation.language.code for translation in translations
                    ),
                    "url": os.path.join(
                        settings.LOCALIZE_CDN_URL, self.instance.state["uuid"]
                    ),
                    "cookie_name": self.instance.configuration["cookie_name"],
                    "css_selector": self.instance.configuration["css_selector"],
                },
            ),
            encoding="utf-8",
        )

        # Generate bilingual JSON files
        for translation in translations:
            with open(
                self.cdn_path(f"{translation.language.code}.json"),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    {
                        unit.source: unit.target
                        for unit in translation.unit_set.filter(
                            state__gte=STATE_TRANSLATED
                        )
                    },
                    handle,
                )

    def daily(self, component: Component, activity_log_id: int | None = None) -> None:
        if not self.instance.configuration["files"].strip():
            return
        # Trigger parsing files
        cdn_parse_html.delay(self.instance.id, component.id)

    def post_update(
        self,
        component: Component,
        previous_head: str,
        skip_push: bool,
        activity_log_id: int | None = None,
    ) -> None:
        self.daily(component)
