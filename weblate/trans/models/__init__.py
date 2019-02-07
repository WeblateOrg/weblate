# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from weblate.celery import app
from weblate.trans.models.alert import Alert
from weblate.trans.models.agreement import ContributorAgreement
from weblate.trans.models.conf import WeblateConf
from weblate.trans.models.project import Project
from weblate.trans.models.component import Component
from weblate.trans.models.translation import Translation
from weblate.trans.models.unit import Unit
from weblate.trans.models.comment import Comment
from weblate.trans.models.suggestion import Suggestion, Vote
from weblate.trans.models.change import Change
from weblate.trans.models.dictionary import Dictionary
from weblate.trans.models.source import Source
from weblate.trans.models.whiteboard import WhiteboardMessage
from weblate.trans.models.componentlist import (
    ComponentList, AutoComponentList,
)
from weblate.trans.signals import user_pre_delete
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.files import remove_readonly

__all__ = [
    'Project', 'Component', 'Translation', 'Unit', 'Suggestion',
    'Comment', 'Vote', 'Change', 'Dictionary', 'Source',
    'WhiteboardMessage', 'ComponentList',
    'WeblateConf', 'ContributorAgreement',
    'Alert',
]


@receiver(post_delete, sender=Project)
def delete_object_dir(sender, instance, **kwargs):
    """Handler to delete (sub)project directory on project deletion."""
    project_path = instance.full_path

    # Remove path if it exists
    if os.path.exists(project_path):
        shutil.rmtree(project_path, onerror=remove_readonly)


@receiver(post_delete, sender=Component)
def delete_component(sender, instance, **kwargs):
    """Handler to delete (sub)project directory on project deletion."""
    from weblate.trans.tasks import cleanup_project
    cleanup_project.delay(instance.project.pk)

    # Do not delete linked components
    if not instance.is_repo_link:
        delete_object_dir(sender, instance, **kwargs)


@receiver(post_save, sender=Source)
@disable_for_loaddata
def update_source(sender, instance, **kwargs):
    """Update unit priority or checks based on source change."""
    if instance.priority_modified:
        Unit.objects.filter(
            id_hash=instance.id_hash,
            translation__component=instance.component,
        ).exclude(
            priority=instance.priority
        ).update(priority=instance.priority)

    if instance.check_flags_modified:
        for unit in instance.units:
            unit.run_checks()
        instance.run_checks()
        for unit in instance.units:
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
            translation.commit_pending('user delete', None)


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


@receiver(post_save, sender=Component)
@disable_for_loaddata
def post_save_update_checks(sender, instance, **kwargs):
    if instance.old_component.check_flags == instance.check_flags:
        return
    update_checks.delay(instance.pk)


@app.task
def update_checks(pk):
    component = Component.objects.get(pk=pk)
    for translation in component.translation_set.all():
        for unit in translation.unit_set.all():
            unit.run_checks()
    for source in component.source_set.all():
        source.run_checks()
    for translation in component.translation_set.all():
        translation.invalidate_cache()
