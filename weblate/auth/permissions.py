# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import Q
from django.utils.translation import gettext

from weblate.formats.base import BilingualUpdateMixin
from weblate.lang.models import Language
from weblate.trans.models import (
    Announcement,
    Category,
    Component,
    ComponentLink,
    ComponentList,
    ContributorAgreement,
    Project,
    Translation,
    Unit,
)
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.workspaces.models import Workspace

from .results import Allowed, Denied

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from django.db.models import Model, QuerySet

    from weblate.auth.models import Group, User
    from weblate.billing.models import Billing
    from weblate.checks.models import Check
    from weblate.memory.models import Memory
    from weblate.trans.models import Comment, Suggestion

    from .results import PermissionResult

SPECIALS: dict[str, Callable[[User, str, Model], bool | PermissionResult]] = {}
UPLOAD_SCOPE_PERMISSIONS = frozenset({"glossary.upload", "upload.perform"})


@dataclass(frozen=True)
class PermissionLanguageScope:
    language_ids: set[int]
    membership_limited: bool


def _has_scoped_permission(
    permission: str,
    permissions: set[str],
    langs: PermissionLanguageScope | None,
    language_id: int | None = None,
    *,
    allow_limited_without_language: bool = False,
) -> bool:
    if permission not in permissions:
        return False
    if langs is None:
        return True
    if language_id is None:
        # Team language selections have historically limited translation
        # actions only. Per-membership limits also restrict project and
        # component checks unless the caller explicitly accepts them.
        return allow_limited_without_language or not langs.membership_limited
    return language_id in langs.language_ids


def _get_language_scope_components(
    obj: ProjectLanguage | CategoryLanguage,
) -> list[tuple[int, int, bool]]:
    return list(
        obj.action_translation_set.values_list(
            "component_id", "component__project_id", "component__restricted"
        ).distinct()
    )


def _needs_language_scope_component_permissions(
    user: User, obj: ProjectLanguage | CategoryLanguage
) -> bool:
    return user.needs_component_restrictions_filter and (
        obj.has_restricted_action_translations
    )


def _has_project_language_permission(
    user: User,
    permission: str,
    project: Project,
    language_id: int,
    *,
    allow_limited_without_language: bool = False,
) -> bool:
    return any(
        _has_scoped_permission(
            permission,
            permissions,
            langs,
            language_id,
            allow_limited_without_language=allow_limited_without_language,
        )
        for permissions, langs in user.get_project_permissions(project)
    )


def _check_language_scope_permission(
    user: User,
    permission: str,
    obj: ProjectLanguage | CategoryLanguage,
    *,
    allow_limited_without_language: bool = False,
) -> bool:
    language_id = obj.language.id
    project = obj.project
    if not check_enforced_2fa(user, project):
        return False

    project_allowed = _has_project_language_permission(
        user,
        permission,
        project,
        language_id,
        allow_limited_without_language=allow_limited_without_language,
    )
    if project_allowed and not _needs_language_scope_component_permissions(user, obj):
        return obj.has_action_translations
    if not project_allowed and not user.component_permissions:
        return False

    components = _get_language_scope_components(obj)
    if not components:
        return False

    project_ids = {project_id for _component_id, project_id, _restricted in components}
    projects_by_id = {project.id: project}
    missing_project_ids = project_ids - projects_by_id.keys()
    if missing_project_ids:
        projects_by_id.update(Project.objects.in_bulk(missing_project_ids))

    project_permissions = {
        project_id: (
            project_allowed
            if project_id == project.id
            else _has_project_language_permission(
                user,
                permission,
                checked_project,
                language_id,
                allow_limited_without_language=allow_limited_without_language,
            )
        )
        for project_id, checked_project in projects_by_id.items()
    }

    for component_id, project_id, restricted in components:
        project = projects_by_id[project_id]
        if not check_enforced_2fa(user, project):
            return False
        component_allowed = any(
            _has_scoped_permission(
                permission,
                permissions,
                langs,
                language_id,
                allow_limited_without_language=allow_limited_without_language,
            )
            for permissions, langs in user.component_permissions.get(component_id, ())
        )
        if not component_allowed and (
            restricted or not project_permissions[project_id]
        ):
            return False
    return True


