# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver

from weblate.trans.alerts.base import AlertSeverity
from weblate.trans.models._conf import WeblateConf
from weblate.trans.models.agreement import ContributorAgreement
from weblate.trans.models.alert import Alert
from weblate.trans.models.announcement import Announcement
from weblate.trans.models.category import Category
from weblate.trans.models.change import Change
from weblate.trans.models.comment import Comment, schedule_comment_stats_update
from weblate.trans.models.component import Component, ComponentLink
from weblate.trans.models.componentlist import AutoComponentList, ComponentList
from weblate.trans.models.label import Label
from weblate.trans.models.pending import PendingUnitChange
from weblate.trans.models.project import CommitPolicyChoices, Project
from weblate.trans.models.report import Report
from weblate.trans.models.suggestion import Suggestion, SuggestionAddResult, Vote
from weblate.trans.models.translation import Translation
from weblate.trans.models.unit import Unit
from weblate.trans.models.variant import Variant
from weblate.trans.models.workflow import WorkflowSetting
from weblate.trans.removal import get_current_removal_batch
from weblate.trans.signals import user_pre_delete
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.files import remove_tree

if TYPE_CHECKING:
    from weblate.auth.models import User

__all__ = [
    "Alert",
    "AlertSeverity",
    "Announcement",
    "Category",
    "Change",
    "Comment",
    "CommitPolicyChoices",
    "Component",
    "ComponentLink",
    "ComponentList",
    "ContributorAgreement",
    "Label",
    "PendingUnitChange",
    "Project",
    "Report",
    "Suggestion",
    "SuggestionAddResult",
    "Translation",
    "Unit",
    "Variant",
    "Vote",
    "WeblateConf",
    "WorkflowSetting",
]


def delete_object_dir(instance: Project | Component) -> None:
    """Remove path if it exists."""
    project_path = instance.full_path
    if os.path.exists(project_path):
        remove_tree(project_path)


@receiver(pre_delete, sender=Project)
def project_pre_delete(sender, instance: Project, **kwargs) -> None:
    # ruff: ignore[import-outside-top-level]
    from weblate.memory.models import Memory, MemoryScope

    Memory.objects.using("default").delete_scope(
        Q(
            scope__in=(MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE),
            project=instance,
        )
        | Q(
            scope__in=(MemoryScope.SCOPE_SHARED, MemoryScope.SCOPE_WORKSPACE),
            source_project=instance,
        ),
        delete_legacy=False,
    )


@receiver(post_delete, sender=Project)
def project_post_delete(sender, instance: Project, **kwargs) -> None:
    """
    Project deletion hook.

    - delete project directory
    - update stats
    """
    batch = get_current_removal_batch()
    if batch is None:
        transaction.on_commit(instance.stats.update_parents)
    else:
        batch.collect_stats(instance.stats.get_update_objects())
    instance.stats.delete()

    # Remove directory
    delete_object_dir(instance)

    # Project-scoped memory rows are owned by MemoryScope. Once the project FK
    # cascade removes those scopes, cleanup can delete scope-less rows in the
    # background without delaying project deletion. By post_delete the scope rows
    # are gone, and project-file memory origins are upload names rather than
    # component paths, so a project path prefix would miss them.
    # ruff: ignore[import-outside-top-level]
    from weblate.memory.tasks import cleanup_orphaned_memory

    cleanup_orphaned_memory.delay_on_commit()


@receiver(pre_delete, sender=Component)
def component_pre_delete(sender, instance: Component, **kwargs) -> None:
    instance.memory_full_slug = instance.full_slug
    instance.memory_workspace_id = instance.project.workspace_id
    batch = instance.removal_batch or get_current_removal_batch()
    if batch is not None:
        batch.collect_stats(instance.stats.get_update_objects())
        batch.collect_stats(instance.stats.get_language_update_objects())
        return
    # Collect list of stats to update, this can't be done after removal
    instance.stats.collect_update_objects(
        extra_objects=instance.stats.get_language_update_objects()
    )


@receiver(post_delete, sender=Component)
def component_post_delete(sender, instance: Component, **kwargs) -> None:
    """
    Component deletion hook.

    - delete component directory
    - update stats, this is accompanied by component_pre_delete
    """
    batch = instance.removal_batch or get_current_removal_batch()
    if batch is None:
        transaction.on_commit(instance.stats.update_parents)
    instance.stats.delete()

    # Do not delete linked components
    if not instance.is_repo_link:
        delete_object_dir(instance)

    memory_full_slug = getattr(instance, "memory_full_slug", None)
    if memory_full_slug is not None:
        instance.delete_automatic_memory_scopes(
            memory_full_slug,
            instance.project_id,
            getattr(instance, "memory_workspace_id", None),
        )

    if batch is None:
        instance.cleanup_conflicting_repository_setup_alerts()


