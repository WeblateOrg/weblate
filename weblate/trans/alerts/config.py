# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Value
from django.db.models.functions import MD5
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy
from weblate_language_data.ambiguous import AMBIGUOUS

from weblate.formats.models import FILE_FORMATS
from weblate.trans.alerts.base import AlertSeverity, BaseAlert, MultiAlert
from weblate.trans.alerts.registry import register
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.requests import (
    format_validation_error,
    get_uri_error,
    validate_request_url,
)
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.validators import (
    WeblateURLValidator,
    is_project_web_allowlisted,
    validate_project_web,
)
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from collections.abc import Callable

    from weblate.auth.models import User
    from weblate.trans.models.component import Component
    from weblate.trans.models.translation import Translation


LIKELY_BILINGUAL_PO_SAMPLE_SIZE = 20
MIN_LIKELY_BILINGUAL_PO_UNITS = 4
EMPTY_SOURCE_VALUES = ("", *(PLURAL_SEPARATOR * count for count in range(1, 10)))


def _looks_like_source_text(value: str) -> bool:
    text = value.strip()
    if not text or not any(char.isalpha() for char in text):
        return False
    if any(char.isspace() for char in text):
        return True
    return text.endswith((".", "?", "!")) or any(char in text for char in ",;:")


def _get_validated_uri_error(
    uri: str,
    validators: tuple[Callable[[str], None], ...],
    *,
    allow_private_targets: bool | None = None,
) -> str | None:
    for validator in validators:
        try:
            validator(uri)
        except ValidationError as error:
            return format_validation_error(error)
    if allow_private_targets is None:
        allow_private_targets = not settings.PROJECT_WEB_RESTRICT_PRIVATE
    try:
        validate_request_url(uri, allow_private_targets=allow_private_targets)
    except ValidationError as error:
        return format_validation_error(error)
    return get_uri_error(uri, allow_private_targets=allow_private_targets)


