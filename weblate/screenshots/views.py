# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView
from django.shortcuts import render, get_object_or_404, redirect

from weblate.screenshots.forms import ScreenshotForm
from weblate.screenshots.models import Screenshot
from weblate.trans.models import Source
from weblate.trans.views.helper import get_subproject
from weblate.trans.permissions import (
    can_delete_screenshot, can_add_screenshot, can_change_screenshot,
)
from weblate.utils import messages


class ScreenshotList(ListView):
    paginate_by = 25
    model = Screenshot
    _add_form = None

    def get_component(self, kwargs):
        return get_subproject(
            self.request,
            kwargs['project'],
            kwargs['subproject']
        )

    def get_queryset(self):
        self.kwargs['component'] = self.get_component(self.kwargs)
        return Screenshot.objects.filter(component=self.kwargs['component'])

    def get_context_data(self):
        result = super(ScreenshotList, self).get_context_data()
        component = self.kwargs['component']
        result['object'] = component
        if can_add_screenshot(self.request.user, component.project):
            if self._add_form is not None:
                result['add_form'] = self._add_form
            else:
                result['add_form'] = ScreenshotForm()
        return result

    def post(self, request, **kwargs):
        component = self.get_component(kwargs)
        if not can_add_screenshot(request.user, component.project):
            raise PermissionDenied()
        self._add_form = ScreenshotForm(request.POST, request.FILES)
        if self._add_form.is_valid():
            obj = Screenshot.objects.create(
                component=component,
                **self._add_form.cleaned_data
            )
            if 'source' in request.POST and request.POST['source'].isdigit():
                try:
                    source = Source.objects.get(pk=request.POST['source'])
                    if source.subproject == component:
                        obj.sources.add(source)
                except Source.DoesNotExist:
                    pass
            messages.success(
                request,
                _('Uploaded screenshot, you can now assign it to source strings.')
            )
            return redirect(obj)
        else:
            messages.error(
                request,
                _('Failed to upload screenshot, please fix errors below.')
            )
            return self.get(request, **kwargs)


class ScreenshotDetail(DetailView):
    model = Screenshot

    def get_object(self):
        obj = super(ScreenshotDetail, self).get_object()
        obj.component.check_acl(self.request)
        return obj


@require_POST
@login_required
def delete_screenshot(request, pk):
    obj = get_object_or_404(Screenshot, pk=pk)
    obj.component.check_acl(request)
    if not can_delete_screenshot(request.user, obj.component.project):
        raise PermissionDenied()

    kwargs = {
        'project': obj.component.project.slug,
        'subproject': obj.component.slug,
    }

    obj.delete()

    messages.success(request, _('Screenshot %s has been deleted.') % obj.name)

    return redirect('screenshots', **kwargs)


@require_POST
@login_required
def remove_source(request, pk):
    obj = get_object_or_404(Screenshot, pk=pk)
    obj.component.check_acl(request)
    if not can_change_screenshot(request.user, obj.component.project):
        raise PermissionDenied()

    obj.sources.remove(request.POST['source'])

    messages.success(request, _('Source has been removed.'))

    return redirect(obj)