@receiver(post_delete, sender=Translation)
def translation_post_delete(sender, instance: Translation, **kwargs) -> None:
    """Delete translation stats on translation deletion."""
    transaction.on_commit(instance.stats.delete)


type StatsTopology = tuple[set[int], set[int], set[int]]


def collect_stats_topology(
    component_id: int, project_id: int, category_id: int | None
) -> StatsTopology:
    """Collect persistent identifiers for a placement-dependent stats update."""
    return ({component_id}, {project_id}, {category_id} if category_id else set())


def merge_stats_topologies(*topologies: StatsTopology) -> StatsTopology:
    """Merge placement-dependent stats update identifiers."""
    components: set[int] = set()
    projects: set[int] = set()
    categories: set[int] = set()
    for topology in topologies:
        components.update(topology[0])
        projects.update(topology[1])
        categories.update(topology[2])
    return components, projects, categories


def schedule_stats_topology_update(*topologies: StatsTopology) -> None:
    """Queue recalculation of placement-dependent statistics."""
    transaction.on_commit(partial(queue_stats_topology_update, *topologies))


def queue_stats_topology_update(*topologies: StatsTopology) -> None:
    """Send a placement-dependent statistics update to Celery."""
    # ruff: ignore[import-outside-top-level]
    from weblate.utils.tasks import update_component_topology_stats

    component_ids, project_ids, category_ids = merge_stats_topologies(*topologies)
    update_component_topology_stats.delay(
        sorted(component_ids), sorted(project_ids), sorted(category_ids)
    )


def is_category_delete(origin: object | None) -> bool:
    """Whether categories are the root objects being deleted."""
    return (
        origin is None
        or isinstance(origin, Category)
        or (getattr(origin, "model", None) is Category)
    )


@receiver(pre_delete, sender=Category)
@disable_for_loaddata
def category_stats_before_delete(
    sender, instance: Category, origin=None, **kwargs
) -> None:
    """Collect stats affected when category links are set to NULL."""
    if not is_category_delete(origin):
        return
    component_ids = list(
        ComponentLink.objects.filter(category=instance).values_list(
            "component_id", flat=True
        )
    )
    if not component_ids:
        return

    batch = get_current_removal_batch()
    if batch is not None:
        for component in Component.objects.filter(pk__in=component_ids):
            batch.collect_stats(component.stats.get_language_update_objects())
            batch.collect_stats(component.stats.get_update_objects())
        return

    deletion_origin = origin if origin is not None else instance
    deletion_state = getattr(deletion_origin, "__dict__", instance.__dict__)
    topology: StatsTopology | None = deletion_state.get("category_stats_topology")
    if topology is None:
        topology = (set(), set(), set())
        deletion_state["category_stats_topology"] = topology
        schedule_stats_topology_update(topology)
    topology[0].update(component_ids)
    topology[1].add(instance.project_id)
    category = instance.category
    while category is not None:
        if category.pk is not None:
            topology[2].add(category.pk)
        category = category.category


@receiver(pre_save, sender=Component)
@disable_for_loaddata
def component_topology_before_save(sender, instance: Component, **kwargs) -> None:
    if not instance.pk:
        return
    try:
        old = Component.objects.get(pk=instance.pk)
    except Component.DoesNotExist:
        return
    if (old.project_id, old.category_id) != (instance.project_id, instance.category_id):
        instance.__dict__["stats_topology_before"] = collect_stats_topology(
            old.pk, old.project_id, old.category_id
        )


@receiver(post_save, sender=Component)
@disable_for_loaddata
def component_topology_after_save(sender, instance: Component, **kwargs) -> None:
    before = instance.__dict__.pop("stats_topology_before", None)
    if before is None:
        return
    schedule_stats_topology_update(
        before,
        collect_stats_topology(instance.pk, instance.project_id, instance.category_id),
    )


@receiver(pre_save, sender=ComponentLink)
@disable_for_loaddata
def component_link_stats_before_save(sender, instance: ComponentLink, **kwargs) -> None:
    if instance.pk:
        try:
            old = ComponentLink.objects.get(pk=instance.pk)
        except ComponentLink.DoesNotExist:
            return
        instance.__dict__["stats_topology_before"] = collect_stats_topology(
            old.component_id, old.project_id, old.category_id
        )


@receiver(post_save, sender=ComponentLink)
@disable_for_loaddata
def component_link_stats_after_save(sender, instance: ComponentLink, **kwargs) -> None:
    before = instance.__dict__.pop("stats_topology_before", None)
    current = collect_stats_topology(
        instance.component_id, instance.project_id, instance.category_id
    )
    schedule_stats_topology_update(*((before, current) if before else (current,)))