def register_perm(*perms: str):
    def wrap_perm(function: Callable[[User, str, Model], bool | PermissionResult]):
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


def check_permission(
    user: User,
    permission: str,
    obj: Unit
    | Translation
    | CategoryLanguage
    | Component
    | ProjectLanguage
    | Category
    | Project
    | ComponentList
    | Workspace,
    *,
    allow_limited_without_language: bool = False,
) -> bool:
    """Check whether user has an object-specific permission."""
    if user.is_superuser:
        return True
    if isinstance(obj, (ProjectLanguage, CategoryLanguage)):
        return _check_language_scope_permission(
            user,
            permission,
            obj,
            allow_limited_without_language=allow_limited_without_language,
        )
    if isinstance(obj, Category):
        obj = obj.project
    if isinstance(obj, Workspace):
        return permission in user.workspace_permissions.get(obj.pk, set())
    if isinstance(obj, Project):
        return any(
            _has_scoped_permission(
                permission,
                permissions,
                langs,
                None,
                allow_limited_without_language=allow_limited_without_language,
            )
            for permissions, langs in user.get_project_permissions(obj)
        ) and check_enforced_2fa(user, obj)
    if isinstance(obj, ComponentList):
        return all(
            check_permission(
                user,
                permission,
                component,
                allow_limited_without_language=allow_limited_without_language,
            )
            and check_enforced_2fa(user, component.project)
            for component in obj.components.iterator()
        )
    if isinstance(obj, Component):
        return (
            (
                not obj.restricted
                and any(
                    _has_scoped_permission(
                        permission,
                        permissions,
                        langs,
                        allow_limited_without_language=allow_limited_without_language,
                    )
                    for permissions, langs in user.get_project_permissions(obj.project)
                )
            )
            or any(
                _has_scoped_permission(
                    permission,
                    permissions,
                    langs,
                    allow_limited_without_language=allow_limited_without_language,
                )
                for permissions, langs in user.component_permissions.get(obj.pk, ())
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
                    _has_scoped_permission(permission, permissions, langs, lang)
                    for permissions, langs in user.get_project_permissions(
                        obj.component.project
                    )
                )
            )
            or any(
                _has_scoped_permission(permission, permissions, langs, lang)
                for permissions, langs in user.component_permissions.get(
                    obj.component_id, ()
                )
            )
        ) and check_enforced_2fa(user, obj.component.project)
    msg = f"Permission {permission} does not support: {obj.__class__}: {obj!r}"
    raise TypeError(msg)


@register_perm("comment.resolve", "comment.delete", "suggestion.delete")
def check_delete_own(
    user: User, permission: str, obj: Comment | Suggestion
) -> bool | PermissionResult:
    if user.is_authenticated and obj.user == user:
        return True
    return check_permission(user, permission, obj.unit.translation)


@register_perm("unit.check")
def check_ignore_check(
    user: User, permission: str, check: Check
) -> bool | PermissionResult:
    if check.is_enforced():
        return False
    return check_permission(user, permission, check.unit.translation)


