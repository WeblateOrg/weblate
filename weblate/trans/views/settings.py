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

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.utils.translation import ugettext as _

from weblate.trans.forms import ComponentSettingsForm, ProjectSettingsForm
from weblate.trans.util import render
from weblate.utils.views import get_project, get_component
from weblate.utils import messages


@never_cache
@login_required
def change_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm('project.edit', obj):
        raise Http404()

    if request.method == 'POST':
        settings_form = ProjectSettingsForm(request, request.POST, instance=obj)
        if settings_form.is_valid():
            settings_form.save()
            messages.success(request, _('Settings saved'))
            return redirect('settings', project=obj.slug)
        else:
            messages.error(
                request,
                _('Invalid settings, please check the form for errors!')
            )
    else:
        settings_form = ProjectSettingsForm(request, instance=obj)

    return render(
        request,
        'project-settings.html',
        {
            'object': obj,
            'settings_form': settings_form,
        }
    )


@never_cache
@login_required
def change_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm('component.edit', obj):
        raise Http404()

    if request.method == 'POST':
        form = ComponentSettingsForm(request, request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, _('Settings saved'))
            return redirect(
                'settings', project=obj.project.slug, component=obj.slug
            )
        else:
            messages.error(
                request,
                _('Invalid settings, please check the form for errors!')
            )
    else:
        form = ComponentSettingsForm(request, instance=obj)

    return render(
        request,
        'component-settings.html',
        {
            'project': obj.project,
            'object': obj,
            'form': form,
        }
    )
