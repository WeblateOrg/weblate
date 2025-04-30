# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import os
import subprocess
from contextlib import suppress
from typing import TYPE_CHECKING
from zipfile import BadZipfile

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.forms import Form, HiddenInput
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.http import urlencode
from django.utils.translation import gettext
from django.views.generic.edit import CreateView

from weblate.trans.backups import ProjectBackup
from weblate.trans.forms import (
    ComponentBranchForm,
    ComponentCreateForm,
    ComponentDiscoverForm,
    ComponentDocCreateForm,
    ComponentInitCreateForm,
    ComponentProjectForm,
    ComponentScratchCreateForm,
    ComponentSelectForm,
    ComponentZipCreateForm,
    ProjectCreateForm,
    ProjectImportCreateForm,
    ProjectImportForm,
)
from weblate.trans.models import Category, Component, Project
from weblate.trans.tasks import perform_update
from weblate.trans.util import get_clean_env
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.licenses import LICENSE_URLS
from weblate.utils.ratelimit import session_ratelimit_post
from weblate.utils.views import create_component_from_doc, create_component_from_zip
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.trans.models.component import ComponentQuerySet

SESSION_CREATE_KEY = "session_component"


class BaseCreateView(CreateView):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.has_billing = "weblate.billing" in settings.INSTALLED_APPS

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_invalid(self, form):
        messages.error(
            self.request,
            gettext(
                "The supplied configuration is incorrect. Please check the errors below.",
            ),
        )
        return super().form_invalid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(session_ratelimit_post("project"), name="dispatch")
class CreateProject(BaseCreateView):
    model = Project
    object: Project
    form_class: type[Form] = ProjectCreateForm
    billings = None

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if "billing" in form.fields:
            billing_field = form.fields["billing"]
            if self.has_billing:
                billing_field.queryset = self.billings
                with suppress(ValueError, KeyError):
                    billing_field.initial = int(self.request.GET["billing"])
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

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        if not self.can_create():
            return redirect("create-project")
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs["can_create"] = self.can_create()
        kwargs["import_form"] = self.get_form(ProjectImportForm)
        if self.has_billing:
            from weblate.billing.models import Billing

            kwargs["user_billings"] = Billing.objects.for_user(
                self.request.user
            ).exists()
        return kwargs

    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):
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


