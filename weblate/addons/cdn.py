# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar
from uuid import uuid4

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import (
    AddonActivityLogReason,
    AddonEvent,
    AddonEventOutcome,
)
from weblate.addons.forms import CDNFilesForm, CDNJSForm
from weblate.addons.tasks import cdn_parse_html
from weblate.utils.state import STATE_TRANSLATED

CDN_JS_FILENAME = "weblate.js"

if TYPE_CHECKING:
    from weblate.addons.models import Addon
    from weblate.auth.models import User
    from weblate.trans.models import Category, Component, Project, Translation


class CDNBaseAddon(BaseAddon):
    user_name = "cdn"
    user_verbose = "CDN add-on"
    icon = "cloud-upload.svg"
    stay_on_create = True

    @classmethod
    def create_object(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
        acting_user: User | None = None,
        **kwargs,
    ) -> Addon:
        # Generate UUID for the CDN
        if "state" not in kwargs:
            kwargs["state"] = {"uuid": uuid4().hex}
        return super().create_object(
            component=component,
            category=category,
            project=project,
            acting_user=acting_user,
            **kwargs,
        )

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        if (
            not settings.LOCALIZE_CDN_URL
            or not settings.LOCALIZE_CDN_PATH
            or (component is not None and not component.translation_set.exists())
        ):
            return False
        return super().can_install(
            component=component, category=category, project=project
        )

    def cdn_path(self, filename: str) -> str:
        return os.path.join(
            settings.LOCALIZE_CDN_PATH, self.instance.state["uuid"], filename
        )

    def cdn_url(self, filename: str) -> str:
        return os.path.join(
            settings.LOCALIZE_CDN_URL, self.instance.state["uuid"], filename
        )

    @cached_property
    def cdn_base_url(self) -> str:
        return os.path.join(settings.LOCALIZE_CDN_URL, self.instance.state["uuid"])

    def ensure_cdn_dir(self) -> None:
        Path(self.cdn_path("")).mkdir(parents=True, exist_ok=True)

    def write_cdn_text(self, filename: str, content: str) -> None:
        target = Path(self.cdn_path(filename))
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=target.parent, encoding="utf-8"
            ) as handle:
                handle.write(content)
                temporary = handle.name
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def copy_cdn_file(self, source: str, filename: str) -> None:
        target = Path(self.cdn_path(filename))
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", delete=False, dir=target.parent
            ) as handle:
                temporary = handle.name
            shutil.copy2(source, temporary)
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def delete_stale_cdn_files(self, expected: set[str]) -> None:
        root = Path(self.cdn_path(""))
        if not root.exists():
            return

        for path in root.rglob("*"):
            if path.is_file() and path.relative_to(root).as_posix() not in expected:
                path.unlink()

        for path in sorted(
            root.rglob("*"), key=lambda item: len(item.parts), reverse=True
        ):
            if path.is_dir():
                with contextlib.suppress(OSError):
                    path.rmdir()