# ruff: ignore[complex-structure]
def check_can_edit(
    user: User,
    permission: str,
    obj: Translation
    | CategoryLanguage
    | Component
    | ProjectLanguage
    | Category
    | Project,
    *,
    is_vote: bool = False,
    allow_limited_without_language: bool | None = None,
) -> bool | PermissionResult:
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
            and component.effective_agreement
            and not ContributorAgreement.objects.has_agreed(user, component)
        ):
            return Denied(
                gettext(
                    "Contributing to this translation requires agreeing to its contributor license agreement."
                )
            )

    # Perform usual permission check
    if allow_limited_without_language is None:
        allow_limited_without_language = isinstance(
            obj, (Translation, ProjectLanguage, CategoryLanguage)
        )
    if not check_permission(
        user,
        permission,
        obj,
        allow_limited_without_language=allow_limited_without_language,
    ):
        if not user.is_authenticated:
            # Signing in might help, but user still might need additional privileges
            return Denied(gettext("Sign in to save translations."))
        if component and component.restricted:
            if permission == "unit.review":
                return Denied(
                    gettext(
                        "Insufficient privileges for approving translations in a restricted component."
                    )
                )
            return Denied(
                gettext(
                    "Insufficient privileges for saving translations in a restricted component."
                )
            )
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
def check_unit_review(
    user: User,
    permission: str,
    obj: Unit
    | Translation
    | CategoryLanguage
    | Component
    | ProjectLanguage
    | Category
    | Project
    | Workspace,
    *,
    skip_enabled: bool = False,
) -> bool | PermissionResult:
    if isinstance(obj, Unit):
        obj = obj.translation
    if isinstance(obj, Workspace):
        return any(
            check_unit_review(user, permission, project, skip_enabled=skip_enabled)
            for project in user.allowed_projects.filter(workspace=obj)
        )
    if not skip_enabled:
        if isinstance(obj, Translation):
            if obj.is_readonly:
                return Denied(gettext("The translation is read-only."))
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
def check_edit_approved(
    user: User,
    permission: str,
    obj: Unit
    | Translation
    | Component
    | Project
    | ProjectLanguage
    | CategoryLanguage
    | Category
    | Workspace,
    *,
    allow_limited_without_language: bool | None = None,
) -> bool | PermissionResult:
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
    if isinstance(obj, Workspace):
        return any(
            check_edit_approved(user, permission, project)
            for project in user.allowed_projects.filter(workspace=obj)
        )
    if isinstance(obj, Translation):
        component = obj.component
        if obj.is_readonly:
            return Denied(gettext("The translation is read-only."))
    elif isinstance(obj, Component):
        component = obj
    if component is not None and component.is_glossary:
        permission = "glossary.edit"
    return check_can_edit(
        user,
        permission,
        obj,
        allow_limited_without_language=allow_limited_without_language,
    )


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
def check_unit_delete(
    user: User, permission: str, obj: Unit | Translation
) -> bool | PermissionResult:
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
def check_unit_add(
    user: User, permission: str, translation: Translation
) -> bool | PermissionResult:
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
def check_translation_add(
    user: User, permission: str, obj: Component | Project
) -> bool | PermissionResult:
    if (
        isinstance(obj, Component)
        and obj.effective_new_lang == "none"
        and not obj.can_add_new_language(user, fast=True)
    ):
        return Denied(
            gettext(
                "Adding new translations is turned off in the component configuration."
            )
        )
    if obj.locked:
        return Denied(gettext("This component is currently locked."))
    return check_permission(user, permission, obj)


@register_perm("translation.auto", "unit.bulk_edit")
def check_autotranslate(
    user: User,
    permission: str,
    translation: Unit
    | Translation
    | CategoryLanguage
    | Component
    | ProjectLanguage
    | Project
    | Workspace,
) -> bool | PermissionResult:
    if isinstance(translation, Unit):
        translation = translation.translation
    if isinstance(translation, Workspace):
        return any(
            check_autotranslate(user, permission, project)
            for project in user.allowed_projects.filter(workspace=translation)
        )
    if isinstance(translation, Translation) and (
        (translation.is_source and not translation.component.intermediate)
        or translation.is_readonly
    ):
        return False
    return check_can_edit(user, permission, translation)


@register_perm("suggestion.vote")
def check_suggestion_vote(
    user: User, permission: str, obj: Unit | Translation
) -> bool | PermissionResult:
    if isinstance(obj, Unit):
        obj = obj.translation
    return check_can_edit(user, permission, obj, is_vote=True)


@register_perm("suggestion.add")
def check_suggestion_add(
    user: User,
    permission: str,
    obj: Unit | Translation | ProjectLanguage | CategoryLanguage,
) -> bool | PermissionResult:
    if isinstance(obj, Unit):
        obj = obj.translation
    if not obj.enable_suggestions or obj.is_readonly:
        return False
    # Check contributor license agreement
    if (
        not user.is_bot
        and isinstance(obj, Translation)
        and obj.component.effective_agreement
        and not ContributorAgreement.objects.has_agreed(user, obj.component)
    ):
        return False
    return check_permission(user, permission, obj)


