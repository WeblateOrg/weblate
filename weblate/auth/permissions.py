# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.translation import gettext

from weblate.lang.models import Language
from weblate.trans.models import (
    Category,
    Component,
    ComponentList,
    ContributorAgreement,
    Project,
    Translation,
    Unit,
)
from weblate.utils.stats import CategoryLanguage, ProjectLanguage

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Model

    from weblate.auth.models import User

SPECIALS: dict[str, Callable[[User, str, Model], bool | PermissionResult]] = {}


class PermissionResult:
    def __init__(self, reason: str = "") -> None:
        self.reason = reason

    def __bool__(self) -> bool:
        raise NotImplementedError


class Allowed(PermissionResult):
    def __bool__(self) -> bool:
        return True


class Denied(PermissionResult):
    def __bool__(self) -> bool:
        return False


def register_perm(*perms):
    def wrap_perm(function):
        for perm in perms:
            SPECIALS[perm] = function
        return function

    return wrap_perm


def check_global_permission(user: User, permission: str) -> bool:
    """Check whether the user has a global permission."""
    if user.is_superuser:
        return True
    return permission in user.global_permissions


def check_enforced_2fa(user: User, project: Project) -> bool:
    """Check whether the user has 2FA configured, in case it is enforced by the project."""
    return user.is_bot or not project.enforced_2fa or user.profile.has_2fa


def check_permission(user: User, permission: str, obj: Model):
    """Check whether user has a object-specific permission."""
    if user.is_superuser:
        return True
    if isinstance(obj, ProjectLanguage):
        obj = obj.project
    if isinstance(obj, CategoryLanguage):
        obj = obj.category.project
    if isinstance(obj, Category):
        obj = obj.project
    if isinstance(obj, Project):
        return any(
            permission in permissions
            for permissions, _langs in user.get_project_permissions(obj)
        ) and check_enforced_2fa(user, obj)
    if isinstance(obj, ComponentList):
        return all(
            check_permission(user, permission, component)
            and check_enforced_2fa(user, component.project)
            for component in obj.components.iterator()
        )
    if isinstance(obj, Component):
        return (
            (
                not obj.restricted
                and any(
                    permission in permissions
                    for permissions, _langs in user.get_project_permissions(obj.project)
                )
            )
            or any(
                permission in permissions
                for permissions, _langs in user.component_permissions[obj.pk]
            )
        ) and check_enforced_2fa(user, obj.project)
    if isinstance(obj, Unit):
        obj = obj.translation
    if isinstance(obj, Translation):
        lang = obj.language_id
        return (
            (
                not obj.component.restricted
                and any(
                    permission in permissions and (langs is None or lang in langs)
                    for permissions, langs in user.get_project_permissions(
                        obj.component.project
                    )
                )
            )
            or any(
                permission in permissions and (langs is None or lang in langs)
                for permissions, langs in user.component_permissions[obj.component_id]
            )
        ) and check_enforced_2fa(user, obj.component.project)
    msg = f"Permission {permission} does not support: {obj.__class__}: {obj!r}"
    raise TypeError(msg)


@register_perm("comment.resolve", "comment.delete", "suggestion.delete")
def check_delete_own(user: User, permission: str, obj: Model):
    if user.is_authenticated and obj.user == user:
        return True
    return check_permission(user, permission, obj.unit.translation)


@register_perm("unit.check")
def check_ignore_check(user: User, permission, check):
    if check.is_enforced():
        return False
    return check_permission(user, permission, check.unit.translation)


def check_can_edit(user: User, permission: str, obj: Model, is_vote=False):  # noqa: C901
    translation = component = None

    if isinstance(obj, Translation):
        translation = obj
        component = obj.component
        project = component.project
    elif isinstance(obj, Component):
        component = obj
        project = component.project
    elif isinstance(obj, Category):
        project = obj.project
    elif isinstance(obj, Project):
        project = obj
    elif isinstance(obj, ProjectLanguage):
        project = obj.project
    elif isinstance(obj, CategoryLanguage):
        project = obj.category.project
    else:
        msg = f"Unknown object for permission check: {obj.__class__}"
        raise TypeError(msg)

    # Email is needed for user to be able to edit
    if user.is_authenticated and not user.email:
        return Denied(
            gettext("Can not perform this operation without an e-mail address.")
        )

    if project and not check_enforced_2fa(user, project):
        # This would later fail in check_permission, but we can give a nicer error
        # message here when checking this specifically.
        return Denied(
            gettext(
                "This project requires two-factor authentication; configure it in your profile."
            )
        )

    if component:
        # Check component lock
        if component.locked:
            return Denied(gettext("This translation is currently locked."))

        # Check contributor license agreement
        if (
            not user.is_bot
            and component.agreement
            and not ContributorAgreement.objects.has_agreed(user, component)
        ):
            return Denied(
                gettext(
                    "Contributing to this translation requires accepting its contributor license agreement."
                )
            )

    # Perform usual permission check
    if not check_permission(user, permission, obj):
        if not user.is_authenticated:
            # Signing in might help, but user still might need additional privileges
            return Denied(gettext("Sign in to save translations."))
        if permission == "unit.review":
            return Denied(
                gettext("Insufficient privileges for approving translations.")
            )
        return Denied(gettext("Insufficient privileges for saving translations."))

    # Special check for source strings (templates)
    if (
        translation
        and translation.is_template
        and not check_permission(user, "unit.template", obj)
    ):
        return Denied(gettext("Insufficient privileges for editing source strings."))

    # Special checks for voting
    if is_vote and translation and not translation.suggestion_voting:
        return Denied(gettext("Suggestion voting is disabled."))
    if (
        not is_vote
        and translation
        and translation.suggestion_voting
        and translation.suggestion_autoaccept > 0
        and not check_permission(user, "unit.override", obj)
    ):
        return Denied(
            gettext(
                "This translation only accepts suggestions, in turn approved by voting."
            )
        )

    # Billing limits
    if not project.paid:
        return Denied(gettext("Pay the bills to unlock this project."))

    return Allowed()


