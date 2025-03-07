# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING

import sentry_sdk
from django.conf import settings
from django.db import models
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy
from weblate_language_data.ambiguous import AMBIGUOUS
from weblate_language_data.countries import DEFAULT_LANGS

from weblate.formats.models import FILE_FORMATS
from weblate.trans.actions import ActionEvents
from weblate.utils.requests import get_uri_error
from weblate.utils.state import STATE_TRANSLATED
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import User
    from weblate.trans.models.component import Component, ComponentQuerySet
    from weblate.trans.models.translation import Translation, TranslationQuerySet


ALERTS: dict[str, type[BaseAlert]] = {}
ALERTS_IMPORT: set[str] = set()


def register(cls):
    name = cls.__name__
    ALERTS[name] = cls
    if cls.on_import:
        ALERTS_IMPORT.add(name)
    return cls


def update_alerts(component: Component, alerts: set[str] | None = None) -> None:
    for name, alert in ALERTS.items():
        if alerts and name not in alerts:
            continue
        with sentry_sdk.start_span(op="alerts.update", name=f"ALERT {name}"):
            result = alert.check_component(component)
            if result is None:
                continue
            if isinstance(result, dict):
                component.add_alert(alert.__name__, **result)
            elif result:
                component.add_alert(alert.__name__)
            else:
                component.delete_alert(alert.__name__)


class Alert(models.Model):
    component = models.ForeignKey(
        "trans.Component", on_delete=models.deletion.CASCADE, db_index=False
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=150)
    dismissed = models.BooleanField(default=False, db_index=True)
    details = models.JSONField(default=dict)

    class Meta:
        unique_together = [("component", "name")]
        verbose_name = "component alert"
        verbose_name_plural = "component alerts"

    def __str__(self) -> str:
        return str(self.obj.verbose)

    def save(self, *args, **kwargs) -> None:
        is_new = not self.id
        super().save(*args, **kwargs)
        if is_new:
            self.component.change_set.create(
                action=ActionEvents.ALERT,
                alert=self,
                details={"alert": self.name},
            )

    @cached_property
    def obj(self):
        return ALERTS[self.name](self, **self.details)

    def render(self, user: User):
        return self.obj.render(user)


class BaseAlert:
    verbose: StrOrPromise = ""
    on_import = False
    link_wide = False
    project_wide = False
    dismissable = False
    doc_page = ""
    doc_anchor = ""

    def __init__(self, instance) -> None:
        self.instance = instance

    def get_analysis(self):
        return {}

    def get_context(self, user: User):
        result = {
            "alert": self.instance,
            "component": self.instance.component,
            "timestamp": self.instance.timestamp,
            "details": self.instance.details,
            "analysis": self.get_analysis(),
            "user": user,
        }
        result.update(self.instance.details)
        return result

    def render(self, user: User):
        return render_to_string(
            f"trans/alert/{self.__class__.__name__.lower()}.html",
            self.get_context(user),
        )

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:  # noqa: ARG004
        return None


class ErrorAlert(BaseAlert):
    def __init__(self, instance, error) -> None:
        super().__init__(instance)
        self.error = error


class MultiAlert(BaseAlert):
    occurrences_limit = 100

    def __init__(self, instance, occurrences) -> None:
        super().__init__(instance)
        self.occurrences = self.process_occurrences(
            occurrences[: self.occurrences_limit]
        )
        self.total_occurrences = len(occurrences)
        self.missed_occurrences = self.total_occurrences > self.occurrences_limit

    def get_context(self, user: User):
        result = super().get_context(user)
        result["occurrences"] = self.occurrences
        result["total_occurrences"] = self.total_occurrences
        result["missed_occurrences"] = self.missed_occurrences
        return result

    def process_occurrences(self, occurrences):
        from weblate.lang.models import Language
        from weblate.trans.models import Unit

        processors = (
            ("language_code", "language", Language.objects.all(), "code"),
            ("unit_pk", "unit", Unit.objects.prefetch().prefetch_full(), "pk"),
        )
        for key, target, base, lookup in processors:
            # Extract list to fetch
            updates = defaultdict(list)
            for occurrence in occurrences:
                if key not in occurrence:
                    continue

                updates[occurrence[key]].append(occurrence)

            if not updates:
                continue

            result = base.filter(**{f"{lookup}__in": updates.keys()})
            for match in result:
                for occurrence in updates[getattr(match, lookup)]:
                    occurrence[target] = match

        return occurrences


