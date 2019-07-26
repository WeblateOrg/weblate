# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

import json
from zipfile import BadZipfile

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.forms import HiddenInput
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.http import urlencode
from django.utils.translation import ugettext as _
from django.views.generic.edit import CreateView

from weblate.trans.forms import (
    ComponentBranchForm,
    ComponentCreateForm,
    ComponentDiscoverForm,
    ComponentInitCreateForm,
    ComponentSelectForm,
    ComponentZipCreateForm,
    ProjectCreateForm,
)
from weblate.trans.models import Change, Component, Project
from weblate.vcs.git import LocalRepository
from weblate.vcs.models import VCS_REGISTRY


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
        Change.objects.create(
            action=Change.ACTION_CREATE_PROJECT,
            project=self.object,
            user=self.request.user,
            author=self.request.user,
        )
        return result

    def can_create(self):
        return (
            (self.has_billing and self.billings) or self.request.user.is_superuser
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
    selected_project = ''
    basic_fields = ('repo', 'name', 'slug', 'vcs')
    empty_form = False
    form_class = ComponentInitCreateForm

    def get_form_class(self):
        """Return the form class to use."""
        if self.stage == 'create':
            return ComponentCreateForm
        if self.stage == 'discover':
            return ComponentDiscoverForm
        return self.form_class

    def get_form_kwargs(self):
        if not self.initial and not self.empty_form:
            return super(CreateComponent, self).get_form_kwargs()

        result = {'initial': self.initial, 'request': self.request}
        if self.has_all_fields() and not self.empty_form:
            result['data'] = self.request.GET
        return result

    def get_success_url(self):
        return reverse(
            'component_progress',
            kwargs=self.object.get_reverse_url_kwargs()
        )

    def form_valid(self, form):
        if self.stage == 'create':
            result = super(CreateComponent, self).form_valid(form)
            Change.objects.create(
                action=Change.ACTION_CREATE_COMPONENT,
                component=self.object,
                user=self.request.user,
                author=self.request.user,
            )
            return result
        if self.stage == 'discover':
            # Move to create
            self.initial = form.cleaned_data
            self.stage = 'create'
            return self.get(self, self.request)
        # Move to discover
        self.stage = 'discover'
        self.initial = form.cleaned_data
        return self.get(self, self.request)

    def get_form(self, form_class=None, empty=False):
        self.empty_form = empty
        form = super(CreateComponent, self).get_form(form_class)
        if 'project' in form.fields:
            project_field = form.fields['project']
            project_field.queryset = self.projects
            project_field.empty_label = None
            if self.selected_project:
                project_field.initial = self.selected_project
        self.empty_form = False
        return form

    def get_context_data(self, **kwargs):
        kwargs = super(CreateComponent, self).get_context_data(**kwargs)
        kwargs['projects'] = self.projects
        kwargs['stage'] = self.stage
        return kwargs

    def fetch_params(self, request):
        try:
            self.selected_project = int(
                request.POST.get('project', request.GET.get('project', ''))
            )
        except ValueError:
            self.selected_project = ''
        if request.user.is_superuser:
            self.projects = Project.objects.order()
        elif self.has_billing:
            from weblate.billing.models import Billing
            self.projects = request.user.owned_projects.filter(
                billing__in=Billing.objects.get_valid()
            ).order()
        else:
            self.projects = request.user.owned_projects
        self.initial = {}
        for field in self.basic_fields:
            if field in request.GET:
                self.initial[field] = request.GET[field]

    def has_all_fields(self):
        return (
            self.stage == 'init'
            and all(field in self.request.GET for field in self.basic_fields)
        )

    def dispatch(self, request, *args, **kwargs):
        if 'filemask' in request.POST:
            self.stage = 'create'
        elif 'discovery' in request.POST:
            self.stage = 'discover'
        else:
            self.stage = 'init'

        self.fetch_params(request)

        # Proceed to post if all params are present
        if self.has_all_fields():
            return self.post(request, *args, **kwargs)

        return super(CreateComponent, self).dispatch(request, *args, **kwargs)


class CreateFromZip(CreateComponent):
    form_class = ComponentZipCreateForm

    def form_valid(self, form):
        if self.stage != 'init':
            return super(CreateFromZip, self).form_valid(form)

        # Create fake component (needed to calculate path)
        fake = Component(
            project=form.cleaned_data['project'],
            slug=form.cleaned_data['slug'],
            name=form.cleaned_data['name'],
        )

        # Create repository
        try:
            LocalRepository.from_zip(fake.full_path, form.cleaned_data['zipfile'])
        except BadZipfile:
            form.add_error('zipfile', _('Failed to parse uploaded ZIP file.'))
            return self.form_invalid(form)

        # Move to discover phase
        self.stage = 'discover'
        self.initial = form.cleaned_data
        self.initial['vcs'] = 'local'
        self.initial['repo'] = 'local:'
        self.initial.pop('zipfile')
        return self.get(self, self.request)


class CreateComponentSelection(CreateComponent):
    template_name = 'trans/component_create.html'

    components = None
    origin = None

    @cached_property
    def branch_data(self):
        def branch_exists(repo, branch):
            return Component.objects.filter(repo=repo, branch=branch).exists()

        result = {}
        for component in self.components:
            repo = component.repo
            branches = [
                branch for branch in component.repository.list_remote_branches()
                if branch != component.branch and not branch_exists(repo, branch)
            ]
            if branches:
                result[component.pk] = branches
        return result

    def fetch_params(self, request):
        super(CreateComponentSelection, self).fetch_params(request)
        self.components = Component.objects.with_repo().filter(
            project__in=self.projects
        )
        if self.selected_project:
            self.components = self.components.filter(project__pk=self.selected_project)
        self.origin = request.POST.get('origin')

    def get_context_data(self, **kwargs):
        kwargs = super(CreateComponentSelection, self).get_context_data(**kwargs)
        kwargs['components'] = self.components
        kwargs['selected_project'] = self.selected_project
        if self.origin == 'branch':
            kwargs['branch_form'] = kwargs['form']
            kwargs['existing_form'] = self.get_form(ComponentSelectForm, empty=True)
        else:
            kwargs['existing_form'] = kwargs['form']
            kwargs['branch_form'] = self.get_form(ComponentBranchForm, empty=True)
        kwargs['branch_data'] = json.dumps(self.branch_data)
        kwargs['full_form'] = self.get_form(ComponentInitCreateForm, empty=True)
        if 'local' in VCS_REGISTRY:
            kwargs['zip_form'] = self.get_form(ComponentZipCreateForm, empty=True)
        return kwargs

    def get_form(self, form_class=None, empty=False):
        form = super(CreateComponentSelection, self).get_form(form_class, empty=empty)
        if isinstance(form, ComponentBranchForm):
            form.fields['component'].queryset = Component.objects.filter(
                pk__in=self.branch_data.keys()
            )
            form.branch_data = self.branch_data
            form.auto_id = "id_branch_%s"
        elif isinstance(form, ComponentSelectForm):
            form.fields['component'].queryset = self.components
            form.auto_id = "id_existing_%s"
        return form

    def get_form_class(self):
        if self.origin == 'branch':
            return ComponentBranchForm
        return ComponentSelectForm

    def redirect_create(self, **kwargs):
        return redirect(
            '{}?{}'.format(reverse('create-component-vcs'), urlencode(kwargs))
        )

    def form_valid(self, form):
        component = form.cleaned_data['component']
        if self.origin == 'existing':
            return self.redirect_create(
                repo=component.get_repo_link_url(),
                project=component.project.pk,
                name=form.cleaned_data['name'],
                slug=form.cleaned_data['slug'],
                vcs=component.vcs,
            )
        if self.origin == 'branch':
            form.instance.save()
            return redirect(reverse(
                'component_progress',
                kwargs=form.instance.get_reverse_url_kwargs()
            ))

        return redirect('create-component')

    def post(self, request, *args, **kwargs):
        if self.origin == 'vcs':
            kwargs = {}
            if self.selected_project:
                kwargs['project'] = self.selected_project
            return self.redirect_create(**kwargs)
        return super(CreateComponentSelection, self).post(request, *args, **kwargs)
