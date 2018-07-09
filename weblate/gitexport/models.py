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

from django.urls import reverse
from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save

from weblate.trans.models import Component, Project
from weblate.utils.site import get_site_url
from weblate.utils.decorators import disable_for_loaddata


SUPPORTED_VCS = frozenset(('git', 'gerrit', 'github', 'subversion'))


def get_export_url(component):
    """Return Git export URL for component"""
    return get_site_url(
        reverse(
            'git-export',
            kwargs={
                'project': component.project.slug,
                'component': component.slug,
                'path': '',
            }
        )
    )


@receiver(pre_save, sender=Component)
def save_component(sender, instance, **kwargs):
    if not instance.is_repo_link and instance.vcs in SUPPORTED_VCS:
        instance.git_export = get_export_url(instance)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def save_project(sender, instance, **kwargs):
    for component in instance.component_set.all():
        if not component.is_repo_link and component.vcs in SUPPORTED_VCS:
            new_url = get_export_url(component)
            if component.git_export != new_url:
                component.git_export = new_url
                component.save(update_fields=['git_export'])
