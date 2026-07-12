# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy

from weblate.addons.models import ADDONS
from weblate.trans.actions import ActionEvents
from weblate.trans.alerts.base import AlertCategory, AlertSeverity, BaseAlert
from weblate.trans.alerts.registry import register
from weblate.utils.docs import get_doc_url

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import User
    from weblate.trans.models.component import Component


XGETTEXT_ALERT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".m",
    ".mm",
    ".php",
    ".pl",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
    ".vala",
}
XGETTEXT_ALERT_IGNORED_DIRS = {
    ".git",
    ".venv",
    "_build",
    "build",
    "dist",
    "locale",
    "locales",
    "node_modules",
    "venv",
}
XGETTEXT_ALERT_SCAN_LIMIT = 2000


def get_locales_parent(component: Component) -> Path | None:
    if not component.new_base:
        return None
    template = Path(component.new_base)
    parts = template.parts
    if "locales" not in parts:
        return None
    locales_index = parts.index("locales")
    if locales_index == 0:
        return Path(component.full_path)
    source_dir = Path(component.full_path).joinpath(*parts[:locales_index])
    return source_dir if source_dir.is_dir() else None


def is_publicly_accessible(component: Component) -> bool:
    return (
        component.project.access_control
        in {component.project.ACCESS_PUBLIC, component.project.ACCESS_PROTECTED}
        and not settings.REQUIRE_LOGIN
    )


class ChecklistAlert(BaseAlert):
    category = AlertCategory.COMMUNITY
    severity = AlertSeverity.WARNING
    dismissible = True
    template_name = "trans/alert/community.html"
    url = ""
    anchor = ""
    configure_permission = "component.edit"

    @classmethod
    def get_url(cls, component: Component) -> str:
        url = reverse(cls.url, kwargs={"path": component.get_url_path()})
        if cls.anchor:
            url = f"{url}#{cls.anchor}"
        return url

    @classmethod
    def is_passing(cls, component: Component) -> bool:
        raise NotImplementedError

    @classmethod
    def check_component(cls, component: Component) -> bool | dict | None:
        if cls.is_relevant(component) and not cls.is_passing(component):
            return {}
        return False

    @classmethod
    def get_configure_permission_object(cls, component: Component):
        return component

    def get_context(self, user: User):
        result = super().get_context(user)
        alert_class = self.__class__
        component = self.instance.component
        configure_url = alert_class.get_url(component)
        doc_url = alert_class.get_doc_url(component, user)
        can_configure = (
            bool(configure_url)
            and configure_url != doc_url
            and user.has_perm(
                alert_class.configure_permission,
                alert_class.get_configure_permission_object(component),
            )
        )
        result["description"] = alert_class.get_description(component)
        result["configure_url"] = configure_url if can_configure else ""
        result["can_configure"] = can_configure
        return result


@register
class MissingRepositoryHook(ChecklistAlert):
    verbose = gettext_lazy(
        "Configure repository hooks for automated flow of updates to Weblate."
    )
    url = "settings"
    anchor = "vcs"

    @classmethod
    def is_passing(cls, component: Component) -> bool:
        return component.change_set.filter(action=ActionEvents.HOOK).exists()

    @classmethod
    def is_relevant(cls, component: Component) -> bool:
        return not component.is_repo_link

    @classmethod
    def get_url(cls, component: Component) -> str:
        return cls.get_doc_url(component)

    @classmethod
    def get_doc_url(cls, _component: Component, user: User | None = None) -> str:
        return get_doc_url("admin/continuous", "update-vcs", user=user)


@register
class MissingPushURL(ChecklistAlert):
    verbose = gettext_lazy(
        "Configure push URL for automated flow of translations from Weblate."
    )
    url = "settings"
    anchor = "vcs"

    @classmethod
    def is_passing(cls, component: Component) -> bool:
        return component.can_push()

    @classmethod
    def get_doc_url(cls, _component: Component, user: User | None = None) -> str:
        return get_doc_url("admin/continuous", "push-changes", user=user)


@register
class MissingTranslationInstructions(ChecklistAlert):
    verbose = gettext_lazy("Define translation instructions to help translators.")
    configure_permission = "project.edit"

    @classmethod
    def is_relevant(cls, component: Component) -> bool:
        return is_publicly_accessible(component)

    @classmethod
    def is_passing(cls, component: Component) -> bool:
        return bool(component.project.instructions)

    @classmethod
    def get_url(cls, component: Component) -> str:
        return reverse("settings", kwargs={"path": component.project.get_url_path()})

    @classmethod
    def get_doc_url(cls, _component: Component, user: User | None = None) -> str:
        return get_doc_url("admin/projects", "project", user=user)

    @classmethod
    def get_configure_permission_object(cls, component: Component):
        return component.project


@register
class MissingScreenshots(ChecklistAlert):
    verbose = gettext_lazy("Add screenshots to show where strings are being used.")
    severity = AlertSeverity.INFO
    url = "screenshots"
    configure_permission = "screenshot.add"

    @classmethod
    def is_passing(cls, component: Component) -> bool:
        # ruff: ignore[import-outside-top-level]
        from weblate.screenshots.models import Screenshot

        return Screenshot.objects.filter(translation__component=component).exists()

    @classmethod
    def get_doc_url(cls, _component: Component, user: User | None = None) -> str:
        return get_doc_url("admin/translating", "screenshots", user=user)


@register
class MissingTranslationFlags(ChecklistAlert):
    verbose = gettext_lazy("Use flags to indicate special strings in your translation.")
    severity = AlertSeverity.INFO
    url = "settings"
    anchor = "show"

    @classmethod
    def is_passing(cls, component: Component) -> bool:
        return (
            bool(component.check_flags)
            or component.source_translation.unit_set.exclude(extra_flags="").exists()
        )

    @classmethod
    def get_doc_url(cls, _component: Component, user: User | None = None) -> str:
        return get_doc_url("admin/checks", "custom-checks", user=user)


