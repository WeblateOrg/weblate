#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.conf import settings

from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.trans.models import (
    Component,
    ContributorAgreement,
    Project,
    Translation,
    Unit,
)
from weblate.utils.stats import ProjectLanguage

SPECIALS = {}


def register_perm(*perms):
    def wrap_perm(function):
        for perm in perms:
            SPECIALS[perm] = function
        return function

    return wrap_perm


def check_global_permission(user, permission, obj):
    """Generic permission check for base classes."""
    if user.is_superuser:
        return True
    return user.groups.filter(roles__permissions__codename=permission).exists()


def check_permission(user, permission, obj):
    """Generic permission check for base classes."""
    if user.is_superuser:
        return True
    if isinstance(obj, ProjectLanguage):
        obj = obj.project
    if isinstance(obj, Project):
        return any(
            permission in permissions
            for permissions, _langs in user.project_permissions[obj.pk]
        )
    if isinstance(obj, Component):
        return (
            not obj.restricted
            and any(
                permission in permissions
                for permissions, _langs in user.project_permissions[obj.project_id]
            )
        ) or any(
            permission in permissions
            for permissions, _langs in user.component_permissions[obj.pk]
        )
    if isinstance(obj, Translation):
        lang = obj.language_id
        return (
            not obj.component.restricted
            and any(
                permission in permissions and lang in langs
                for permissions, langs in user.project_permissions[
                    obj.component.project_id
                ]
            )
        ) or any(
            permission in permissions and lang in langs
            for permissions, langs in user.component_permissions[obj.component_id]
        )
    raise ValueError(
        f"Permission {permission} does not support: {obj.__class__.__name__}"
    )


@register_perm("comment.delete", "suggestion.delete")
def check_delete_own(user, permission, obj):
    if user.is_authenticated and obj.user == user:
        return True
    return check_permission(user, permission, obj.unit.translation)


@register_perm("unit.check")
def check_ignore_check(user, permission, check):
    if check.is_enforced():
        return False
    return check_permission(user, permission, check.unit.translation)


def check_can_edit(user, permission, obj, is_vote=False):
    translation = component = None

    if isinstance(obj, Translation):
        translation = obj
        component = obj.component
        project = component.project
    elif isinstance(obj, Component):
        component = obj
        project = component.project
    elif isinstance(obj, Project):
        project = obj
    else:
        raise ValueError("Uknown object for permission check!")

    # Email is needed for user to be able to edit
    if user.is_authenticated and not user.email:
        return False

    if component:
        # Check component lock
        if component.locked:
            return False

        # Check contributor agreement
        if component.agreement and not ContributorAgreement.objects.has_agreed(
            user, component
        ):
            return False

    # Perform usual permission check
    if not check_permission(user, permission, obj):
        return False

    # Special check for source strings (templates)
    if (
        translation
        and translation.is_template
        and not check_permission(user, "unit.template", obj)
    ):
        return False

    # Special checks for voting
    if is_vote and component and not component.suggestion_voting:
        return False
    if (
        not is_vote
        and translation
        and component.suggestion_voting
        and component.suggestion_autoaccept > 0
        and not check_permission(user, "unit.override", obj)
    ):
        return False

    # Billing limits
    if not project.paid:
        return False

    return True


@register_perm("unit.review")
def check_unit_review(user, permission, obj, skip_enabled=False):
    if not skip_enabled:
        if isinstance(obj, Translation):
            if not obj.enable_review:
                return False
        else:
            if isinstance(obj, Component):
                project = obj.project
            else:
                project = obj
            if not project.source_review and not project.translation_review:
                return False
    return check_can_edit(user, permission, obj)


@register_perm("unit.edit", "suggestion.accept")
def check_edit_approved(user, permission, obj):
    component = None
    if isinstance(obj, Unit):
        unit = obj
        obj = unit.translation
        # Read only check is unconditional as there is another one
        # in PluralTextarea.render
        if unit.readonly or (
            unit.approved
            and not check_unit_review(user, "unit.review", obj, skip_enabled=True)
        ):
            return False
    if isinstance(obj, Translation):
        component = obj.component
        if obj.is_readonly:
            return False
    elif isinstance(obj, Component):
        component = obj
    if component is not None and component.is_glossary:
        permission = "glossary.edit"
    return check_can_edit(user, permission, obj)


