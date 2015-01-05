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
'''
Helper methods for views.
'''

from weblate.trans.models import Project, SubProject, Translation
from weblate.lang.models import Language
from django.shortcuts import get_object_or_404
import django.utils.translation


def get_translation(request, project, subproject, lang, skip_acl=False):
    '''
    Returns translation matching parameters.
    '''
    translation = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    if not skip_acl:
        translation.check_acl(request)
    return translation


def get_subproject(request, project, subproject, skip_acl=False):
    '''
    Returns subproject matching parameters.
    '''
    subproject = get_object_or_404(
        SubProject,
        project__slug=project,
        slug=subproject
    )
    if not skip_acl:
        subproject.check_acl(request)
    return subproject


def get_project(request, project, skip_acl=False):
    '''
    Returns project matching parameters.
    '''
    project = get_object_or_404(
        Project,
        slug=project,
    )
    if not skip_acl:
        project.check_acl(request)
    return project


def get_project_translation(request, project=None, subproject=None, lang=None):
    '''
    Returns project, subproject, translation tuple for given parameters.
    '''

    if lang is not None and subproject is not None:
        # Language defined? We can get all
        translation = get_translation(request, project, subproject, lang)
        subproject = translation.subproject
        project = subproject.project
    else:
        translation = None
        if subproject is not None:
            # Component defined?
            subproject = get_subproject(request, project, subproject)
            project = subproject.project
        elif project is not None:
            # Only project defined?
            project = get_project(request, project)

    # Return tuple
    return project, subproject, translation


def try_set_language(lang):
    '''
    Tries to activate language, returns matching Language object.
    '''

    try:
        django.utils.translation.activate(lang)
    except Exception:
        # Ignore failure on activating language
        pass
    try:
        return Language.objects.get(code=lang)
    except Language.DoesNotExist:
        return None