@register
class DuplicateString(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Duplicated string found in the file.")
    on_import = True

    # Note: The removal of this alert can be also done in Translation.delete_unit


@register
class DuplicateLanguage(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Duplicated translation.")
    on_import = True

    def get_analysis(self):
        component = self.instance.component
        result = {"monolingual": bool(component.template)}
        source = component.source_language.code
        for occurrence in self.occurrences:
            if occurrence["language_code"] == source:
                result["source_language"] = True
            codes = {
                code.strip().replace("-", "_").lower()
                for code in occurrence["codes"].split(",")
            }
            if codes.intersection(DEFAULT_LANGS):
                result["default_country"] = True
        return result


@register
class DuplicateFilemask(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Duplicated file mask.")
    link_wide = True
    doc_page = "admin/projects"
    doc_anchor = "component-filemask"

    def __init__(self, instance, duplicates) -> None:
        super().__init__(instance)
        self.duplicates = duplicates

    @staticmethod
    def get_translations(component: Component) -> TranslationQuerySet:
        from weblate.trans.models import Translation

        return Translation.objects.filter(
            Q(component=component) | Q(component__linked_component=component)
        )

    @classmethod
    def check_component(cls, component: Component) -> bool | dict | None:
        if component.is_repo_link:
            return False

        translations = set(
            cls.get_translations(component)
            .values_list("filename")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .values_list("filename", flat=True)
        )
        translations.discard("")
        if translations:
            return {"duplicates": sorted(translations)}
        return False

    def resolve_filename(
        self, filename: str
    ) -> ComponentQuerySet | TranslationQuerySet:
        if "*" in filename:
            # Legacy path for old alerts
            # TODO: Remove in Weblate 6.0
            return self.instance.component.component_set.filter(filemask=filename)
        return self.get_translations(self.instance.component).filter(filename=filename)

    def get_analysis(self):
        return {
            "duplicates_resolved": [
                (filename, self.resolve_filename(filename))
                for filename in self.duplicates
            ]
        }


@register
class MergeFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not merge the repository.")
    link_wide = True
    doc_page = "faq"
    doc_anchor = "merge"


@register
class PushFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not push the repository.")
    link_wide = True
    behind_messages = (
        "The tip of your current branch is behind its remote counterpart",
        "fetch first",
    )
    terminal_message = "terminal prompts disabled"
    not_found_messages = (
        "Repository not found.",
        "HTTP Error 404: Not Found",
        "Repository was archived so is read-only",
        "does not appear to be a git repository",
    )
    temporary_messages = (
        "Empty reply from server",
        "no suitable response from remote hg",
        "cannot lock ref",
        "Too many retries",
        "Connection timed out",
    )
    permission_messages = (
        "denied to",
        "The repository exists, but forking is disabled.",
        "protected branch hook declined",
        "GH006:",
    )
    gerrit_messages = (
        "is not registered in your account, and you lack 'forge",
        "prohibited by Gerrit",
    )
    doc_page = "admin/continuous"
    doc_anchor = "push-changes"

    def get_analysis(self):
        terminal_disabled = self.terminal_message in self.error
        repo_suggestion = None
        force_push_suggestion = False
        component = self.instance.component

        # Missing credentials
        if terminal_disabled:
            if component.push:
                if component.push.startswith("https://github.com/"):
                    repo_suggestion = f"git@github.com:{component.push[19:]}"
            elif component.repo.startswith("https://github.com/"):
                repo_suggestion = f"git@github.com:{component.repo[19:]}"

        # Missing commits
        behind = any(message in self.error for message in self.behind_messages)
        if behind:
            force_push_suggestion = (
                component.vcs == "git"
                and component.merge_style == "rebase"
                and bool(component.push_branch)
            )

        return {
            "terminal": terminal_disabled,
            "behind": behind,
            "repo_suggestion": repo_suggestion,
            "force_push_suggestion": force_push_suggestion,
            "not_found": any(
                message in self.error for message in self.not_found_messages
            ),
            "permission": any(
                message in self.error for message in self.permission_messages
            ),
            "gerrit": any(message in self.error for message in self.gerrit_messages),
            "temporary": any(
                message in self.error for message in self.temporary_messages
            ),
        }

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        if not component.can_push():
            return False
        # We do not trigger it here, just remove stale alert
        return None


@register
class UpdateFailure(PushFailure):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not update the repository.")
    link_wide = True
    doc_page = "admin/projects"
    doc_anchor = "component-repo"


@register
class ParseError(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not parse translation files.")
    on_import = True


@register
class BillingLimit(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Your billing plan has exceeded its limits.")


@register
class RepositoryOutdated(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Repository outdated.")
    link_wide = True


@register
class RepositoryChanges(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Repository has changes.")
    link_wide = True
    dismissable = True


@register
class MissingLicense(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("License info missing.")
    doc_page = "admin/projects"
    doc_anchor = "component-license"

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return (
            component.project.access_control == component.project.ACCESS_PUBLIC
            and settings.LICENSE_REQUIRED
            and not component.license
            and not settings.LOGIN_REQUIRED_URLS
            and (settings.LICENSE_FILTER is None or settings.LICENSE_FILTER)
        )


@register
class AddonScriptError(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not run add-on.")
    doc_page = "adons"


@register
class CDNAddonError(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not run add-on.")
    doc_page = "adons"
    doc_anchor = "addon-weblate-cdn-cdnjs"


@register
class MsgmergeAddonError(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not run add-on.")
    doc_page = "adons"
    doc_anchor = "addon-weblate-gettext-msgmerge"


@register
class MonolingualTranslation(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Misconfigured monolingual translation.")
    doc_page = "formats"
    doc_anchor = "bimono"

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        if (
            component.is_glossary
            or component.template
            or not component.source_language.uses_whitespace()
        ):
            return False

        # Pick translation with translated strings except source one
        translation: Translation | None = None
        for current in component.translation_set.filter(
            unit__state__gte=STATE_TRANSLATED
        ).exclude(language_id=component.source_language_id):
            if not current.language.uses_whitespace():
                continue
            translation = current

        # Bail out if there is no suitable translation
        if translation is None:
            return False

        allunits = translation.unit_set

        source_space = allunits.filter(source__contains=" ")
        target_space = allunits.filter(
            state__gte=STATE_TRANSLATED, target__contains=" "
        )
        return (
            allunits.count() > 3 and not source_space.exists() and target_space.exists()
        )


@register
class UnsupportedConfiguration(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Unsupported component configuration")
    doc_page = "admin/projects"
    doc_anchor = "component"

    def __init__(self, instance, vcs, file_format) -> None:
        super().__init__(instance)
        self.vcs = vcs
        self.file_format = file_format

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        vcs = component.vcs not in VCS_REGISTRY
        file_format = component.file_format not in FILE_FORMATS
        if vcs or file_format:
            return {"file_format": file_format, "vcs": vcs}
        return False


@register
class BrokenBrowserURL(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Broken repository browser URL")
    dismissable = True
    doc_page = "admin/projects"
    doc_anchor = "component-repoweb"

    def __init__(self, instance, link, error) -> None:
        super().__init__(instance)
        self.link = link
        self.error = error

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        location_error = None
        location_link = None
        if component.repoweb:
            # Pick random translation with translated strings except source one
            translation = (
                component.translation_set.filter(unit__state__gte=STATE_TRANSLATED)
                .exclude(language_id=component.source_language_id)
                .first()
            )

            if translation:
                allunits = translation.unit_set
            else:
                allunits = component.source_translation.unit_set

            unit = allunits.exclude(location="").first()
            if unit:
                for _location, filename, line in unit.get_locations():
                    location_link = component.get_repoweb_link(filename, line)
                    if location_link is None:
                        continue
                    # We only test first link
                    location_error = get_uri_error(location_link)
                    break
        if location_error:
            return {"link": location_link, "error": location_error}
        return False


@register
class BrokenProjectURL(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Broken project website URL")
    dismissable = True
    doc_page = "admin/projects"
    doc_anchor = "project-web"
    project_wide = True

    def __init__(self, instance, error=None) -> None:
        super().__init__(instance)
        self.error = error

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        if component.project.web:
            location_error = get_uri_error(component.project.web)
            if location_error is not None:
                return {"error": location_error}
        return False


@register
class UnusedScreenshot(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Unused screenshot")
    doc_page = "admin/translating"
    doc_anchor = "screenshots"

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        from weblate.screenshots.models import Screenshot

        return (
            Screenshot.objects.filter(translation__component=component)
            .annotate(Count("units"))
            .filter(units__count=0)
            .exists()
        )


@register
class AmbiguousLanguage(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Ambiguous language code.")
    dismissable = True
    doc_page = "admin/languages"
    doc_anchor = "ambiguous-languages"

    def get_context(self, user: User):
        result = super().get_context(user)
        ambgiuous = self.instance.component.get_ambiguous_translations().values_list(
            "language__code", flat=True
        )
        result["ambiguous"] = {code: AMBIGUOUS[code] for code in ambgiuous}
        return result

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return component.get_ambiguous_translations().exists()


@register
class NoLibreConditions(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Does not meet Libre hosting conditions.")

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return (
            settings.OFFER_HOSTING
            and component.project.billings
            and component.project.billing.plan.price == 0
            and not component.project.billing.valid_libre
        )


@register
class UnusedEnforcedCheck(BaseAlert):
    verbose = gettext_lazy("Unused enforced checks.")
    doc_page = "admin/checks"
    doc_anchor = "enforcing-checks"

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return any(component.get_unused_enforcements())


@register
class NoMaskMatches(BaseAlert):
    verbose = gettext_lazy("No file mask matches.")
    doc_page = "admin/projects"
    doc_anchor = "component-filemask"

    def get_analysis(self):
        return {
            "can_add": self.instance.component.can_add_new_language(None, fast=True),
        }

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return (
            not component.is_glossary
            and component.translation_set.count() <= 1
            and not component.intermediate
        )


@register
class InexistantFiles(BaseAlert):
    verbose = gettext_lazy("Inexistent files.")
    doc_page = "admin/projects"
    doc_anchor = "component-template"

    def __init__(self, instance, files) -> None:
        super().__init__(instance)
        self.files = files

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        missing_files = [
            name
            for name in (component.template, component.intermediate, component.new_base)
            if name and not os.path.exists(os.path.join(component.full_path, name))
        ]
        if missing_files:
            return {"files": missing_files}
        return False


@register
class UnusedComponent(BaseAlert):
    verbose = gettext_lazy("Component seems unused.")
    doc_page = "devel/community"

    def get_analysis(self):
        return {"days": settings.UNUSED_ALERT_DAYS}

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        if settings.UNUSED_ALERT_DAYS == 0:
            return False
        if component.is_glossary:
            # Auto created glossaries can live without being used
            return False
        if component.stats.all == component.stats.translated:
            # Allow fully translated ones
            return False
        last_changed = component.stats.last_changed
        cutoff = timezone.now() - timedelta(days=settings.UNUSED_ALERT_DAYS)
        if last_changed is not None:
            # If last content change is present, use it to decide
            return last_changed < cutoff
        oldest_change = component.change_set.order_by("timestamp").first()
        # Weird, each component should have change
        return oldest_change is None or oldest_change.timestamp < cutoff


@register
class MonolingualGlossary(BaseAlert):
    verbose = gettext_lazy("Glossary using monolingual files.")
    doc_page = "user/glossary"
    dismissable = True

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return component.is_glossary and bool(component.template)
