# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import os
import shutil

from django.db.models.signals import post_delete, post_save, m2m_changed
from django.dispatch import receiver

from weblate.trans.models.conf import WeblateConf
from weblate.trans.models.project import Project
from weblate.trans.models.component import Component
from weblate.trans.models.translation import Translation
from weblate.trans.models.unit import Unit
from weblate.trans.models.comment import Comment
from weblate.trans.models.suggestion import Suggestion, Vote
from weblate.trans.models.search import IndexUpdate
from weblate.trans.models.change import Change
from weblate.trans.models.dictionary import Dictionary
from weblate.trans.models.source import Source
from weblate.trans.models.whiteboard import WhiteboardMessage
from weblate.trans.models.componentlist import (
    ComponentList, AutoComponentList,
)
from weblate.trans.signals import (
    vcs_post_push, vcs_post_update, vcs_pre_commit, vcs_post_commit,
    user_pre_delete, translation_post_add,
)
from weblate.trans.scripts import (
    run_post_push_script, run_post_update_script, run_pre_commit_script,
    run_post_commit_script, run_post_add_script,
)
from weblate.utils.decorators import disable_for_loaddata

__all__ = [
    'Project', 'Component', 'Translation', 'Unit', 'Suggestion',
    'Comment', 'Vote', 'IndexUpdate', 'Change', 'Dictionary', 'Source',
    'WhiteboardMessage', 'ComponentList',
    'WeblateConf',
]


@receiver(post_delete, sender=Project)
@receiver(post_delete, sender=Component)
def delete_object_dir(sender, instance, **kwargs):
    """Handler to delete (sub)project directory on project deletion."""
    # Do not delete linked components
    if hasattr(instance, 'is_repo_link') and instance.is_repo_link:
        return

    project_path = instance.full_path

    # Remove path if it exists
    if os.path.exists(project_path):
        shutil.rmtree(project_path)


@receiver(post_save, sender=Source)
@disable_for_loaddata
def update_source(sender, instance, **kwargs):
    """Update unit priority or checks based on source change."""
    related_units = Unit.objects.filter(
        id_hash=instance.id_hash,
        translation__component=instance.component,
    )
    if instance.priority_modified:
        units = related_units.exclude(
            priority=instance.priority
        )
        units.update(priority=instance.priority)

    if instance.check_flags_modified:
        for unit in related_units:
            unit.run_checks()
            unit.translation.invalidate_cache()


@receiver(post_delete, sender=Comment)
@receiver(post_save, sender=Comment)
@disable_for_loaddata
def update_comment_flag(sender, instance, **kwargs):
    """Update related unit comment flags"""
    for unit in instance.related_units:
        # Update unit stats
        unit.update_has_comment()
        unit.translation.invalidate_cache()


@receiver(post_delete, sender=Suggestion)
@receiver(post_save, sender=Suggestion)
@disable_for_loaddata
def update_suggestion_flag(sender, instance, **kwargs):
    """Update related unit suggestion flags"""
    for unit in instance.related_units:
        # Update unit stats
        unit.update_has_suggestion()
        unit.translation.invalidate_cache()


@receiver(vcs_post_push)
def post_push(sender, component, **kwargs):
    run_post_push_script(component)


@receiver(vcs_post_update)
def post_update(sender, component, previous_head, **kwargs):
    run_post_update_script(component, previous_head)


@receiver(vcs_pre_commit)
def pre_commit(sender, translation, **kwargs):
    run_pre_commit_script(
        translation.component, translation, translation.get_filename()
    )


@receiver(vcs_post_commit)
def post_commit(sender, translation, **kwargs):
    run_post_commit_script(
        translation.component, translation, translation.get_filename()
    )


@receiver(translation_post_add)
def post_add(sender, translation, **kwargs):
    run_post_add_script(
        translation.component, translation, translation.get_filename()
    )


@receiver(user_pre_delete)
def user_commit_pending(sender, instance, **kwargs):
    """Commit pending changes for user on account removal."""
    # All user changes
    all_changes = Change.objects.last_changes(instance).filter(
        user=instance,
    )

    # Filter where project is active
    user_translation_ids = all_changes.values_list(
        'translation', flat=True
    ).distinct()

    # Commit changes where user is last author
    for translation in Translation.objects.filter(pk__in=user_translation_ids):
        try:
            last_author = translation.change_set.content()[0].author
        except IndexError:
            # Non content changes
            continue
        if last_author == instance:
            translation.commit_pending(None)


@receiver(m2m_changed, sender=ComponentList.components.through)
def change_componentlist(sender, instance, **kwargs):
    instance.stats.invalidate()


@receiver(post_save, sender=AutoComponentList)
@disable_for_loaddata
def auto_componentlist(sender, instance, **kwargs):
    for component in Component.objects.all():
        instance.check_match(component)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def auto_project_componentlist(sender, instance, **kwargs):
    for component in instance.component_set.all():
        auto_component_list(sender, component)


@receiver(post_save, sender=Component)
@disable_for_loaddata
def auto_component_list(sender, instance, **kwargs):
    for auto in AutoComponentList.objects.all():
        auto.check_match(instance)