def check_manage_units(translation: Translation, component: Component) -> bool:
    if not isinstance(component, Component):
        return False
    source = translation.is_source
    template = component.has_template()
    # Add only to source in monolingual
    if not source and template:
        return False
    # Check if adding is generally allowed
    if not component.manage_units or (template and not component.edit_template):
        return False
    return True


@register_perm("unit.delete")
def check_unit_delete(user, permission, obj):
    if isinstance(obj, Unit):
        obj = obj.translation
    component = obj.component
    # Check if removing is generally allowed
    if not check_manage_units(obj, component):
        return False
    if component.is_glossary:
        permission = "glossary.delete"
    return check_can_edit(user, permission, obj)


@register_perm("unit.add")
def check_unit_add(user, permission, translation):
    component = translation.component
    # Check if adding is generally allowed
    if not check_manage_units(translation, component):
        return False

    # Does file format support adding?
    if not component.file_format_cls.can_add_unit:
        return False

    if component.is_glossary:
        permission = "glossary.add"

    return check_can_edit(user, permission, translation)


@register_perm("translation.add")
def check_translation_add(user, permission, component):
    if component.new_lang == "none" and not component.can_add_new_language(
        user, fast=True
    ):
        return False
    if component.locked:
        return False
    return check_permission(user, permission, component)


@register_perm("translation.auto")
def check_autotranslate(user, permission, translation):
    if isinstance(translation, Translation) and (
        (translation.is_source and not translation.component.intermediate)
        or translation.is_readonly
    ):
        return False
    return check_can_edit(user, permission, translation)


@register_perm("suggestion.vote")
def check_suggestion_vote(user, permission, obj):
    if isinstance(obj, Unit):
        obj = obj.translation
    return check_can_edit(user, permission, obj, is_vote=True)


@register_perm("suggestion.add")
def check_suggestion_add(user, permission, obj):
    if isinstance(obj, Unit):
        obj = obj.translation
    if not obj.component.enable_suggestions or obj.is_readonly:
        return False
    # Check contributor agreement
    if obj.component.agreement and not ContributorAgreement.objects.has_agreed(
        user, obj.component
    ):
        return False
    return check_permission(user, permission, obj)


@register_perm("upload.perform")
def check_contribute(user, permission, translation):
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
def check_machinery(user, permission, obj):
    # No permission in case there are no machinery services enabled
    if not MACHINE_TRANSLATION_SERVICES.exists():
        return False

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
def check_translation_delete(user, permission, obj):
    if obj.is_source:
        return False
    return check_permission(user, permission, obj)


@register_perm("reports.view", "change.download")
def check_possibly_global(user, permission, obj):
    if obj is None:
        return user.is_superuser
    return check_permission(user, permission, obj)


@register_perm("meta:vcs.status")
def check_repository_status(user, permission, obj):
    return (
        check_permission(user, "vcs.push", obj)
        or check_permission(user, "vcs.commit", obj)
        or check_permission(user, "vcs.reset", obj)
        or check_permission(user, "vcs.update", obj)
    )


@register_perm("billing.view")
def check_billing_view(user, permission, obj):
    if hasattr(obj, "all_projects"):
        if user.is_superuser or obj.owners.filter(pk=user.pk).exists():
            return True
        # This is a billing object
        return any(check_permission(user, permission, prj) for prj in obj.all_projects)
    return check_permission(user, permission, obj)


@register_perm("billing:project.permissions")
def check_billing(user, permission, obj):
    if "weblate.billing" in settings.INSTALLED_APPS:
        if not any(billing.plan.change_access_control for billing in obj.billings):
            return False

    return check_permission(user, "project.permissions", obj)


# This does not exist for real
@register_perm("announcement.delete")
def check_announcement_delete(user, permission, obj):
    return (
        user.is_superuser
        or (obj.component and check_permission(user, "component.edit", obj.component))
        or (obj.project and check_permission(user, "project.edit", obj.project))
    )


# This does not exist for real
@register_perm("unit.flag")
def check_unit_flag(user, permission, obj: Translation):
    if not obj.component.is_glossary or obj.is_source:
        return user.has_perm("source.edit", obj)

    return user.has_perm("glossary.edit", obj)
