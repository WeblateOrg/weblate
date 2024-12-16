# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from functools import partial

from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver

from weblate.trans.models._conf import WeblateConf
from weblate.trans.models.agreement import ContributorAgreement
from weblate.trans.models.alert import Alert
from weblate.trans.models.announcement import Announcement
from weblate.trans.models.category import Category
from weblate.trans.models.change import Change
from weblate.trans.models.comment import Comment
from weblate.trans.models.component import Component
from weblate.trans.models.componentlist import AutoComponentList, ComponentList
from weblate.trans.models.label import Label
from weblate.trans.models.project import Project
from weblate.trans.models.suggestion import Suggestion, Vote
from weblate.trans.models.translation import Translation
from weblate.trans.models.unit import Unit
from weblate.trans.models.variant import Variant
from weblate.trans.models.workflow import WorkflowSetting
from weblate.trans.signals import user_pre_delete
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.files import remove_tree

__all__ = [
    "Alert",
    "Announcement",
    "Category",
    "Change",
    "Comment",
    "Component",
    "ComponentList",
    "ContributorAgreement",
    "Label",
    "Project",
    "Suggestion",
    "Translation",
    "Unit",
    "Variant",
    "Vote",
    "WeblateConf",
    "WorkflowSetting",
]


def delete_object_dir(instance) -> None:
    """Remove path if it exists."""
    project_path = instance.full_path
    if os.path.exists(project_path):
        remove_tree(project_path)


@receiver(post_delete, sender=Project)
def project_post_delete(sender, instance, **kwargs) -> None:
    """
    Project deletion hook.

    - delete project directory
    - update stats
    """
    # Update stats
    transaction.on_commit(instance.stats.update_parents)
    instance.stats.delete()

    # Remove directory
    delete_object_dir(instance)


@receiver(pre_delete, sender=Component)
def component_pre_delete(sender, instance, **kwargs) -> None:
    # Collect list of stats to update, this can't be done after removal
    instance.stats.collect_update_objects()


@receiver(post_delete, sender=Component)
def component_post_delete(sender, instance, **kwargs) -> None:
    """
    Component deletion hook.

    - delete component directory
    - update stats, this is accompanied by component_pre_delete
    """
    # Update stats
    transaction.on_commit(instance.stats.update_parents)
    instance.stats.delete()

    # Do not delete linked components
    if not instance.is_repo_link:
        delete_object_dir(instance)


@receiver(post_delete, sender=Translation)
def translation_post_delete(sender, instance, **kwargs) -> None:
    """Delete translation stats on translation deletion."""
    transaction.on_commit(instance.stats.delete)


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
def label_pre_delete(sender, instance, **kwargs) -> None:
    instance.project.collect_label_cleanup(instance)


@receiver(post_delete, sender=Label)
def label_post_delete(sender, instance, **kwargs) -> None:
    """Invalidate label stats on its deletion."""
    transaction.on_commit(
        partial(instance.project.cleanup_label_stats, name=instance.name)
    )


@receiver(user_pre_delete)
def user_commit_pending(sender, instance, **kwargs) -> None:
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
    # When removing project, the linked component might be already deleted now
    try:
        if instance.linked_component:
            instance.linked_component.update_alerts()
    except Component.DoesNotExist:
        pass


@receiver(post_save, sender=Comment)
@receiver(post_save, sender=Suggestion)
@disable_for_loaddata
def stats_invalidate(sender, instance, **kwargs) -> None:
    """Invalidate stats on new comment or suggestion."""
    instance.unit.invalidate_related_cache()