class ImportProject(CreateProject):
    form_class = ProjectImportForm
    template_name = "trans/project_import.html"

    def setup(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        if "import_project" in request.session and os.path.exists(
            request.session["import_project"]
        ):
            if "zipfile" in request.FILES:
                # Delete previous (stale) import data
                del request.session["import_project"]
                request.session.pop("import_billing", None)
                self.projectbackup = None
            else:
                self.projectbackup = ProjectBackup(request.session["import_project"])
                # The backup is already validated at this point,
                # but we need to load the info.
                self.projectbackup.validate()
        else:
            request.session.pop("import_project", None)
            request.session.pop("import_billing", None)
            self.projectbackup = None
        super().setup(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if "billing" in form.fields and self.has_billing:
            from weblate.billing.models import Billing

            billing = self.request.session.get("import_billing")
            if billing:
                form.fields["billing"].initial = Billing.objects.get(pk=billing)
        return form

    def get_form_class(self):
        """Return the form class to use."""
        if self.projectbackup:
            return ProjectImportCreateForm
        return self.form_class

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.projectbackup:
            kwargs["projectbackup"] = self.projectbackup
        return kwargs

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        if "zipfile" in request.FILES and self.projectbackup:
            # Delete previous (stale) import data
            os.unlink(self.projectbackup.filename)
            del self.request.session["import_project"]
            self.request.session.pop("import_billing", None)
            self.projectbackup = None
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if isinstance(form, ProjectImportForm):
            # Save current zip to the import dir
            self.request.session["import_project"] = form.cleaned_data[
                "projectbackup"
            ].store_for_import()
            if form.cleaned_data["billing"]:
                self.request.session["import_billing"] = form.cleaned_data["billing"].pk
            return redirect("create-project-import")
        # Perform actual import
        project = self.projectbackup.restore(
            project_name=form.cleaned_data["name"],
            project_slug=form.cleaned_data["slug"],
            user=self.request.user,
            billing=form.cleaned_data["billing"],
        )
        del self.request.session["import_project"]
        return redirect(project)


@method_decorator(login_required, name="dispatch")
class CreateComponent(BaseCreateView):
    model = Component
    projects = None
    stage = None
    selected_project = None
    selected_category = None
    basic_fields = ("repo", "name", "slug", "vcs", "source_language")
    empty_form = False
    form_class: type[ComponentProjectForm] = ComponentInitCreateForm
    request: AuthenticatedHttpRequest

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
                if SESSION_CREATE_KEY in self.request.session:
                    result["data"] = self.request.session[SESSION_CREATE_KEY]
                else:
                    result["data"] = self.request.GET
        return result

    def get_success_url(self):
        return reverse("show_progress", kwargs={"path": self.object.get_url_path()})

    def warn_outdated(self, form) -> None:
        linked = form.instance.linked_component
        if linked:
            perform_update.delay("Component", linked.pk, auto=True)
            if linked.repo_needs_merge():
                messages.warning(
                    self.request,
                    gettext(
                        "The repository is outdated, you might not get "
                        "expected results until you update it."
                    ),
                )

    def detect_license(self, form) -> None:
        """Automatic license detection based on licensee."""
        try:
            process_result = subprocess.run(
                ["licensee", "detect", "--json", form.instance.full_path],
                text=True,
                capture_output=True,
                env=get_clean_env(),
                check=True,
            )
        except FileNotFoundError:
            return
        except (OSError, subprocess.CalledProcessError) as error:
            if getattr(error, "returncode", 0) != 1:
                report_error("Failed licensee invocation")
            return
        result = json.loads(process_result.stdout)
        for license_data in result["licenses"]:
            spdx_id = license_data["spdx_id"]
            for license_id in (f"{spdx_id}-or-later", f"{spdx_id}-only", spdx_id):
                if license_id in LICENSE_URLS:
                    self.initial["license"] = license_id
                    messages.info(
                        self.request,
                        gettext(
                            "Detected license as %s, please check whether it is correct."
                        )
                        % license_id,
                    )
                    return

    def form_valid(self, form):
        if self.stage == "create":
            form.instance.manage_units = (
                bool(form.instance.template) or form.instance.file_format == "tbx"
            )
            if self.duplicate_existing_component and (
                source_component := form.cleaned_data["source_component"]
            ):
                fields_to_duplicate = [
                    "agreement",
                    "merge_style",
                    "commit_message",
                    "add_message",
                    "delete_message",
                    "merge_message",
                    "addon_message",
                    "pull_message",
                ]
                for field in fields_to_duplicate:
                    setattr(form.instance, field, getattr(source_component, field))

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
            return self.get(self.request)
        # Move to discover
        self.stage = "discover"
        self.request.method = "GET"
        self.initial = form.cleaned_data
        self.warn_outdated(form)
        return self.get(self.request)

    def get_form(self, form_class=None, empty=False):
        self.empty_form = empty
        form = super().get_form(form_class)
        if "project" in form.fields:
            project_field = form.fields["project"]
            category_field = form.fields["category"]
            project_field.queryset = self.projects
            category_field.queryset = Category.objects.filter(project__in=self.projects)
            project_field.empty_label = None
            if self.selected_project:
                project_field.initial = self.selected_project
                with suppress(IndexError):
                    form.fields["source_language"].initial = Component.objects.filter(
                        project=self.selected_project
                    )[0].source_language_id
                if self.selected_category:
                    category_field.initial = self.selected_category
        self.empty_form = False
        if "source_component" in form.fields and self.duplicate_existing_component:
            self.components = Component.objects.filter(
                pk=self.duplicate_existing_component
            )
            form.fields["source_component"].queryset = self.components
            form.initial["source_component"] = self.duplicate_existing_component
        return form

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs["projects"] = self.projects
        kwargs["stage"] = self.stage
        return kwargs

    def fetch_params(self, request: AuthenticatedHttpRequest) -> None:
        try:
            self.selected_project = int(
                request.POST.get("project", request.GET.get("project", ""))
            )
        except ValueError:
            self.selected_project = None
        try:
            self.selected_category = int(
                request.POST.get("category", request.GET.get("category", ""))
            )
        except ValueError:
            self.selected_category = None
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
        session_data = {}
        if SESSION_CREATE_KEY in request.GET and SESSION_CREATE_KEY in request.session:
            session_data = request.session[SESSION_CREATE_KEY]
        for field in self.basic_fields:
            if field in session_data:
                self.initial[field] = session_data[field]
            elif field in request.GET:
                self.initial[field] = request.GET[field]

        try:
            self.duplicate_existing_component = int(request.GET.get("source_component"))
        except (ValueError, TypeError):
            self.duplicate_existing_component = None

    def has_all_fields(self):
        session_data = {}
        if (
            SESSION_CREATE_KEY in self.request.GET
            and SESSION_CREATE_KEY in self.request.session
        ):
            session_data = self.request.session[SESSION_CREATE_KEY]
        return self.stage == "init" and all(
            field in session_data or field in self.request.GET
            for field in self.basic_fields
        )

    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        if "new_base" in request.POST:
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
        except (BadZipfile, OSError):
            form.add_error("zipfile", gettext("Could not parse uploaded ZIP file."))
            return self.form_invalid(form)

        # Move to discover phase
        self.stage = "discover"
        self.initial = form.cleaned_data
        self.initial["vcs"] = "local"
        self.initial["repo"] = "local:"
        self.initial["branch"] = "main"
        self.initial.pop("zipfile")
        self.request.method = "GET"
        return self.get(self.request)


class CreateFromDoc(CreateComponent):
    form_class = ComponentDocCreateForm

    def form_valid(self, form):
        if self.stage != "init":
            return super().form_valid(form)

        fake = create_component_from_doc(
            form.cleaned_data,
            form.cleaned_data.pop("docfile"),
            form.cleaned_data.pop("target_language", None),
        )
        # Move to discover phase
        self.stage = "discover"
        self.initial = form.cleaned_data
        self.initial["vcs"] = "local"
        self.initial["repo"] = "local:"
        self.initial["branch"] = "main"
        self.initial["template"] = fake.template
        self.initial["filemask"] = fake.filemask

        self.request.method = "GET"
        return self.get(self.request)


class CreateComponentSelection(CreateComponent):
    template_name = "trans/component_create.html"

    components: ComponentQuerySet
    origin: str | None = None
    duplicate_existing_component = None

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

    def fetch_params(self, request: AuthenticatedHttpRequest) -> None:
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

        try:
            self.duplicate_existing_component = int(request.GET.get("component"))
        except (ValueError, TypeError):
            self.duplicate_existing_component = None
        self.initial = {}
        if self.duplicate_existing_component:
            source_component = Component.objects.get(
                pk=self.duplicate_existing_component
            )
            self.initial |= {
                "component": source_component,
                "is_glossary": source_component.is_glossary,
            }

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
            if self.duplicate_existing_component:
                self.components |= Component.objects.filter_access(
                    self.request.user
                ).filter(pk=self.duplicate_existing_component)
            form.fields["component"].queryset = self.components
        return form

    def get_form_class(self):
        if self.origin == "branch":
            return ComponentBranchForm
        if self.origin == "scratch":
            return ComponentScratchCreateForm
        return ComponentSelectForm

    def redirect_create(self, **kwargs):
        # Store params in session
        self.request.session[SESSION_CREATE_KEY] = kwargs

        return redirect(
            "{}?{}".format(
                reverse("create-component-vcs"), urlencode({SESSION_CREATE_KEY: 1})
            )
        )

    def form_valid(self, form):
        if self.origin == "scratch":
            project = form.cleaned_data["project"]
            component = project.scratch_create_component(**form.cleaned_data)
            return redirect(
                reverse("show_progress", kwargs={"path": component.get_url_path()})
            )
        component = form.cleaned_data["component"]
        if self.origin == "existing":
            return self.redirect_create(
                repo=component.repo or component.get_repo_link_url(),
                project=component.project.pk,
                category=component.category.pk if component.category else "",
                name=form.cleaned_data["name"],
                slug=form.cleaned_data["slug"],
                is_glossary=form.cleaned_data["is_glossary"],
                vcs=component.vcs,
                source_language=component.source_language.pk,
                license=component.license,
                source_component=component.pk,
            )
        if self.origin == "branch":
            form.instance.save()
            return redirect(
                reverse("show_progress", kwargs={"path": form.instance.get_url_path()})
            )

        return redirect("create-component")

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        if self.origin == "vcs":
            kwargs = {}
            if self.selected_project:
                kwargs["project"] = self.selected_project
            return self.redirect_create(**kwargs)
        return super().post(request, *args, **kwargs)
