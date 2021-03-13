#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import json
import subprocess
from zipfile import BadZipfile

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.forms import HiddenInput
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.generic.edit import CreateView

from weblate.trans.forms import (
    ComponentBranchForm,
    ComponentCreateForm,
    ComponentDiscoverForm,
    ComponentDocCreateForm,
    ComponentInitCreateForm,
    ComponentScratchCreateForm,
    ComponentSelectForm,
    ComponentZipCreateForm,
    ProjectCreateForm,
)
from weblate.trans.models import Component, Project
from weblate.trans.tasks import perform_update
from weblate.trans.util import get_clean_env
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.licenses import LICENSE_URLS
from weblate.utils.views import create_component_from_doc, create_component_from_zip
from weblate.vcs.models import VCS_REGISTRY


class BaseCreateView(CreateView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.has_billing = "weblate.billing" in settings.INSTALLED_APPS

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs


@method_decorator(login_required, name="dispatch")
class CreateProject(BaseCreateView):
    model = Project
    form_class = ProjectCreateForm
    billings = None

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        billing_field = form.fields["billing"]
        if self.has_billing:
            billing_field.queryset = self.billings
            try:
                billing_field.initial = int(self.request.GET["billing"])
            except (ValueError, KeyError):
                pass
            billing_field.required = not self.request.user.is_superuser
            if self.request.user.is_superuser:
                billing_field.empty_label = "-- without billing --"
        else:
            billing_field.required = False
            billing_field.widget = HiddenInput()
        return form

    def form_valid(self, form):
        result = super().form_valid(form)
        if self.has_billing and form.cleaned_data["billing"]:
            billing = form.cleaned_data["billing"]
        else:
            billing = None
        self.object.post_create(self.request.user, billing)
        return result

    def can_create(self):
        return (self.has_billing and self.billings) or self.request.user.has_perm(
            "project.add"
        )

    def post(self, request, *args, **kwargs):
        if not self.can_create():
            return redirect("create-project")
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs["can_create"] = self.can_create()
        if self.has_billing:
            from weblate.billing.models import Billing

            kwargs["user_billings"] = Billing.objects.for_user(
                self.request.user
            ).exists()
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        if self.has_billing:
            from weblate.billing.models import Billing

            billings = Billing.objects.get_valid().for_user(request.user).prefetch()
            pks = set()
            for billing in billings:
                limit = billing.plan.display_limit_projects
                if limit == 0 or billing.count_projects < limit:
                    pks.add(billing.pk)
            self.billings = Billing.objects.filter(pk__in=pks).prefetch()
        return super().dispatch(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class CreateComponent(BaseCreateView):
    model = Component
    projects = None
    stage = None
    selected_project = ""
    basic_fields = ("repo", "name", "slug", "vcs", "source_language")
    empty_form = False
    form_class = ComponentInitCreateForm

    def get_form_class(self):
        """Return the form class to use."""
        if self.stage == "create":
            return ComponentCreateForm
        if self.stage == "discover":
            return ComponentDiscoverForm
        return self.form_class

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        if self.request.method != "POST":
            if self.initial:
                # When going from other form (for example ZIP import)
                result.pop("data", None)
                result.pop("files", None)
            if self.has_all_fields() and not self.empty_form:
                result["data"] = self.request.GET
        return result

    def get_success_url(self):
        return reverse(
            "component_progress", kwargs=self.object.get_reverse_url_kwargs()
        )

    def warn_outdated(self, form):
        linked = form.instance.linked_component
        if linked:
            perform_update.delay("Component", linked.pk, auto=True)
            if linked.repo_needs_merge():
                messages.warning(
                    self.request,
                    _(
                        "The repository is outdated, you might not get "
                        "expected results until you update it."
                    ),
                )

    def detect_license(self, form):
        """Automatic license detection based on licensee."""
        try:
            process_result = subprocess.run(
                ["licensee", "detect", "--json", form.instance.full_path],
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=get_clean_env(),
                check=True,
            )
        except FileNotFoundError:
            return
        except (OSError, subprocess.CalledProcessError) as error:
            if getattr(error, "returncode", 0) != 1:
                report_error(cause="Failed licensee invocation")
            return
        result = json.loads(process_result.stdout)
        for license_data in result["licenses"]:
            spdx_id = license_data["spdx_id"]
            for license in (f"{spdx_id}-or-later", f"{spdx_id}-only", spdx_id):
                if license in LICENSE_URLS:
                    self.initial["license"] = license
                    messages.info(
                        self.request,
                        _("Detected license as %s, please check whether it is correct.")
                        % license,
                    )
                    return

    def form_valid(self, form):
        if self.stage == "create":
            form.instance.manage_units = (
                bool(form.instance.template) or form.instance.file_format == "tbx"
            )
            result = super().form_valid(form)
            self.object.post_create(self.request.user)
            return result
        if self.stage == "discover":
            # Move to create
            self.initial = form.cleaned_data
            self.stage = "create"
            self.request.method = "GET"
            self.warn_outdated(form)
            self.detect_license(form)
            return self.get(self, self.request)
        # Move to discover
        self.stage = "discover"
        self.request.method = "GET"
        self.initial = form.cleaned_data
        self.warn_outdated(form)
        return self.get(self, self.request)

    def get_form(self, form_class=None, empty=False):
        self.empty_form = empty
        form = super().get_form(form_class)
        if "project" in form.fields:
            project_field = form.fields["project"]
            project_field.queryset = self.projects
            project_field.empty_label = None
            if self.selected_project:
                project_field.initial = self.selected_project
                try:
                    form.fields["source_language"].initial = Component.objects.filter(
                        project=self.selected_project
                    )[0].source_language_id
                except IndexError:
                    pass
        self.empty_form = False
        return form

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs["projects"] = self.projects
        kwargs["stage"] = self.stage
        return kwargs

    def fetch_params(self, request):
        try:
            self.selected_project = int(
                request.POST.get("project", request.GET.get("project", ""))
            )
        except ValueError:
            self.selected_project = ""
        if request.user.is_superuser:
            self.projects = Project.objects.order()
        elif self.has_billing:
            from weblate.billing.models import Billing

            self.projects = request.user.managed_projects.filter(
                billing__in=Billing.objects.get_valid()
            ).order()
        else:
            self.projects = request.user.managed_projects
        self.initial = {}
        for field in self.basic_fields:
            if field in request.GET:
                self.initial[field] = request.GET[field]

    def has_all_fields(self):
        return self.stage == "init" and all(
            field in self.request.GET for field in self.basic_fields
        )

    def dispatch(self, request, *args, **kwargs):
        if "filemask" in request.POST:
            self.stage = "create"
        elif "discovery" in request.POST:
            self.stage = "discover"
        else:
            self.stage = "init"

        self.fetch_params(request)

        # Proceed to post if all params are present
        if self.has_all_fields():
            return self.post(request, *args, **kwargs)

        return super().dispatch(request, *args, **kwargs)


class CreateFromZip(CreateComponent):
    form_class = ComponentZipCreateForm

    def form_valid(self, form):
        if self.stage != "init":
            return super().form_valid(form)

        try:
            create_component_from_zip(form.cleaned_data)
        except BadZipfile:
            form.add_error("zipfile", _("Failed to parse uploaded ZIP file."))
            return self.form_invalid(form)

        # Move to discover phase
        self.stage = "discover"
        self.initial = form.cleaned_data
        self.initial["vcs"] = "local"
        self.initial["repo"] = "local:"
        self.initial["branch"] = "main"
        self.initial.pop("zipfile")
        self.request.method = "GET"
        return self.get(self, self.request)


class CreateFromDoc(CreateComponent):
    form_class = ComponentDocCreateForm

    def form_valid(self, form):
        if self.stage != "init":
            return super().form_valid(form)

        create_component_from_doc(form.cleaned_data)

        # Move to discover phase
        self.stage = "discover"
        self.initial = form.cleaned_data
        self.initial["vcs"] = "local"
        self.initial["repo"] = "local:"
        self.initial["branch"] = "main"
        self.initial.pop("docfile")
        self.request.method = "GET"
        return self.get(self, self.request)


class CreateComponentSelection(CreateComponent):
    template_name = "trans/component_create.html"

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
                branch
                for branch in component.repository.list_remote_branches()
                if branch != component.branch and not branch_exists(repo, branch)
            ]
            if branches:
                result[component.pk] = branches
        return result

    def fetch_params(self, request):
        super().fetch_params(request)
        self.components = (
            Component.objects.filter_access(request.user)
            .with_repo()
            .prefetch()
            .filter(project__in=self.projects)
            .order_project()
        )
        if self.selected_project:
            self.components = self.components.filter(project__pk=self.selected_project)
        self.origin = request.POST.get("origin")

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs["components"] = self.components
        kwargs["selected_project"] = self.selected_project
        kwargs["existing_form"] = self.get_form(ComponentSelectForm, empty=True)
        kwargs["branch_form"] = self.get_form(ComponentBranchForm, empty=True)
        kwargs["branch_data"] = json.dumps(self.branch_data)
        kwargs["full_form"] = self.get_form(ComponentInitCreateForm, empty=True)
        if "local" in VCS_REGISTRY:
            kwargs["zip_form"] = self.get_form(ComponentZipCreateForm, empty=True)
            kwargs["scratch_form"] = self.get_form(
                ComponentScratchCreateForm, empty=True
            )
            kwargs["doc_form"] = self.get_form(ComponentDocCreateForm, empty=True)
        if self.origin == "branch":
            kwargs["branch_form"] = kwargs["form"]
        elif self.origin == "scratch":
            kwargs["scratch_form"] = kwargs["form"]
        else:
            kwargs["existing_form"] = kwargs["form"]
        return kwargs

    def get_form(self, form_class=None, empty=False):
        form = super().get_form(form_class, empty=empty)
        if isinstance(form, ComponentBranchForm):
            form.fields["component"].queryset = Component.objects.filter(
                pk__in=self.branch_data.keys()
            ).order_project()
            form.branch_data = self.branch_data
        elif isinstance(form, ComponentSelectForm):
            form.fields["component"].queryset = self.components
        return form

    def get_form_class(self):
        if self.origin == "branch":
            return ComponentBranchForm
        if self.origin == "scratch":
            return ComponentScratchCreateForm
        return ComponentSelectForm

    def redirect_create(self, **kwargs):
        return redirect(
            "{}?{}".format(reverse("create-component-vcs"), urlencode(kwargs))
        )

    def form_valid(self, form):
        if self.origin == "scratch":
            project = form.cleaned_data["project"]
            component = project.scratch_create_component(**form.cleaned_data)
            return redirect(
                reverse("component_progress", kwargs=component.get_reverse_url_kwargs())
            )
        component = form.cleaned_data["component"]
        if self.origin == "existing":
            return self.redirect_create(
                repo=component.get_repo_link_url(),
                project=component.project.pk,
                name=form.cleaned_data["name"],
                slug=form.cleaned_data["slug"],
                vcs=component.vcs,
                source_language=component.source_language.pk,
            )
        if self.origin == "branch":
            form.instance.save()
            return redirect(
                reverse(
                    "component_progress", kwargs=form.instance.get_reverse_url_kwargs()
                )
            )

        return redirect("create-component")

    def post(self, request, *args, **kwargs):
        if self.origin == "vcs":
            kwargs = {}
            if self.selected_project:
                kwargs["project"] = self.selected_project
            return self.redirect_create(**kwargs)
        return super().post(request, *args, **kwargs)
