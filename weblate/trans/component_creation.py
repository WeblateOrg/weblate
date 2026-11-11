# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from weblate.trans.models import Component, Project
from weblate.trans.util import is_repo_link

if TYPE_CHECKING:
    from django.forms import ModelForm

    from weblate.auth.models import User
    from weblate.trans.models.component import ComponentQuerySet
    from weblate.trans.models.project import ProjectQuerySet


def get_creation_projects(user: User) -> ProjectQuerySet:
    """Return projects available for component creation."""
    if user.is_superuser:
        return Project.objects.order()
    if "weblate.billing" in settings.INSTALLED_APPS:
        # ruff: ignore[import-outside-top-level]
        from weblate.billing.models import Billing

        return user.accessible_managed_projects.filter(
            workspace__billing__in=Billing.objects.get_valid()
        ).order()
    return user.accessible_managed_projects


def get_creation_components(
    user: User, projects: ProjectQuerySet, project_id: int | None = None
) -> ComponentQuerySet:
    """Return accessible repository components in creation projects."""
    components = (
        Component.objects.filter_access(user)
        .with_repo()
        .filter(project__in=projects)
        .order_project()
    )
    if project_id is not None:
        components = components.filter(project_id=project_id)
    return components


def get_component_branches(component: Component) -> list[str]:
    """Discover unused remote branches for one eligible component."""
    branches = component.repository.list_remote_branches(timeout=15)
    existing = set(
        Component.objects.filter(repo=component.repo).values_list("branch", flat=True)
    )
    return [
        branch
        for branch in branches
        if branch != component.branch and branch not in existing
    ]


def get_accessible_repository_link(user: User, repo: str | None) -> Component | None:
    """Resolve a repository link without exposing hidden or policy-blocked targets."""
    if not repo or not is_repo_link(repo):
        return None
    # Import after the trans models are initialized to avoid a permissions cycle.
    from weblate.auth.permissions import check_enforced_2fa  # ruff: ignore[import-outside-top-level]

    try:
        component = Component.objects.filter_access(user).get_linked(repo)
    except (Component.DoesNotExist, ValueError):
        return None
    if component is None or (
        not user.is_superuser and not check_enforced_2fa(user, component.project)
    ):
        return None
    return component


def changes_component_sensitive_access(form: ModelForm[Component], user: User) -> bool:
    """Check submitted access changes before model validation touches the repo."""
    if form.instance.pk and "restricted" in form.changed_data:
        return True
    restricted = form.instance.restricted
    if not form.instance.pk and "restricted" in form.fields:
        field = form["restricted"]
        try:
            restricted = field.field.clean(field.value())
        except ValidationError:
            return False
    if restricted or "repo" not in form.changed_data:
        return False
    # Normalize only this field; full form validation can mutate the checkout.
    repo_field = form["repo"]
    try:
        repo = repo_field.field.clean(repo_field.value())
    except ValidationError:
        return False
    source = get_accessible_repository_link(user, repo)
    return source is not None and source.restricted


def validate_repository_link(
    user: User, repo: str, *, require_edit: bool = True
) -> Component | None:
    """Validate visibility before checking authority to use a linked repository."""
    if not is_repo_link(repo) or "/" not in repo[10:]:
        return None
    component = get_accessible_repository_link(user, repo)
    if component is None:
        raise ValidationError(
            gettext("This component does not exist or you cannot access it.")
        )
    if require_edit and not user.has_perm("component.edit", component):
        raise ValidationError(
            gettext("You do not have permission to access this component.")
        )
    return component