@register_perm("unit.review")
def check_unit_review(user: User, permission: str, obj: Model, skip_enabled=False):
    if not skip_enabled:
        if isinstance(obj, Unit):
            obj = obj.translation
        if isinstance(obj, Translation):
            if not obj.enable_review:
                if obj.is_source:
                    return Denied(gettext("Source-string reviews are turned off."))
                return Denied(gettext("Translation reviews are turned off."))
        else:
            if isinstance(obj, CategoryLanguage):
                project = obj.category.project
            elif isinstance(
                obj,
                Component | ProjectLanguage | Category,
            ):
                project = obj.project
            else:
                project = obj
            if not project.source_review and not project.translation_review:
                return Denied(gettext("Reviewing is turned off."))
    return check_can_edit(user, permission, obj)


@register_perm("unit.edit", "suggestion.accept")
def check_edit_approved(user: User, permission: str, obj: Model):
    component = None
    if isinstance(obj, Unit):
        unit = obj
        obj = unit.translation
        # Read-only check is unconditional as there is another one
        # in PluralTextarea.render
        if unit.readonly:
            if not unit.source_unit.translated:
                return Denied(gettext("The source string needs review."))
            return Denied(gettext("The string is read-only."))
        # Ignore approved state if review is not disabled. This might
        # happen after disabling them.
        if (
            unit.approved
            and obj.enable_review
            and not check_unit_review(user, "unit.review", obj, skip_enabled=True)
        ):
            return Denied(
                gettext(
                    "Only reviewers can change approved strings. Please add a suggestion if you think the string should be changed."
                )
            )
    if isinstance(obj, Translation):
        component = obj.component
        if obj.is_readonly:
            return Denied(gettext("The translation is read-only."))
    elif isinstance(obj, Component):
        component = obj
    if component is not None and component.is_glossary:
        permission = "glossary.edit"
    return check_can_edit(user, permission, obj)


def check_manage_units(
    translation: Translation, component: Component
) -> PermissionResult:
    if not isinstance(component, Component):
        return Denied("Invalid scope")
    source = translation.is_source
    template = component.has_template()
    # Add only to source in monolingual
    if not source and template:
        return Denied(gettext("Add the string to the source language instead."))
    # Check if adding is generally allowed
    if not component.manage_units or (template and not component.edit_template):
        return Denied(
            gettext("Adding strings is disabled in the component configuration.")
        )
    return Allowed()


@register_perm("unit.delete")
def check_unit_delete(user: User, permission: str, obj: Model):
    if isinstance(obj, Unit):
        if (
            obj.translation.component.is_glossary
            and not obj.translation.is_source
            and "terminology" in obj.all_flags
        ):
            return Denied(
                gettext(
                    "Cannot remove terminology translation. Remove the source string instead."
                )
            )
        obj = obj.translation
    component = obj.component
    # Check if removing is generally allowed
    can_manage = check_manage_units(obj, component)
    if not can_manage:
        return can_manage

    # Does file format support removing?
    if not component.file_format_cls.can_delete_unit:
        return Denied(gettext("The file format does not support this."))

    if component.is_glossary:
        permission = "glossary.delete"
    return check_can_edit(user, permission, obj)


@register_perm("unit.add")
def check_unit_add(user: User, permission, translation):
    component = translation.component
    # Check if adding is generally allowed
    can_manage = check_manage_units(translation, component)
    if not can_manage:
        return can_manage

    # Does file format support adding?
    if not component.file_format_cls.can_add_unit:
        return Denied(gettext("The file format does not support this."))

    if component.is_glossary:
        permission = "glossary.add"

    return check_can_edit(user, permission, translation)


@register_perm("translation.add")
def check_translation_add(user: User, permission, component):
    if component.new_lang == "none" and not component.can_add_new_language(
        user, fast=True
    ):
        return Denied(
            gettext(
                "Adding new translations is turned off in the component configuration."
            )
        )
    if component.locked:
        return Denied(gettext("This component is currently locked."))
    return check_permission(user, permission, component)


