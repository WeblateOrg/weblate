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

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.translation import ugettext as _
from django.views.generic import ListView, UpdateView

from weblate.addons.models import Addon, ADDONS
from weblate.permissions.helpers import can_edit_subproject
from weblate.utils import messages
from weblate.utils.views import ComponentViewMixin


class AddonViewMixin(ComponentViewMixin):
    def get_queryset(self):
        component = self.get_component()
        if not can_edit_subproject(self.request.user, component.project):
            raise PermissionDenied('Can not edit component')
        self.kwargs['component'] = component
        return Addon.objects.filter(component=component)

    def redirect_list(self, message=None):
        if message:
            messages.error(self.request, message)
        component = self.get_component()
        return redirect(
            'addons',
            project=component.project.slug,
            subproject=component.slug
        )


class AddonList(AddonViewMixin, ListView):
    paginate_by = None
    model = Addon
    _add_form = None

    def get_context_data(self):
        result = super(AddonList, self).get_context_data()
        component = self.kwargs['component']
        result['object'] = component
        installed = set([x.addon.name for x in result['object_list']])
        result['available'] = [
            {
                'verbose': x.verbose,
                'description': x.description,
                'name': x.name,
                'icon': x.icon,
            }
            for x in ADDONS.values()
            if x.is_compatible(component) and x.name not in installed
        ]
        return result

    def post(self, request, **kwargs):
        component = self.get_component()
        name = request.POST.get('name')
        addon = ADDONS.get(name)
        if not name or addon is None or not addon.is_compatible(component):
            return self.redirect_list(_('Attempt to install invalid addon!'))
        installed = set([x.addon.name for x in self.get_queryset()])
        if name in installed:
            return self.redirect_list(_('Addon is already installed!'))

        form = None
        if not addon.settings_form:
            addon.create(component)
            return self.redirect_list()
        elif 'form' in request.POST:
            form = addon.get_add_form(component, request.POST)
            if form.is_valid():
                form.save()
                return self.redirect_list()
        else:
            form = addon.get_add_form(component)
        return RENDER(form)


class AddonDetail(AddonViewMixin, UpdateView):
    model = Addon

    def get_context_data(self, **kwargs):
        result = super(AddonDetail, self).get_context_data(**kwargs)
        component = result['object'].component
        if can_change_screenshot(self.request.user, component.project):
            if self._edit_form is not None:
                result['edit_form'] = self._edit_form
            else:
                result['edit_form'] = ScreenshotForm(instance=result['object'])
        return result

    def post(self, request, **kwargs):
        obj = self.get_object()
        if 'delete' in request.POST:
            obj.delete()
            return self.redirect_list()
        if can_change_screenshot(request.user, obj.component.project):
            self._edit_form = ScreenshotForm(
                request.POST, request.FILES, instance=obj
            )
            if self._edit_form.is_valid():
                self._edit_form.save()
            else:
                return self.get(request, **kwargs)
        return redirect(obj)
