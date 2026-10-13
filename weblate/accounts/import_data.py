# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.translation import gettext

from weblate.accounts.data import NotificationScope
from weblate.accounts.forms import (
    FullNameField,
    LanguagesForm,
    ProfileForm,
    UserSettingsForm,
)
from weblate.accounts.models import AuditLog, Profile, Subscription
from weblate.accounts.notifications import NOTIFICATIONS
from weblate.lang.models import Language

if TYPE_CHECKING:
    from django.db.models import Field

    from weblate.auth.models import AuthenticatedHttpRequest, User


PROFILE_FIELDS = (
    frozenset(UserSettingsForm.Meta.fields)
    | frozenset(ProfileForm.Meta.fields)
    | {"nearby_strings", "auto_watch", "contribute_personal_tm"}
)
PROFILE_FIELDS -= {"public_email"}
PUBLIC_FIELDS = frozenset(ProfileForm.Meta.fields)


def _valid_profile_value(profile: Profile, field: str, value: object) -> object:
    if field in PUBLIC_FIELDS:
        value = ProfileForm(instance=profile).fields[field].clean(value)
    elif field in UserSettingsForm.Meta.fields:
        value = UserSettingsForm(instance=profile).fields[field].clean(value)
    model_field = cast("Field", Profile._meta.get_field(field))  # ruff: ignore[private-member-access]
    return model_field.clean(value, profile)


def _skipped_setting(field: str, value: str = "") -> str:
    if field == "full_name":
        label = gettext("Full name")
    elif field == "notification":
        label = gettext("Notification setting")
    else:
        model_field = cast("Field", Profile._meta.get_field(field))  # ruff: ignore[private-member-access]
        label = force_str(model_field.verbose_name)
    return f"{label}: {value[:100]}" if value else label


def _import_notifications(user: User, rules: list[dict], skipped: list[str]) -> None:
    available = {
        notification.get_name(): notification for notification in NOTIFICATIONS
    }
    present: set[tuple[str, int]] = set()
    for rule in rules:
        name = rule["notification"]
        scope = rule["scope"]
        frequency = rule["frequency"]
        notification = available.get(name)
        if (
            notification is not None
            and scope in NotificationScope.configurable()
            and rule.get("project") is None
            and rule.get("component") is None
            and not rule.get("onetime", False)
        ):
            # Keep an existing subscription when its exported frequency is invalid.
            present.add((name, scope))
        if (
            notification is None
            or scope not in NotificationScope.configurable()
            or rule.get("project") is not None
            or rule.get("component") is not None
            or rule.get("onetime", False)
            or frequency
            not in {value for value, _label in notification.get_freq_choices()}
        ):
            skipped.append(_skipped_setting("notification", name))
            continue
        Subscription.objects.update_or_create(
            user=user,
            notification=name,
            scope=scope,
            project=None,
            component=None,
            defaults={"frequency": frequency, "onetime": False},
        )

    stale = [
        subscription.pk
        for subscription in Subscription.objects.filter(
            user=user,
            scope__in=NotificationScope.configurable(),
            project=None,
            component=None,
            onetime=False,
        )
        if (subscription.notification, subscription.scope) not in present
    ]
    if stale:
        Subscription.objects.filter(pk__in=stale).delete()


@transaction.atomic
# ruff: ignore[complex-structure]
def import_user_settings(
    user: User,
    data: dict,
    *,
    request: AuthenticatedHttpRequest,
    notifications: bool = False,
    commit_identity: bool = False,
) -> list[str]:
    """Apply compatible exported settings and return names of skipped values."""
    profile = user.profile
    source = data["profile"]
    skipped: list[str] = []
    updates: set[str] = set()

    for field in sorted(PROFILE_FIELDS | {"public_email"}):
        if field not in source:
            continue
        try:
            value = _valid_profile_value(profile, field, source[field])
        except (ValidationError, ValueError, TypeError):
            skipped.append(_skipped_setting(field))
            continue
        setattr(profile, field, value)
        updates.add(field)

    if "full_name" in data["basic"]:
        try:
            name = FullNameField().clean(data["basic"]["full_name"])
        except ValidationError:
            skipped.append(_skipped_setting("full_name"))
        else:
            if name != user.full_name:
                AuditLog.objects.create(
                    user, request, "full_name", old=user.full_name, new=name
                )
            user.full_name = name
            user.save(update_fields=["full_name"])

    if commit_identity:
        for field, choices in (
            ("commit_email", profile.get_commit_email_choices()),
            ("commit_name", profile.get_commit_name_choices()),
        ):
            if field not in source:
                continue
            allowed = {choice for choice, _label in choices}
            value = source[field]
            if value not in allowed:
                skipped.append(_skipped_setting(field))
                continue
            setattr(profile, field, value)
            updates.add(field)

    if "language" in source:
        try:
            value = (
                LanguagesForm(instance=profile)
                .fields["language"]
                .clean(source["language"])
            )
        except (ValidationError, ValueError, TypeError):
            skipped.append(_skipped_setting("language"))
        else:
            profile.language = value
            updates.add("language")

    for field in ("languages", "secondary_languages"):
        if field not in source:
            continue
        selected = []
        available = {
            language.code: language
            for language in Language.objects.have_translation().filter(
                code__in=[code for code in source[field] if "\x00" not in code]
            )
        }
        for code in source[field]:
            if "\x00" in code:
                skipped.append(_skipped_setting(field))
                continue
            language = available.get(code)
            if language is None:
                skipped.append(_skipped_setting(field, code))
            else:
                selected.append(language)
        if selected or not source[field]:
            getattr(profile, field).set(selected)

    if "watched" in source:
        selected = []
        available = {
            project.slug: project
            for project in user.allowed_projects.filter(
                slug__in=[slug for slug in source["watched"] if "\x00" not in slug]
            )
        }
        for slug in source["watched"]:
            if "\x00" in slug:
                skipped.append(_skipped_setting("watched"))
                continue
            project = available.get(slug)
            if project is None:
                skipped.append(_skipped_setting("watched", slug))
            else:
                selected.append(project)
        if selected or not source["watched"]:
            profile.watched.set(selected)

    if (
        "dashboard_component_list" in source
        and source["dashboard_component_list"] is not None
    ):
        skipped.append(_skipped_setting("dashboard_component_list"))
    if "dashboard_view" in source:
        try:
            view = Profile._meta.get_field("dashboard_view").clean(  # ruff: ignore[private-member-access]
                source["dashboard_view"], profile
            )
        except (ValidationError, ValueError, TypeError):
            skipped.append(_skipped_setting("dashboard_view"))
        else:
            if view == Profile.DASHBOARD_COMPONENT_LIST or (
                view == Profile.DASHBOARD_COMPONENT_LISTS
                and not profile.allowed_dashboard_component_lists.exists()
            ):
                skipped.append(_skipped_setting("dashboard_view"))
            else:
                profile.dashboard_view = view
                profile.dashboard_component_list = None
                updates.update(("dashboard_view", "dashboard_component_list"))

    if updates:
        profile.save(update_fields=updates)

    if notifications and "notifications" in data:
        _import_notifications(user, data["notifications"], skipped)

    return skipped
