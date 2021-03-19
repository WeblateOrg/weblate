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
import os

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
from weblate.trans.models.label import Label
from weblate.trans.models.project import Project
from weblate.trans.models.suggestion import Suggestion, Vote
from weblate.trans.models.translation import Translation
from weblate.trans.models.unit import Unit
from weblate.trans.models.variant import Variant
from weblate.trans.signals import user_pre_delete
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.files import remove_tree

__all__ = [
    "Project",
    "Component",
    "Translation",
    "Unit",
    "Suggestion",
    "Comment",
    "Vote",
    "Change",
    "Announcement",
    "ComponentList",
    "WeblateConf",
    "ContributorAgreement",
    "Alert",
    "Variant",
    "Label",
]


def delete_object_dir(instance):
    """Remove path if it exists."""
    project_path = instance.full_path
    if os.path.exists(project_path):
        remove_tree(project_path)


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


@receiver(m2m_changed, sender=Unit.labels.through)
@disable_for_loaddata
def change_labels(sender, instance, action, pk_set, **kwargs):
    """Update unit labels."""
    if (
        action not in ("post_add", "post_remove", "post_clear")
        or (action != "post_clear" and not pk_set)
        or not instance.is_source
    ):
        return
    if not instance.is_batch_update:
        instance.translation.component.invalidate_cache()


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
def change_componentlist(sender, instance, action, **kwargs):
    if not action.startswith("post_"):
        return
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


@receiver(post_delete, sender=Component)
@disable_for_loaddata
def post_delete_linked(sender, instance, **kwargs):
    # When removing project, the linked component might be already deleted now
    try:
        if instance.linked_component:
            instance.linked_component.update_link_alerts(noupdate=True)
    except Component.DoesNotExist:
        pass


@receiver(post_save, sender=Comment)
@receiver(post_save, sender=Suggestion)
@receiver(post_delete, sender=Suggestion)
@disable_for_loaddata
def stats_invalidate(sender, instance, **kwargs):
    """Invalidate stats on new comment or suggestion."""
    # Invalidate stats counts
    instance.unit.translation.invalidate_cache()
    # Invalidate unit cached properties
    for key in ["all_comments", "suggestions"]:
        if key in instance.__dict__:
            del instance.__dict__[key]
