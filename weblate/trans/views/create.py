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

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.forms import HiddenInput
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
from django.views.generic.edit import CreateView
from django.utils.text import slugify

from weblate.trans.forms import (
    ProjectCreateForm, ComponentCreateForm, ComponentInitCreateForm,
    ComponentDiscoverForm,
)
from weblate.trans.models import Project, Component


class BaseCreateView(CreateView):
    def __init__(self, **kwargs):
        super(BaseCreateView, self).__init__(**kwargs)
        self.has_billing = 'weblate.billing' in settings.INSTALLED_APPS

    def get_form_kwargs(self):
        kwargs = super(BaseCreateView, self).get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs


@method_decorator(login_required, name='dispatch')
class CreateProject(BaseCreateView):
    model = Project
    form_class = ProjectCreateForm
    billings = None

    def get_form(self, form_class=None):
        form = super(CreateProject, self).get_form(form_class)
        billing_field = form.fields['billing']
        if self.has_billing:
            billing_field.queryset = self.billings
            try:
                billing_field.initial = int(self.request.GET['billing'])
            except (ValueError, KeyError):
                pass
            billing_field.required = (
                not self.request.user.is_superuser
            )
            if self.request.user.is_superuser:
                billing_field.empty_label = '-- without billing --'
        else:
            billing_field.required = False
            billing_field.widget = HiddenInput()
        return form

    def form_valid(self, form):
        result = super(CreateProject, self).form_valid(form)
        if self.has_billing and form.cleaned_data['billing']:
            form.cleaned_data['billing'].projects.add(self.object)
            self.object.access_control = Project.ACCESS_PRIVATE
            self.object.save()
        if not self.request.user.is_superuser:
            self.object.add_user(self.request.user, '@Administration')
        return result

    def can_create(self):
        return (
            (self.has_billing and self.billings) or
            self.request.user.is_superuser
        )

    def post(self, request, *args, **kwargs):
        if not self.can_create():
            return redirect('create-project')
        return super(CreateProject, self).post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs = super(CreateProject, self).get_context_data(**kwargs)
        kwargs['can_create'] = self.can_create()
        if self.has_billing:
            from weblate.billing.models import Billing
            kwargs['user_billings'] = Billing.objects.for_user(
                self.request.user
            ).exists()
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        if self.has_billing:
            from weblate.billing.models import Billing
            billings = Billing.objects.get_valid().for_user(request.user)
            pks = set()
            for billing in billings:
                limit = billing.plan.display_limit_projects
                if limit == 0 or billing.count_projects() < limit:
                    pks.add(billing.pk)
            self.billings = Billing.objects.filter(pk__in=pks)
        return super(CreateProject, self).dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class CreateComponent(BaseCreateView):
    model = Component
    projects = None
    stage = None

    def get_form_class(self):
        """Return the form class to use."""
        if self.stage == 'create':
            return ComponentCreateForm
        elif self.stage == 'discover':
            return ComponentDiscoverForm
        return ComponentInitCreateForm

    def get_form_kwargs(self):
        if not self.initial:
            return super(CreateComponent, self).get_form_kwargs()
        return {'initial': self.initial, 'request': self.request}

    def form_valid(self, form):
        if self.stage == 'create':
            return super(CreateComponent, self).form_valid(form)
        elif self.stage == 'discover':
            # Move to create
            self.initial = form.cleaned_data
            self.stage = 'create'
            return self.get(self, self.request)
        # Move to discover
        self.stage = 'discover'
        self.initial = form.cleaned_data
        return self.get(self, self.request)

    def get_form(self, form_class=None):
        form = super(CreateComponent, self).get_form(form_class)
        project_field = form.fields['project']
        project_field.queryset = self.projects
        project_field.empty_label = None
        try:
            project_field.initial = int(self.request.GET['project'])
        except (ValueError, KeyError):
            pass
        return form

    def get_context_data(self, **kwargs):
        kwargs = super(CreateComponent, self).get_context_data(**kwargs)
        kwargs['projects'] = self.projects
        kwargs['stage'] = self.stage
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        if 'filemask' in request.POST:
            self.stage = 'create'
        elif 'discovery' in request.POST:
            self.stage = 'discover'
        else:
            self.stage = 'init'
        if self.request.user.is_superuser:
            self.projects = Project.objects.all()
        elif self.has_billing:
            from weblate.billing.models import Billing
            self.projects = request.user.owned_projects.filter(
                billing__in=Billing.objects.get_valid()
            )
        else:
            self.projects = request.user.owned_projects

        return super(CreateComponent, self).dispatch(request, *args, **kwargs)