@register_perm("translation.auto")
def check_autotranslate(user: User, permission, translation):
    if isinstance(translation, Translation) and (
        (translation.is_source and not translation.component.intermediate)
        or translation.is_readonly
    ):
        return False
    return check_can_edit(user, permission, translation)


@register_perm("suggestion.vote")
def check_suggestion_vote(user: User, permission: str, obj: Model):
    if isinstance(obj, Unit):
        obj = obj.translation
    return check_can_edit(user, permission, obj, is_vote=True)


@register_perm("suggestion.add")
def check_suggestion_add(user: User, permission: str, obj: Model):
    if isinstance(obj, Unit):
        obj = obj.translation
    if not obj.enable_suggestions or obj.is_readonly:
        return False
    # Check contributor license agreement
    if (
        not user.is_bot
        and obj.component.agreement
        and not ContributorAgreement.objects.has_agreed(user, obj.component)
    ):
        return False
    return check_permission(user, permission, obj)


@register_perm("upload.perform")
def check_contribute(user: User, permission, translation):
    # Bilingual source translations
    if translation.is_source and not translation.is_template:
        return hasattr(
            translation.component.file_format_cls, "update_bilingual"
        ) and user.has_perm("source.edit", translation)
    if translation.component.is_glossary:
        permission = "glossary.upload"
    return check_can_edit(user, permission, translation) and (
        # Normal upload
        check_edit_approved(user, "unit.edit", translation)
        # Suggestion upload
        or check_suggestion_add(user, "suggestion.add", translation)
        # Add upload
        or check_suggestion_add(user, "unit.add", translation)
        # Source upload
        or (translation.is_source and user.has_perm("source.edit", translation))
    )


@register_perm("machinery.view")
def check_machinery(user: User, permission: str, obj: Model):
    # No machinery for source without intermediate language
    if (
        isinstance(obj, Translation)
        and obj.is_source
        and not obj.component.intermediate
    ):
        return False

    # Check the actual machinery.view permission
    if not check_permission(user, permission, obj):
        return False

    # Only show machinery to users allowed to translate or suggest
    return check_edit_approved(user, "unit.edit", obj) or check_suggestion_add(
        user, "suggestion.add", obj
    )


@register_perm("translation.delete")
def check_translation_delete(user: User, permission: str, obj: Model):
    if obj.is_source:
        return False
    return check_permission(user, permission, obj)


@register_perm("reports.view", "change.download")
def check_possibly_global(user: User, permission: str, obj: Model):
    if obj is None or isinstance(obj, Language):
        return user.is_superuser
    return check_permission(user, permission, obj)


@register_perm("meta:vcs.status")
def check_repository_status(user: User, permission: str, obj: Model):
    return (
        check_permission(user, "vcs.push", obj)
        or check_permission(user, "vcs.commit", obj)
        or check_permission(user, "vcs.reset", obj)
        or check_permission(user, "vcs.update", obj)
    )


@register_perm("meta:team.edit")
def check_team_edit(user: User, permission: str, obj: Model):
    return (
        check_global_permission(user, "group.edit")
        or (
            obj.defining_project
            and check_permission(user, "project.permissions", obj.defining_project)
        )
        or obj.admins.filter(pk=user.pk).exists()
    )


@register_perm("meta:team.users")
def check_team_edit_users(user: User, permission: str, obj: Model):
    return (
        check_team_edit(user, permission, obj) or obj.pk in user.administered_group_ids
    )


@register_perm("billing.view")
def check_billing_view(user: User, permission: str, obj: Model):
    if hasattr(obj, "all_projects"):
        if user.has_perm("billing.manage") or obj.owners.filter(pk=user.pk).exists():
            return True
        # This is a billing object
        return any(check_permission(user, permission, prj) for prj in obj.all_projects)
    return check_permission(user, permission, obj)


@register_perm("billing:project.permissions")
def check_billing(user: User, permission: str, obj: Model):
    if user.is_superuser:
        return True

    if (
        "weblate.billing" in settings.INSTALLED_APPS
        and not any(billing.plan.change_access_control for billing in obj.billings)
        and not obj.access_control
    ):
        return False

    return check_permission(user, "project.permissions", obj)


# This does not exist for real
@register_perm("announcement.delete")
def check_announcement_delete(user: User, permission: str, obj: Model):
    return (
        user.is_superuser
        or (obj.component and check_permission(user, "component.edit", obj.component))
        or (obj.project and check_permission(user, "project.edit", obj.project))
    )


# This does not exist for real
@register_perm("unit.flag")
def check_unit_flag(user: User, permission: str, obj: Model):
    if isinstance(obj, Unit):
        obj = obj.translation
    if not obj.component.is_glossary:
        return user.has_perm("source.edit", obj)

    return check_can_edit(user, "glossary.edit", obj)


@register_perm("memory.edit", "memory.delete")
def check_memory_perms(user: User, permission, memory):
    from weblate.memory.models import Memory

    if isinstance(memory, Memory):
        if memory.user_id == user.id:
            return True
        project = memory.project
    else:
        project = memory
    if project is None:
        return check_global_permission(user, "memory.manage")
    return check_permission(user, permission, project)
