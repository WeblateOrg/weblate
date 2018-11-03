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
from django.urls import reverse
from django.utils.translation import ugettext as _
from django.views.generic import ListView, UpdateView

from weblate.addons.models import Addon, ADDONS
from weblate.utils import messages
from weblate.utils.views import ComponentViewMixin


class AddonViewMixin(ComponentViewMixin):
    def get_queryset(self):
        component = self.get_component()
        if not self.request.user.has_perm('component.edit', component):
            raise PermissionDenied('Can not edit component')
        self.kwargs['component_obj'] = component
        return Addon.objects.filter_component(component)

    def get_success_url(self):
        component = self.get_component()
        return reverse(
            'addons',
            kwargs={
                'project': component.project.slug,
                'component': component.slug,
            }
        )

    def redirect_list(self, message=None):
        if message:
            messages.error(self.request, message)
        return redirect(self.get_success_url())


class AddonList(AddonViewMixin, ListView):
    paginate_by = None
    model = Addon

    def get_context_data(self, **kwargs):
        result = super(AddonList, self).get_context_data(**kwargs)
        component = self.kwargs['component_obj']
        result['object'] = component
        installed = set([x.addon.name for x in result['object_list']])
        result['available'] = sorted(
            [
                x for x in ADDONS.values()
                if x.can_install(component, self.request.user)
                and (x.multiple or x.name not in installed)
            ],
            key=lambda x:x.name
        )
        return result

    def post(self, request, **kwargs):
        component = self.get_component()
        name = request.POST.get('name')
        addon = ADDONS.get(name)
        installed = set([x.addon.name for x in self.get_queryset()])
        if (not name or
                addon is None or
                not addon.can_install(component, request.user) or
                (name in installed and not addon.multiple)):
            return self.redirect_list(_('Invalid addon name specified!'))

        form = None
        if addon.settings_form is None:
            addon.create(component)
            return self.redirect_list()
        elif 'form' in request.POST:
            form = addon.get_add_form(component, data=request.POST)
            if form.is_valid():
                form.save()
                return self.redirect_list()
        else:
            form = addon.get_add_form(component)
        return self.response_class(
            request=self.request,
            template=['addons/addon_detail.html'],
            context={
                'addon': addon,
                'form': form,
                'object': self.kwargs['component_obj'],
            },
        )


class AddonDetail(AddonViewMixin, UpdateView):
    model = Addon
    template_name_suffix = '_detail'

    def get_form(self, form_class=None):
        return self.object.addon.get_settings_form(
            **self.get_form_kwargs()
        )

    def get_context_data(self, **kwargs):
        result = super(AddonDetail, self).get_context_data(**kwargs)
        result['object'] = self.object.component
        result['instance'] = self.object
        result['addon'] = self.object.addon
        return result

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if 'delete' in request.POST:
            obj.delete()
            return self.redirect_list()
        return super(AddonDetail, self).post(request, *args, **kwargs)
