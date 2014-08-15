# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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

__all__ = [
    'Project', 'SubProject', 'Translation', 'Unit', 'Check', 'Suggestion',
    'Comment', 'Vote', 'IndexUpdate', 'Change', 'Dictionary', 'Source',
    'Advertisement', 'WhiteboardMessage',
]

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
def update_string_pririties(sender, instance, **kwargs):
    """
    Updates unit score
    """
    if instance.priority_modified:
        units = Unit.objects.filter(
            checksum=instance.checksum
        ).exclude(
            priority=instance.priority
        )
        units.update(priority=instance.priority)


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
    return related_units


@receiver(post_save, sender=Check)
def update_failed_check(sender, instance, **kwargs):
    """
    Update related unit failed check flag.
    """
    if instance.ignore:
        for unit in get_related_units(instance):
            unit.update_has_failing_check(False)