def _category_component_filter(category: Category) -> Q:
    return (
        Q(category=category)
        | Q(category__category=category)
        | Q(category__category__category=category)
    )


def _category_translation_component_filter(category: Category) -> Q:
    return (
        Q(component__category=category)
        | Q(component__category__category=category)
        | Q(component__category__category__category=category)
    )


def _category_link_filter(category: Category) -> Q:
    return (
        Q(category=category)
        | Q(category__category=category)
        | Q(category__category__category=category)
    )


def _category_translation_filter(category: Category) -> Q:
    shared_component_ids = ComponentLink.objects.filter(
        _category_link_filter(category)
    ).values("component_id")
    return _category_translation_component_filter(category) | Q(
        component_id__in=shared_component_ids
    )


def _has_upload_scope_permission(
    scoped_permissions: Iterable[tuple[set[str], PermissionLanguageScope | None]],
    language_id: int | None = None,
) -> bool:
    return any(
        _has_scoped_permission(
            permission,
            permissions,
            langs,
            language_id,
            allow_limited_without_language=True,
        )
        for permissions, langs in scoped_permissions
        for permission in UPLOAD_SCOPE_PERMISSIONS
    )


def _get_upload_child_translations(
    obj: Component | ProjectLanguage | CategoryLanguage | Category | Project,
) -> Iterable[Translation]:
    if isinstance(obj, Component):
        return obj.translation_set.select_related(
            "component", "component__project", "language"
        )
    if isinstance(obj, ProjectLanguage | CategoryLanguage):
        return obj.translation_set
    if isinstance(obj, Category):
        return (
            Translation.objects.filter(_category_translation_filter(obj))
            .distinct()
            .select_related("component", "component__project", "language")
        )
    return (
        Translation.objects.filter(Q(component__project=obj) | Q(component__links=obj))
        .distinct()
        .select_related("component", "component__project", "language")
    )


def _get_user_upload_component_ids(user: User, language_id: int | None) -> set[int]:
    return {
        component_id
        for component_id, scoped_permissions in user.component_permissions.items()
        if _has_upload_scope_permission(scoped_permissions, language_id)
    }


def _has_upload_component_scope(
    user: User,
    obj: Component | ProjectLanguage | CategoryLanguage | Category | Project,
    language_id: int | None,
) -> bool:
    component_ids = _get_user_upload_component_ids(user, language_id)
    if not component_ids:
        return False

    if isinstance(obj, Component):
        return obj.pk in component_ids

    if isinstance(obj, Project | ProjectLanguage):
        project = obj if isinstance(obj, Project) else obj.project
        components = Component.objects.filter(pk__in=component_ids).filter(
            Q(project=project) | Q(links=project)
        )
        if language_id is not None:
            components = components.filter(translation__language_id=language_id)
        return components.exists()

    category = obj if isinstance(obj, Category) else obj.category
    own_components = Component.objects.filter(pk__in=component_ids).filter(
        _category_component_filter(category)
    )
    if language_id is not None:
        own_components = own_components.filter(translation__language_id=language_id)
    if own_components.exists():
        return True

    shared_links = ComponentLink.objects.filter(
        _category_link_filter(category), component_id__in=component_ids
    )
    if language_id is not None:
        shared_links = shared_links.filter(
            component__translation__language_id=language_id
        )
    return shared_links.exists()


def _has_upload_scope(
    user: User,
    obj: Component | ProjectLanguage | CategoryLanguage | Category | Project,
) -> bool:
    if user.is_superuser:
        return True

    if isinstance(obj, Component):
        language_id = None
        project = obj.project
    elif isinstance(obj, ProjectLanguage | CategoryLanguage):
        language_id = obj.language.id
        project = obj.project
    elif isinstance(obj, Category):
        language_id = None
        project = obj.project
    else:
        language_id = None
        project = obj

    return _has_upload_scope_permission(
        user.get_project_permissions(project), language_id
    ) or _has_upload_component_scope(user, obj, language_id)