@register
class BillingLimit(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Your billing plan has exceeded its limits.")

    @classmethod
    def can_user_act_for(
        cls, user: User, component: Component, _details: dict[str, Any]
    ) -> bool:
        workspace = component.project.workspace
        return workspace is not None and bool(
            user.has_perm("workspace.edit", workspace)
        )


@register
class MissingLicense(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("License info missing.")
    doc_page = "admin/projects"
    doc_anchor = "component-license"

    @classmethod
    def is_relevant(cls, _component: Component) -> bool:
        return settings.LICENSE_REQUIRED

    @classmethod
    def is_passing(cls, component: Component) -> bool:
        return component.libre_license

    @classmethod
    def get_url(cls, component: Component) -> str:
        return reverse("settings", kwargs={"path": component.get_url_path()}) + "#basic"

    @classmethod
    def get_doc_url(cls, _component: Component, _user: User | None = None) -> str:
        return "https://choosealicense.com/"

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return component.project.needs_license() and not component.effective_license


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
        if component.source_language_id is None:
            return False

        translation: Translation | None = None
        for current in (
            component.translation_set.filter(unit__state__gte=STATE_TRANSLATED)
            .exclude(language_id=component.source_language_id)
            .select_related("language")
        ):
            if not current.language.uses_whitespace():
                continue
            translation = current

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
class BilingualPOConfiguredAsMonolingual(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Bilingual gettext PO file configured as monolingual.")
    doc_page = "formats"
    doc_anchor = "bimono"

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        if (
            component.is_glossary
            or component.file_format != "po-mono"
            or not component.template
            or component.source_language_id is None
            or not component.source_language.uses_whitespace()
        ):
            return False

        units = list(
            component.source_translation.unit_set.filter(
                source__lower__md5__in=[
                    MD5(Value(source)) for source in EMPTY_SOURCE_VALUES
                ]
            )
            .exclude(context__lower__md5=MD5(Value("")))
            .values_list("source", "context")[:LIKELY_BILINGUAL_PO_SAMPLE_SIZE]
        )
        contexts = [
            context
            for source, context in units
            if not source.replace(PLURAL_SEPARATOR, "")
        ]
        if len(contexts) < MIN_LIKELY_BILINGUAL_PO_UNITS:
            return False

        return (
            sum(1 for context in contexts if _looks_like_source_text(context))
            >= MIN_LIKELY_BILINGUAL_PO_UNITS
        )


@register
class UnsupportedConfiguration(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Unsupported component configuration")
    doc_page = "admin/projects"
    doc_anchor = "component"

    def __init__(self, instance, vcs: str, file_format: str) -> None:
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
    dismissible = True
    doc_page = "admin/projects"
    doc_anchor = "component-repoweb"

    def __init__(self, instance, link: str, error: str) -> None:
        super().__init__(instance)
        self.link = link
        self.error = error

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        location_error = None
        location_link = None
        if component.repoweb:
            if component.source_language_id is None:
                return False
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
                    location_error = _get_validated_uri_error(
                        location_link,
                        validators=(WeblateURLValidator(),),
                    )
                    break
        if location_error:
            return {"link": location_link, "error": location_error}
        return False


@register
class BrokenProjectURL(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Broken project website URL")
    dismissible = True
    doc_page = "admin/projects"
    doc_anchor = "project-web"
    project_wide = True

    @classmethod
    def get_dismissal_context(cls, component: Component, details: dict) -> dict:
        return {"details": details, "web": component.project.web}

    def __init__(self, instance, error: str | None = None) -> None:
        super().__init__(instance)
        self.error = error

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        if not settings.WEBSITE_ALERTS_ENABLED:
            return False

        if component.project.web:
            project_slug = component.project.slug or None
            allow_private_targets = (
                not settings.PROJECT_WEB_RESTRICT_PRIVATE
                or is_project_web_allowlisted(project_slug)
            )
            location_error = _get_validated_uri_error(
                component.project.web,
                validators=(
                    WeblateURLValidator(),
                    partial(validate_project_web, project_slug=project_slug),
                ),
                allow_private_targets=allow_private_targets,
            )
            if location_error is not None:
                return {"error": location_error}
        return False


@register
class UnusedScreenshot(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Unused screenshot")
    severity = AlertSeverity.WARNING
    dismissible = True
    doc_page = "admin/translating"
    doc_anchor = "screenshots"

    @classmethod
    def can_user_act_for(
        cls, user: User, component: Component, details: dict[str, Any]
    ) -> bool:
        return (
            super().can_user_act_for(user, component, details)
            or bool(user.has_perm("screenshot.edit", component))
            or bool(user.has_perm("screenshot.delete", component))
        )

    @classmethod
    def get_dismissal_context(cls, component: Component, details: dict) -> dict:
        # ruff: ignore[import-outside-top-level]
        from weblate.screenshots.models import Screenshot

        screenshots = list(
            Screenshot.objects.filter(
                translation__component=component, units__isnull=True
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        return {"details": details, "screenshots": screenshots}

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        # ruff: ignore[import-outside-top-level]
        from weblate.screenshots.models import Screenshot

        return (
            Screenshot.objects.filter(translation__component=component)
            .filter(units__isnull=True)
            .exists()
        )


@register
class AmbiguousLanguage(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Ambiguous language code.")
    dismissible = True
    doc_page = "admin/languages"
    doc_anchor = "ambiguous-languages"

    @classmethod
    def can_user_act_for(
        cls, user: User, component: Component, details: dict[str, Any]
    ) -> bool:
        return super().can_user_act_for(user, component, details) or bool(
            user.has_perm("language.edit")
        )

    @classmethod
    def get_dismissal_context(cls, component: Component, details: dict) -> dict:
        languages = list(
            component.get_ambiguous_translations()
            .order_by("language__code")
            .values_list("language__code", flat=True)
        )
        return {"details": details, "languages": languages}

    def get_context(self, user: User) -> dict[str, Any]:
        result = super().get_context(user)
        ambiguous = self.instance.component.get_ambiguous_translations().values_list(
            "language__code", flat=True
        )
        result["ambiguous"] = {code: AMBIGUOUS[code] for code in ambiguous}
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
            and bool(component.project.billings)
            and component.project.billing.plan.price == 0
            and not component.project.billing.valid_libre_without_alerts
        )


@register
class UnusedEnforcedCheck(BaseAlert):
    verbose = gettext_lazy("Unused enforced checks.")
    doc_page = "admin/checks"
    doc_anchor = "enforcing-checks"

    @classmethod
    def can_user_act_for(
        cls, user: User, component: Component, details: dict[str, Any]
    ) -> bool:
        return super().can_user_act_for(user, component, details) or bool(
            user.has_perm("source.edit", component)
        )

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return any(component.get_unused_enforcements())


@register
class UnusedComponent(BaseAlert):
    verbose = gettext_lazy("Component seems unused.")
    doc_page = "devel/community"

    def get_analysis(self) -> dict[str, Any]:
        return {"days": settings.UNUSED_ALERT_DAYS}

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        if settings.UNUSED_ALERT_DAYS == 0:
            return False
        if component.is_glossary:
            return False
        if component.stats.all == component.stats.translated:
            return False
        last_changed = component.stats.last_changed
        cutoff = timezone.now() - timedelta(days=settings.UNUSED_ALERT_DAYS)
        if last_changed is not None:
            return last_changed < cutoff
        oldest_change = component.change_set.order_by("timestamp").first()
        return oldest_change is None or oldest_change.timestamp < cutoff


@register
class MonolingualGlossary(BaseAlert):
    verbose = gettext_lazy("Glossary using monolingual files.")
    doc_page = "user/glossary"
    dismissible = True

    @classmethod
    def get_dismissal_context(cls, component: Component, details: dict) -> dict:
        return {"details": details, "template": component.template}

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return component.is_glossary and bool(component.template)


@register
class UnusedGlossaryLanguage(MultiAlert):
    verbose = gettext_lazy("Unused glossary language.")
    doc_page = "user/glossary"

    @classmethod
    def can_user_act_for(
        cls, user: User, component: Component, details: dict[str, Any]
    ) -> bool:
        return super().can_user_act_for(user, component, details) or bool(
            user.has_perm("translation.delete", component)
        )

    def process_occurrences(
        self, occurrences: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        result = super().process_occurrences(occurrences)
        updates: dict[int, list[dict[str, Any]]] = {}
        for occurrence in result:
            if "translation_pk" not in occurrence:
                continue
            updates.setdefault(occurrence["translation_pk"], []).append(occurrence)
        if not updates:
            return result

        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Translation

        for translation in Translation.objects.filter(pk__in=updates).select_related(
            "component", "language"
        ):
            for occurrence in updates[translation.pk]:
                occurrence["translation"] = translation
        return result

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        if not component.is_glossary:
            return False

        # ruff: ignore[import-outside-top-level]
        from weblate.glossary.tasks import get_stale_glossary_translations

        # ruff: ignore[import-outside-top-level]
        from weblate.utils.stats import prefetch_stats

        occurrences = [
            {
                "language_code": translation.language_code,
                "translation_pk": translation.pk,
            }
            for translation in prefetch_stats(
                get_stale_glossary_translations(component.project, component)
            )
            if not translation.can_be_deleted()
        ]
        if occurrences:
            return {"occurrences": occurrences}
        return False