def is_standalone_component_link_delete(origin: object | None) -> bool:
    """Whether a link is explicitly deleted rather than removed by a cascade."""
    return (
        origin is None
        or isinstance(origin, ComponentLink)
        or (getattr(origin, "model", None) is ComponentLink)
    )


@receiver(pre_delete, sender=ComponentLink)
@disable_for_loaddata
def component_link_stats_before_delete(
    sender, instance: ComponentLink, origin=None, **kwargs
) -> None:
    if not is_standalone_component_link_delete(origin):
        return
    instance.__dict__["stats_topology_before"] = collect_stats_topology(
        instance.component_id, instance.project_id, instance.category_id
    )


@receiver(post_delete, sender=ComponentLink)
@disable_for_loaddata
def component_link_stats_after_delete(
    sender, instance: ComponentLink, origin=None, **kwargs
) -> None:
    if not is_standalone_component_link_delete(origin):
        return
    before = instance.__dict__.pop("stats_topology_before", None)
    if before is not None:
        schedule_stats_topology_update(before)


@receiver(m2m_changed, sender=Unit.labels.through)
@disable_for_loaddata
def change_labels(sender, instance, action, pk_set, **kwargs) -> None:
    """Update unit labels."""
    if (
        action not in {"post_add", "post_remove", "post_clear"}
        or (action != "post_clear" and not pk_set)
        or not instance.is_source
    ):
        return
    if not instance.is_batch_update:
        instance.translation.component.invalidate_cache()


@receiver(pre_delete, sender=Label)
def label_pre_delete(sender, instance: Label, **kwargs) -> None:
    instance.project.collect_label_cleanup(instance)


@receiver(post_delete, sender=Label)
def label_post_delete(sender, instance, **kwargs) -> None:
    """Invalidate label stats on its deletion."""
    transaction.on_commit(
        partial(instance.project.cleanup_label_stats, name=instance.name)
    )


@receiver(user_pre_delete)
def user_commit_pending(sender, instance: User, **kwargs) -> None:
    """Commit pending changes for user on account removal."""
    # All user changes
    all_changes = Change.objects.last_changes(instance).filter(user=instance)

    # Filter where project is active
    user_translation_ids = all_changes.values_list("translation", flat=True).distinct()

    # Commit changes where user is last author
    for translation in Translation.objects.filter(pk__in=user_translation_ids):
        try:
            last_author = translation.change_set.content()[0].author
        except IndexError:
            # Non content changes
            continue
        if last_author == instance:
            translation.commit_pending("user delete", None)


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def user_comment_stats_before_delete(sender, instance: User, **kwargs) -> None:
    """Collect translations affected by comments removed with a user."""
    instance.__dict__["comment_stats_translation_ids"] = list(
        Comment.objects.filter(user=instance)
        .values_list("unit__translation_id", flat=True)
        .distinct()
    )


@receiver(post_delete, sender=settings.AUTH_USER_MODEL)
def user_comment_stats_after_delete(sender, instance: User, **kwargs) -> None:
    """Queue a batched stats refresh after a user comment cascade."""
    schedule_comment_stats_update(
        instance.__dict__.pop("comment_stats_translation_ids", [])
    )


@receiver(m2m_changed, sender=ComponentList.components.through)
@disable_for_loaddata
def change_componentlist(sender, instance, action, **kwargs) -> None:
    if not action.startswith("post_"):
        return
    transaction.on_commit(instance.stats.update_stats)


@receiver(post_save, sender=AutoComponentList)
@disable_for_loaddata
def auto_componentlist(sender, instance, **kwargs) -> None:
    for component in Component.objects.iterator():
        instance.check_match(component)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def auto_project_componentlist(sender, instance, **kwargs) -> None:
    for component in instance.component_set.iterator():
        auto_component_list(sender, component)


@receiver(post_save, sender=Component)
@disable_for_loaddata
def auto_component_list(sender, instance, **kwargs) -> None:
    for auto in AutoComponentList.objects.iterator():
        auto.check_match(instance)


@receiver(post_delete, sender=Component)
@disable_for_loaddata
def post_delete_linked(sender, instance, **kwargs) -> None:
    batch = instance.removal_batch or get_current_removal_batch()
    if batch is not None:
        batch.collect_linked_component(instance.linked_component_id)
        return
    # When removing project, the linked component might be already deleted now
    with suppress(Component.DoesNotExist):
        if instance.linked_component:
            instance.linked_component.update_alerts()


@receiver(post_save, sender=Comment)
@receiver(post_save, sender=Suggestion)
@disable_for_loaddata
def stats_invalidate(sender, instance, **kwargs) -> None:
    """Invalidate stats on new comments or suggestions."""
    instance.unit.invalidate_related_cache()