def _bind_upload_child_scope(
    obj: Component | ProjectLanguage | CategoryLanguage | Category | Project,
    translation: Translation,
) -> None:
    if isinstance(obj, Component):
        if translation.component_id == obj.pk:
            translation.component = obj
            _bind_upload_child_workflow_settings(obj.project, translation)
        return

    project = obj if isinstance(obj, Project) else obj.project
    if translation.component.project_id == project.pk:
        translation.component.project = project
        _bind_upload_child_workflow_settings(project, translation)


def _bind_upload_child_workflow_settings(
    project: Project, translation: Translation
) -> None:
    project_language = project.project_languages.data.get(translation.language_id)
    if (
        project_language is not None
        and "workflow_settings" in project_language.__dict__
    ):
        translation.__dict__["workflow_settings"] = project_language.workflow_settings


def _has_upload_child(
    user: User,
    obj: Component | ProjectLanguage | CategoryLanguage | Category | Project,
) -> bool:
    if not _has_upload_scope(user, obj):
        return False

    for translation in _get_upload_child_translations(obj):
        _bind_upload_child_scope(obj, translation)
        if user.has_perm("upload.perform", translation):
            return True
    return False


@register_perm("upload.perform")
def check_upload(
    user: User,
    permission: str,
    obj: Translation
    | Component
    | ProjectLanguage
    | CategoryLanguage
    | Category
    | Project,
) -> bool | PermissionResult:
    """
    Check whether user can perform any upload operation.

    The actual check for the method is implemented in
    weblate.trans.util.check_upload_method_permissions.
    """
    if isinstance(obj, Translation):
        # Source upload
        if obj.is_source and not user.has_perm("source.edit", obj):
            return Denied(
                gettext("Insufficient privileges for editing source strings.")
            )
        # Bilingual source translations
        if (
            obj.is_source
            and not obj.is_template
            and not issubclass(obj.component.file_format_cls, BilingualUpdateMixin)
        ):
            return Denied(
                gettext("The file format does not support updating source strings.")
            )
        if obj.component.is_glossary:
            permission = "glossary.upload"
        return check_can_edit(user, permission, obj) and (
            # Normal upload
            check_edit_approved(user, "unit.edit", obj)
            # Suggestion upload
            or check_suggestion_add(user, "suggestion.add", obj)
            # Add upload
            or check_suggestion_add(user, "unit.add", obj)
            # Source upload
            or obj.is_source
        )

    return _has_upload_child(user, obj)


@register_perm("machinery.view")
def check_machinery(
    user: User, permission: str, obj: Translation | Component | Project
) -> bool | PermissionResult:
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
def check_translation_delete(
    user: User, permission: str, obj: Translation | CategoryLanguage | ProjectLanguage
) -> bool | PermissionResult:
    if (
        isinstance(obj, (Translation, CategoryLanguage, ProjectLanguage))
        and obj.is_source
    ):
        return False
    return check_permission(user, permission, obj)


@register_perm("reports.view", "change.download")
def check_possibly_global(
    user: User, permission: str, obj: Language | Translation | Component | Project
) -> bool | PermissionResult:
    if obj is None or isinstance(obj, Language):
        return user.is_superuser
    return check_permission(user, permission, obj)


@register_perm("meta:vcs.status")
def check_repository_status(
    user: User, permission: str, obj: Translation | Component | Project
) -> bool | PermissionResult:
    return (
        check_permission(user, "vcs.push", obj)
        or check_permission(user, "vcs.commit", obj)
        or check_permission(user, "vcs.reset", obj)
        or check_permission(user, "vcs.update", obj)
    )