@register
class MissingSafeHTMLFlag(ChecklistAlert):
    verbose = gettext_lazy(
        "Add safe-html or auto-safe-html flag to avoid dangerous HTML from translators for strings which are rendered as HTML."
    )
    severity = AlertSeverity.WARNING
    url = "settings"
    anchor = "show"

    @classmethod
    def is_relevant(cls, component: Component) -> bool:
        cache_key = f"alert:safe-html:{component.id}"
        result = cache.get(cache_key)
        if result is not None:
            return result
        result = component.source_translation.unit_set.filter(
            source__contains="<a "
        ).exists()
        cache.set(cache_key, result, 86400)
        return result

    @classmethod
    def is_passing(cls, component: Component) -> bool:
        return (
            "safe-html" in component.check_flags
            or "auto-safe-html" in component.check_flags
            or component.source_translation.unit_set.filter(
                extra_flags__contains="safe-html"
            ).exists()
            or component.source_translation.unit_set.filter(
                extra_flags__contains="auto-safe-html"
            ).exists()
        )

    @classmethod
    def get_doc_url(cls, _component: Component, user: User | None = None) -> str:
        return get_doc_url("user/checks", "check-safe-html", user=user)


class AddonRecommendationAlert(ChecklistAlert):
    verbose = gettext_lazy("Recommended add-on")
    severity = AlertSeverity.INFO
    addon = ""
    url = "addons"

    @classmethod
    def is_passing(cls, component: Component) -> bool:
        return cls.addon in component.addons_cache.names

    @classmethod
    def is_relevant(cls, component: Component) -> bool:
        if cls.addon not in ADDONS:
            return False
        addon = ADDONS[cls.addon]
        return addon.can_install(component=component)

    @classmethod
    def get_description(cls, _component: Component) -> StrOrPromise:
        return format_html(
            "{} {}<br />{}",
            gettext_lazy("Enable add-on:"),
            ADDONS[cls.addon].verbose,
            ADDONS[cls.addon].description,
        )

    @classmethod
    def get_doc_url(cls, _component: Component, user: User | None = None) -> str:
        return get_doc_url(
            "admin/addons", ADDONS[cls.addon].get_doc_anchor(), user=user
        )


@register
class RecommendedLanguageConsistencyAddon(AddonRecommendationAlert):
    addon = "weblate.consistency.languages"

    @classmethod
    def is_relevant(cls, component: Component) -> bool:
        if component.project.component_set.exclude(is_glossary=True).count() <= 1:
            return False
        return super().is_relevant(component)


@register
class RecommendedLinguasAddon(AddonRecommendationAlert):
    addon = "weblate.gettext.linguas"


@register
class RecommendedConfigureAddon(AddonRecommendationAlert):
    addon = "weblate.gettext.configure"


@register
class RecommendedCleanupAddon(AddonRecommendationAlert):
    addon = "weblate.cleanup.generic"


@register
class RecommendedGenerateMoAddon(AddonRecommendationAlert):
    addon = "weblate.gettext.mo"

    @classmethod
    def is_relevant(cls, component: Component) -> bool:
        if not super().is_relevant(component):
            return False
        translations = component.translation_set.exclude(
            pk=component.source_translation.id
        )
        try:
            translation = translations[0]
        except IndexError:
            return False
        try:
            filename = translation.get_filename()
        except ValidationError:
            return False
        if filename is None or not filename.endswith(".po"):
            return False
        mofilename = f"{filename[:-3]}.mo"
        return os.path.exists(mofilename)


@register
class RecommendedXgettextAddon(AddonRecommendationAlert):
    addon = "weblate.gettext.xgettext"

    @classmethod
    def is_relevant(cls, component: Component) -> bool:
        if not super().is_relevant(component):
            return False
        if not component.new_base or Path(component.new_base).stem in {
            "django",
            "djangojs",
            "docs",
        }:
            return False

        scanned = 0
        for _root, dirs, files in os.walk(component.full_path):
            dirs[:] = [name for name in dirs if name not in XGETTEXT_ALERT_IGNORED_DIRS]
            for filename in files:
                scanned += 1
                if scanned > XGETTEXT_ALERT_SCAN_LIMIT:
                    return False
                if os.path.splitext(filename)[1] in XGETTEXT_ALERT_SUFFIXES:
                    return True
        return False


@register
class RecommendedMesonAddon(AddonRecommendationAlert):
    addon = "weblate.gettext.meson"


@register
class RecommendedDjangoAddon(AddonRecommendationAlert):
    addon = "weblate.gettext.django"

    @classmethod
    def is_relevant(cls, component: Component) -> bool:
        if not component.new_base:
            return False
        return super().is_relevant(component) and Path(component.new_base).stem in {
            "django",
            "djangojs",
        }


@register
class RecommendedSphinxAddon(AddonRecommendationAlert):
    addon = "weblate.gettext.sphinx"

    @classmethod
    def is_relevant(cls, component: Component) -> bool:
        if not super().is_relevant(component):
            return False
        if not component.new_base:
            return False
        if Path(component.new_base).stem != "docs":
            return False
        source_dir = get_locales_parent(component)
        if source_dir is None:
            return False
        if not (source_dir / "conf.py").exists():
            return False

        scanned = 0
        for _root, dirs, files in os.walk(source_dir):
            dirs[:] = [name for name in dirs if name not in XGETTEXT_ALERT_IGNORED_DIRS]
            for filename in files:
                scanned += 1
                if scanned > XGETTEXT_ALERT_SCAN_LIMIT:
                    return False
                if filename.endswith(".rst"):
                    return True
        return False
