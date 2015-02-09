# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import shutil

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from weblate.trans.models.project import Project
from weblate.trans.models.subproject import SubProject
from weblate.trans.models.translation import Translation
from weblate.trans.models.unit import Unit
from weblate.trans.models.unitdata import (
    Check, Suggestion, Comment, Vote
)
from weblate.trans.models.search import IndexUpdate
from weblate.trans.models.changes import Change
from weblate.trans.models.dictionary import Dictionary
from weblate.trans.models.source import Source
from weblate.trans.models.advertisement import Advertisement
from weblate.trans.models.whiteboard import WhiteboardMessage

__all__ = [
    'Project', 'SubProject', 'Translation', 'Unit', 'Check', 'Suggestion',
    'Comment', 'Vote', 'IndexUpdate', 'Change', 'Dictionary', 'Source',
    'Advertisement', 'WhiteboardMessage',
]


@receiver(post_delete, sender=Project)
@receiver(post_delete, sender=SubProject)
def delete_object_dir(sender, instance, **kwargs):
    """
    Handler to delete (sub)project directory on project deletion.
    """
    # Do not delete linked subprojects
    if hasattr(instance, 'is_repo_link') and instance.is_repo_link:
        return

    project_path = instance.get_path()

    # Remove path if it exists
    if os.path.exists(project_path):
        shutil.rmtree(project_path)


@receiver(post_save, sender=Source)
def update_source(sender, instance, **kwargs):
    """
    Updates unit priority or checks based on source change.
    """
    related_units = Unit.objects.filter(
        checksum=instance.checksum,
        translation__subproject=instance.subproject,
    )
    if instance.priority_modified:
        units = related_units.exclude(
            priority=instance.priority
        )
        units.update(priority=instance.priority)

    if instance.check_flags_modified:
        for unit in related_units:
            unit.run_checks()


def get_related_units(unitdata):
    '''
    Returns queryset with related units.
    '''
    related_units = Unit.objects.filter(
        contentsum=unitdata.contentsum,
        translation__subproject__project=unitdata.project,
    )
    if unitdata.language is not None:
        related_units = related_units.filter(
            translation__language=unitdata.language
        )

    return related_units.select_related(
        'translation__subproject__project',
        'translation__language'
    )


@receiver(post_save, sender=Check)
def update_failed_check_flag(sender, instance, **kwargs):
    """
    Update related unit failed check flag.
    """
    if instance.language is None:
        return
    related = get_related_units(instance)
    if instance.for_unit is not None:
        related = related.exclude(pk=instance.for_unit)
    for unit in related:
        unit.update_has_failing_check(False)


@receiver(post_delete, sender=Comment)
@receiver(post_save, sender=Comment)
def update_comment_flag(sender, instance, **kwargs):
    """
    Update related unit comment flags
    """
    for unit in get_related_units(instance):
        # Update unit stats
        unit.update_has_comment()

        # Invalidate counts cache
        if instance.language is None:
            unit.translation.invalidate_cache('sourcecomments')


@receiver(post_delete, sender=Suggestion)
@receiver(post_save, sender=Suggestion)
def update_suggestion_flag(sender, instance, **kwargs):
    """
    Update related unit suggestion flags
    """
    for unit in get_related_units(instance):
        # Update unit stats
        unit.update_has_suggestion()


@receiver(post_delete, sender=Unit)
def cleanup_deleted(sender, instance, **kwargs):
    '''
    Removes stale checks/comments/suggestions for deleted units.
    '''
    project = instance.translation.subproject.project
    language = instance.translation.language
    contentsum = instance.translation
    units = Unit.objects.filter(
        translation__language=language,
        translation__subproject__project=project,
        contentsum=contentsum
    )
    if units.exists():
        # There are other units as well, but some checks
        # (eg. consistency) needs update now
        for unit in units:
            unit.run_checks()
        return

    # Last unit referencing to these checks
    Check.objects.filter(
        project=project,
        language=language,
        contentsum=contentsum
    ).delete()
    # Delete suggestons referencing this unit
    Suggestion.objects.filter(
        project=project,
        language=language,
        contentsum=contentsum
    ).delete()
    # Delete translation comments referencing this unit
    Comment.objects.filter(
        project=project,
        language=language,
        contentsum=contentsum
    ).delete()
    # Check for other units with same source
    other_units = Unit.objects.filter(
        translation__subproject__project=project,
        contentsum=contentsum
    )
    if not other_units.exists():
        # Delete source comments as well if this was last reference
        Comment.objects.filter(
            project=project,
            language=None,
            contentsum=contentsum
        ).delete()
        # Delete source checks as well if this was last reference
        Check.objects.filter(
            project=project,
            language=None,
            contentsum=contentsum
        ).delete()