class CDNJSAddon(CDNBaseAddon):
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_DAILY,
        AddonEvent.EVENT_POST_COMMIT,
        AddonEvent.EVENT_POST_REMOVE,
        AddonEvent.EVENT_POST_UPDATE,
    }
    name = "weblate.cdn.cdnjs"
    version_added = "4.2"
    verbose = gettext_lazy("JavaScript localization CDN")
    description = gettext_lazy(
        "Publishes translations into content delivery network "
        "for use in JavaScript or HTML localization."
    )

    settings_form = CDNJSForm

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        if component is not None and not component.has_template():
            return False
        return super().can_install(
            component=component, category=category, project=project
        )

    @cached_property
    def cdn_js_url(self) -> str:
        return self.cdn_url(CDN_JS_FILENAME)

    def publish_localization(self, component: Component) -> None:
        # Get list of applicable translations
        threshold = self.instance.configuration["threshold"]
        translations = [
            translation
            for translation in component.translation_set.all()
            if (not translation.is_source or component.intermediate)
            and translation.stats.translated > threshold
        ]

        # Create output directory
        self.ensure_cdn_dir()

        # Generate JavaScript loader
        expected = {CDN_JS_FILENAME}
        self.write_cdn_text(
            CDN_JS_FILENAME,
            render_to_string(
                "addons/js/weblate.js.template",
                {
                    "languages": sorted(
                        translation.language.code for translation in translations
                    ),
                    "url": self.cdn_base_url,
                    "cookie_name": self.instance.configuration["cookie_name"],
                    "css_selector": self.instance.configuration["css_selector"],
                },
            ),
        )

        # Generate bilingual JSON files
        for translation in translations:
            filename = f"{translation.language.code}.json"
            self.write_cdn_text(
                filename,
                json.dumps(
                    {
                        unit.source: unit.target
                        for unit in translation.unit_set.filter(
                            state__gte=STATE_TRANSLATED
                        )
                    }
                ),
            )
            expected.add(filename)

        self.delete_stale_cdn_files(expected)

    def post_commit(
        self, component: Component, store_hash: bool, activity_log_id: int | None = None
    ) -> None:
        self.publish_localization(component)

    def daily_component(
        self,
        component: Component,
        activity_log_id: int | None = None,
    ) -> AddonEventOutcome:
        if not self.instance.configuration["files"].strip():
            return AddonEventOutcome.skipped(AddonActivityLogReason.NO_SOURCE_FILES)
        # Trigger parsing files
        cdn_parse_html.delay_on_commit(
            self.instance.id,
            component.id,
            activity_log_id=activity_log_id,
        )
        return AddonEventOutcome.pending()

    def post_update(
        self,
        component: Component,
        previous_head: str,
        skip_push: bool,
        changed_files: list[str],
        parse_after_update: bool = False,
        activity_log_id: int | None = None,
    ) -> AddonEventOutcome:
        return self.daily_component(component, activity_log_id=activity_log_id)

    def post_remove(
        self, translation: Translation, activity_log_id: int | None = None
    ) -> None:
        self.publish_localization(translation.component)


class CDNFilesAddon(CDNBaseAddon):
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_COMPONENT_UPDATE,
        AddonEvent.EVENT_POST_COMMIT,
        AddonEvent.EVENT_POST_REMOVE,
        AddonEvent.EVENT_POST_UPDATE,
    }
    name = "weblate.cdn.files"
    version_added = "2026.5"
    verbose = gettext_lazy("Translation files CDN")
    description = gettext_lazy(
        "Publishes translation files into a content delivery network."
    )
    needs_component = True
    settings_form = CDNFilesForm

    @cached_property
    def cdn_files_url(self) -> str:
        return self.cdn_url("")

    def get_translations(self, component: Component) -> list[Translation]:
        return [
            translation
            for translation in component.translation_set.select_related("language")
            if translation.filename
            and (component.has_template() or not translation.is_source)
        ]

    def get_output_filename(self, translation: Translation, filename: str) -> str:
        language_code = translation.language.code
        if translation.component.file_format_cls.simple_filename:
            return f"{language_code}{Path(translation.filename).suffix}"
        base_path = Path(translation.component.full_path, translation.filename)
        try:
            relative_path = Path(filename).relative_to(base_path)
        except ValueError:
            relative_path = Path(
                os.path.relpath(filename, translation.component.full_path)
            )
        return os.path.join(
            language_code,
            relative_path.as_posix(),
        )

    @staticmethod
    def validate_output_filename(filename: str) -> None:
        if Path(filename).as_posix() == CDN_JS_FILENAME:
            raise ValueError(
                gettext("The translation files CDN add-on cannot publish weblate.js.")
            )

    def publish_files(self, component: Component) -> None:
        self.ensure_cdn_dir()

        expected = set()
        for translation in self.get_translations(component):
            filenames = translation.filenames
            for filename in filenames:
                if not os.path.isfile(filename):
                    continue
                output_filename = self.get_output_filename(
                    translation,
                    filename,
                )
                self.validate_output_filename(output_filename)
                self.copy_cdn_file(filename, output_filename)
                expected.add(output_filename)

        self.delete_stale_cdn_files(expected)

    def post_commit(
        self, component: Component, store_hash: bool, activity_log_id: int | None = None
    ) -> None:
        self.publish_files(component)

    def component_update(
        self, component: Component, activity_log_id: int | None = None
    ) -> None:
        self.publish_files(component)

    def post_remove(
        self, translation: Translation, activity_log_id: int | None = None
    ) -> None:
        self.publish_files(translation.component)

    def post_update(
        self,
        component: Component,
        previous_head: str,
        skip_push: bool,
        changed_files: list[str],
        parse_after_update: bool = False,
        activity_log_id: int | None = None,
    ) -> None:
        self.publish_files(component)
