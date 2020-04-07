#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


import os
import shutil

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from weblate.trans.models._conf import WeblateConf
from weblate.trans.models.agreement import ContributorAgreement
from weblate.trans.models.alert import Alert
from weblate.trans.models.announcement import Announcement
from weblate.trans.models.change import Change
from weblate.trans.models.comment import Comment
from weblate.trans.models.component import Component
from weblate.trans.models.componentlist import AutoComponentList, ComponentList
from weblate.trans.models.dictionary import Dictionary
from weblate.trans.models.label import Label
from weblate.trans.models.project import Project
from weblate.trans.models.shaping import Shaping
from weblate.trans.models.suggestion import Suggestion, Vote
from weblate.trans.models.translation import Translation
from weblate.trans.models.unit import Unit
from weblate.trans.signals import user_pre_delete
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.files import remove_readonly

__all__ = [
    "Project",
    "Component",
    "Translation",
    "Unit",
    "Suggestion",
    "Comment",
    "Vote",
    "Change",
    "Dictionary",
    "Announcement",
    "ComponentList",
    "WeblateConf",
    "ContributorAgreement",
    "Alert",
    "Shaping",
    "Label",
]


def delete_object_dir(instance):
    """Remove path if it exists."""
    project_path = instance.full_path
    if os.path.exists(project_path):
        shutil.rmtree(project_path, onerror=remove_readonly)


@receiver(post_delete, sender=Project)
def project_post_delete(sender, instance, **kwargs):
    """Handler to delete (sub)project directory on project deletion."""
    # Invalidate stats
    instance.stats.invalidate()

    # Remove directory
    delete_object_dir(instance)


@receiver(post_delete, sender=Component)
def component_post_delete(sender, instance, **kwargs):
    """Handler to delete (sub)project directory on project deletion."""
    # Invalidate stats
    instance.stats.invalidate()

    # Do not delete linked components
    if not instance.is_repo_link:
        delete_object_dir(instance)


@receiver(post_save, sender=Unit)
@disable_for_loaddata
def update_source(sender, instance, **kwargs):
    """Update unit priority or checks based on source change."""
    if not instance.translation.is_source:
        return
    # We can not exclude current unit here as we need to trigger the updates below
    units = Unit.objects.filter(
        translation__component=instance.translation.component, id_hash=instance.id_hash
    )
    # Propagate attributes
    units.exclude(extra_context=instance.extra_context).update(
        extra_context=instance.extra_context
    )
    units.exclude(extra_flags=instance.extra_flags).update(
        extra_flags=instance.extra_flags
    )
    # Run checks, update state and priority if flags changed
    if (
        instance.old_unit.extra_flags != instance.extra_flags
        or instance.state != instance.old_unit.state
    ):
        for unit in units:
            unit.update_state()
            unit.update_priority()
            unit.run_checks()
            unit.translation.invalidate_cache()


@receiver(m2m_changed, sender=Unit.labels.through)
@disable_for_loaddata
def change_labels(sender, instance, **kwargs):
    """Update unit labels."""
    if not instance.translation.is_source:
        return
    units = Unit.objects.filter(
        translation__component=instance.translation.component, id_hash=instance.id_hash
    ).exclude(pk=instance.pk)

    # Force fetching labels
    labels = instance.labels.all()
    list(labels)

    for unit in units.prefetch():
        # This emulates set in ManyRelatedManager, we just need to know if there was
        # any change to effectively invalidate caches
        old_labels = set(unit.labels.all())
        new_labels = []
        for label in labels:
            if label in old_labels:
                old_labels.remove(label)
            else:
                new_labels.append(label)

        if old_labels:
            unit.labels.remove(*old_labels)
        if new_labels:
            unit.labels.add(*new_labels)
        if old_labels or new_labels:
            unit.translation.invalidate_cache()


@receiver(post_delete, sender=Comment)
@receiver(post_save, sender=Comment)
@disable_for_loaddata
def update_comment_flag(sender, instance, **kwargs):
    """Update related unit comment flags."""
    # Update unit stats
    try:
        if instance.unit.update_has_comment():
            instance.unit.translation.invalidate_cache()
    except Unit.DoesNotExist:
        pass


@receiver(post_delete, sender=Suggestion)
@receiver(post_save, sender=Suggestion)
@disable_for_loaddata
def update_suggestion_flag(sender, instance, **kwargs):
    """Update related unit suggestion flags."""
    # Update unit stats
    try:
        if instance.unit.update_has_suggestion():
            instance.unit.translation.invalidate_cache()
    except Unit.DoesNotExist:
        pass


@receiver(user_pre_delete)
def user_commit_pending(sender, instance, **kwargs):
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
def change_componentlist(sender, instance, **kwargs):
    instance.stats.invalidate()


@receiver(post_save, sender=AutoComponentList)
@disable_for_loaddata
def auto_componentlist(sender, instance, **kwargs):
    for component in Component.objects.iterator():
        instance.check_match(component)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def auto_project_componentlist(sender, instance, **kwargs):
    for component in instance.component_set.iterator():
        auto_component_list(sender, component)


@receiver(post_save, sender=Component)
@disable_for_loaddata
def auto_component_list(sender, instance, **kwargs):
    for auto in AutoComponentList.objects.iterator():
        auto.check_match(instance)


@receiver(post_save, sender=Component)
@disable_for_loaddata
def post_save_update_checks(sender, instance, **kwargs):
    from weblate.trans.tasks import update_checks

    if instance.old_component.check_flags == instance.check_flags:
        return
    update_checks.delay(instance.pk)


@receiver(post_delete, sender=Component)
@disable_for_loaddata
def post_delete_linked(sender, instance, **kwargs):
    # When removing project, the linked component might be already deleted now
    try:
        if instance.linked_component:
            instance.linked_component.update_alerts()
    except Component.DoesNotExist:
        pass
