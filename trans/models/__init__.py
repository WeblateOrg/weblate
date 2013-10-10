# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from django.db.models.signals import post_delete
from django.dispatch import receiver

from trans.models.project import Project
from trans.models.subproject import SubProject
from trans.models.translation import Translation
from trans.models.unit import Unit
from trans.models.unitdata import (
    Check, Suggestion, Comment, IndexUpdate, Vote
)
from trans.models.changes import Change
from trans.models.dictionary import Dictionary
from trans.models.source import Source


@receiver(post_delete, sender=Project)
@receiver(post_delete, sender=SubProject)
def delete_object_dir(sender, instance, **kwargs):
    '''
    Handler to delete (sub)project directory on project deletion.
    '''
    # Do not delete linked subprojects
    if hasattr(instance, 'is_repo_link') and instance.is_repo_link():
        return

    project_path = instance.get_path()

    # Remove path if it exists
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