@register_perm("meta:team.edit")
def check_team_edit(
    user: User, permission: str, obj: Group | Project | Workspace
) -> bool:
    # ruff: ignore[import-outside-top-level]
    from weblate.auth.models import Group

    return (
        check_global_permission(user, "group.edit")
        or (
            isinstance(obj, Group)
            and obj.defining_project
            and check_permission(user, "project.permissions", obj.defining_project)
        )
        or (
            isinstance(obj, Group)
            and obj.defining_workspace
            and check_permission(user, "workspace.edit_members", obj.defining_workspace)
        )
        or (
            isinstance(obj, Project)
            and check_permission(user, "project.permissions", obj)
        )
        or (
            isinstance(obj, Workspace)
            and check_permission(user, "workspace.edit_members", obj)
        )
    )


@register_perm("meta:team.users")
def check_team_edit_users(
    user: User, permission: str, obj: Group | Project | Workspace
) -> bool | PermissionResult:
    # ruff: ignore[import-outside-top-level]
    from weblate.auth.models import Group

    return check_team_edit(user, permission, obj) or (
        isinstance(obj, Group) and obj.pk in user.administered_group_ids
    )


@register_perm("meta:billing.view")
def check_billing_view(
    user: User, permission: str, obj: Billing | Project
) -> bool | PermissionResult:
    if user.has_perm("billing.manage"):
        return True

    billings: list[Billing] | QuerySet[Billing]
    # We check Billing by hasattr to avoid importing optional Django app. To make type
    # checker understand this, there is negative check on Project and cast in the
    # check_permission call.
    if hasattr(obj, "all_projects") and not isinstance(obj, Project):
        billings = [obj]
    else:
        billings = obj.billings

    return any(
        billing.workspace_id
        and check_permission(user, "workspace.edit", billing.workspace)
        for billing in billings
    )


@register_perm("billing:project.permissions")
def check_billing(user: User, permission: str, obj: Project) -> bool | PermissionResult:
    if user.is_superuser:
        return True

    if (
        "weblate.billing" in settings.INSTALLED_APPS
        and not any(billing.plan.change_access_control for billing in obj.billings)
        and not obj.access_control
    ):
        return False

    return check_permission(user, "project.permissions", obj)


@register_perm("announcement.delete")
def check_announcement_delete(
    user: User,
    permission: str,
    obj: Announcement | Project | ProjectLanguage | Category | Component | None,
) -> bool | PermissionResult:
    if isinstance(obj, Announcement):
        if obj.component_id is not None:
            if obj.language_id is not None:
                try:
                    translation = obj.component.translation_set.get(
                        language_id=obj.language_id
                    )
                except Translation.DoesNotExist:
                    return False
                return check_permission(user, permission, translation)
            obj = obj.component
        elif obj.category_id is not None:
            obj = obj.category
        elif obj.language_id is not None:
            if obj.project_id is not None:
                obj = ProjectLanguage(obj.project, obj.language)
            else:
                obj = None
        else:
            obj = obj.project

    if obj is None:
        return check_global_permission(user, permission)
    return check_permission(user, permission, obj)


# This does not exist for real
@register_perm("meta:unit.flag")
def check_unit_flag(
    user: User, permission: str, obj: Unit | Translation
) -> bool | PermissionResult:
    if isinstance(obj, Unit):
        obj = obj.translation
    if not obj.component.is_glossary:
        return user.has_perm("source.edit", obj)

    return check_can_edit(user, "glossary.edit", obj)


@register_perm("memory.edit", "memory.delete")
def check_memory_perms(
    user: User, permission: str, memory: Memory | Project
) -> bool | PermissionResult:
    # ruff: ignore[import-outside-top-level]
    from weblate.memory.models import Memory

    if isinstance(memory, Memory):
        for scope in memory.get_scope_list():
            if scope.user_id == user.id:
                return True
            if scope.project_id:
                project = scope.project
                if project is not None and check_permission(user, permission, project):
                    return True
            if scope.workspace_id:
                source_project = scope.source_project
                if source_project is not None and check_permission(
                    user, permission, source_project
                ):
                    return True
                if scope.workspace is not None and check_permission(
                    user, permission, scope.workspace
                ):
                    return True
        return check_global_permission(user, "memory.manage")

    project = memory
    if project is None:
        return check_global_permission(user, "memory.manage")
    return check_permission(user, permission, project)
