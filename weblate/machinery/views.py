# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import (
    Http404,
    HttpRequest,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from django.views.generic.edit import FormView

from weblate.machinery.base import (
    MachineTranslationError,
    sanitize_machinery_error,
)
from weblate.machinery.models import (
    MACHINERY,
    MachineryExclusion,
    MachineryInstallation,
    applicable_installations,
    resolve_installation,
)
from weblate.trans.formatting import format_language_string
from weblate.trans.models import Project, Unit
from weblate.utils.errors import report_error
from weblate.utils.views import parse_path
from weblate.wladmin.views import MENU as MANAGE_MENU

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.machinery.base import (
        BatchMachineTranslation,
        SettingsDict,
    )
    from weblate.trans.models import Translation
    from weblate.workspaces.models import Workspace


class MachineryMixin:
    # Scope-specific setup populates this attribute before dispatch.
    workspace: Any

    @cached_property
    def global_settings_dict(self) -> dict[str, SettingsDict]:
        return {
            item.selector: item.configuration
            for item in MachineryInstallation.objects.filter(
                workspace__isnull=True, project__isnull=True
            )
        }


class MachineryProjectMixin(MachineryMixin):
    def post_setup(self, request: AuthenticatedHttpRequest, kwargs) -> None:
        self.project = parse_path(request, [kwargs["project"]], (Project,))

    @cached_property
    def settings_dict(self) -> dict[str, SettingsDict]:
        return self.project.get_machinery_settings()


class MachineryWorkspaceMixin(MachineryMixin):
    def post_setup(self, request: AuthenticatedHttpRequest, kwargs) -> None:
        from weblate.workspaces.models import Workspace  # ruff: ignore[import-outside-top-level]

        self.workspace = get_object_or_404(Workspace, pk=kwargs["workspace"])


class MachineryGlobalMixin(MachineryMixin):
    @cached_property
    def settings_dict(self) -> dict[str, SettingsDict]:
        return self.global_settings_dict


class DeprecatedMachinery:
    is_available = False
    settings_form: None = None
    sends_data_to_third_party = False

    def __init__(self, identifier: str) -> None:
        self.identifier = self.name = identifier

    def get_identifier(self) -> str:
        return self.identifier

    def get_doc_anchor(self) -> str:
        return f"mt-{self.get_identifier()}"


class MachineryConfiguration:
    def __init__(
        self,
        machinery,
        configuration: SettingsDict | None,
        *,
        project=None,
        is_configured: bool = True,
        installation: MachineryInstallation | None = None,
        enabled: bool | None = None,
        workspace=None,
        excluded_here: bool = False,
    ) -> None:
        self.machinery = machinery
        self.configuration = configuration
        self.project = project
        self.is_configured = is_configured
        self.installation = installation
        self.enabled = enabled
        self.workspace = workspace
        self.excluded_here = excluded_here

    @property
    def is_enabled(self) -> bool:
        return (
            self.enabled if self.enabled is not None else self.configuration is not None
        )

    @property
    def is_available(self):
        return self.machinery.is_available

    @property
    def id(self):
        return (
            self.installation.selector
            if self.installation
            else self.machinery.get_identifier()
        )

    @property
    def name(self):
        return self.machinery.name

    @property
    def doc_anchor(self):
        return self.machinery.get_doc_anchor()

    @property
    def has_settings(self) -> bool:
        return self.machinery.settings_form is not None and (
            self.installation is None
            or (self.project is None and self.workspace is None)
            or (
                self.project is not None
                and self.installation.project_id == self.project.pk
            )
            or (
                self.workspace is not None
                and self.installation.workspace_id == self.workspace.pk
            )
        )

    @property
    def can_delete(self) -> bool:
        return self.installation is not None and (
            (
                self.project is not None
                and self.installation.project_id == self.project.pk
            )
            or (
                self.workspace is not None
                and self.installation.workspace_id == self.workspace.pk
            )
            or (self.project is None and self.workspace is None)
        )

    @property
    def can_enable(self) -> bool:
        return self.can_delete or self.excluded_here

    @property
    def inherited_scope(self) -> str | None:
        if self.installation is None or self.can_delete:
            return None
        return "workspace" if self.installation.workspace_id is not None else "site"

    def get_absolute_url(self) -> str:
        kwargs = {"machinery": self.id}
        if self.project:
            kwargs["project"] = self.project.slug
        if self.workspace:
            kwargs["workspace"] = self.workspace.pk
        return reverse("machinery-edit", kwargs=kwargs)


class ListMachineryView(TemplateView):
    template_name = "machinery/list.html"
    workspace: Any

    def setup(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:  # type: ignore[override]
        super().setup(request, *args, **kwargs)
        self.project = None
        self.workspace = None
        self.post_setup(request, kwargs)
        self.configured_services = sorted(
            self.get_configured_services(), key=lambda obj: obj.name.casefold()
        )
        self.available_services = sorted(
            (
                MachineryConfiguration(
                    obj,
                    None,
                    project=self.project,
                    workspace=self.workspace,
                    is_configured=False,
                )
                for obj in MACHINERY.values()
            ),
            key=lambda obj: obj.name.casefold(),
        )

    @cached_property
    def settings_dict(self) -> dict[str, SettingsDict]:
        raise NotImplementedError

    def post_setup(self, request: AuthenticatedHttpRequest, kwargs) -> None:
        return

    def get_configured_services(self):
        if self.project:
            query = Q(project=self.project) | Q(
                project__isnull=True, workspace__isnull=True
            )
            if self.project.workspace_id:
                query |= Q(workspace_id=self.project.workspace_id)
            exclusions = MachineryExclusion.objects.filter(project=self.project)
            if self.project.workspace_id:
                exclusions |= MachineryExclusion.objects.filter(
                    workspace_id=self.project.workspace_id
                )
        elif self.workspace:
            query = Q(workspace=self.workspace) | Q(
                project__isnull=True, workspace__isnull=True
            )
            exclusions = MachineryExclusion.objects.filter(workspace=self.workspace)
        else:
            query = Q(project__isnull=True, workspace__isnull=True)
            exclusions = MachineryExclusion.objects.none()
        rules = list(exclusions)
        for installation in MachineryInstallation.objects.filter(query).order_by("id"):
            engine = installation.engine
            inherited = (
                self.project and installation.project_id != self.project.pk
            ) or (self.workspace and installation.workspace_id != self.workspace.pk)
            excluded_here = bool(inherited) and any(
                (rule.installation_id == installation.pk or rule.engine == engine)
                and (
                    (self.project is not None and rule.project_id == self.project.pk)
                    or (
                        self.workspace is not None
                        and rule.workspace_id == self.workspace.pk
                    )
                )
                for rule in rules
            )
            excluded_upstream = bool(inherited) and any(
                (rule.installation_id == installation.pk or rule.engine == engine)
                and self.project is not None
                and rule.workspace_id == self.project.workspace_id
                and installation.workspace_id is None
                for rule in rules
            )
            enabled = installation.enabled and not (excluded_here or excluded_upstream)
            try:
                machinery = MACHINERY[engine]
            except KeyError:
                yield MachineryConfiguration(
                    DeprecatedMachinery(engine),
                    installation.configuration,
                    project=self.project,
                    workspace=self.workspace,
                    installation=installation,
                    enabled=enabled,
                    excluded_here=excluded_here,
                )
            else:
                yield MachineryConfiguration(
                    machinery,
                    installation.configuration,
                    project=self.project,
                    workspace=self.workspace,
                    installation=installation,
                    enabled=enabled,
                    excluded_here=excluded_here,
                )

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["configured_services"] = self.configured_services
        result["available_services"] = self.available_services
        if not self.project and not self.workspace:
            result["menu_items"] = MANAGE_MENU
            result["menu_page"] = "machinery"
        return result


class ListMachineryGlobalView(MachineryGlobalMixin, ListMachineryView):
    pass


class ListMachineryProjectView(MachineryProjectMixin, ListMachineryView):
    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["project"] = self.project
        return result


class ListMachineryWorkspaceView(MachineryWorkspaceMixin, ListMachineryView):
    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not request.user.has_perm("workspace.edit", self.workspace):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["workspace"] = self.workspace
        return result


class EditMachineryView(FormView):
    template_name = "machinery/edit.html"

    machinery: DeprecatedMachinery | type[BatchMachineTranslation]
    workspace: Any

    def setup(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:  # type: ignore[override]
        super().setup(request, *args, **kwargs)
        self.machinery_id, _, identifier = kwargs["machinery"].partition(":")
        self.installation = (
            get_object_or_404(MachineryInstallation, pk=identifier)
            if identifier.isdecimal()
            else None
        )
        if self.installation and self.installation.engine != self.machinery_id:
            msg = "Invalid installation"
            raise Http404(msg)
        try:
            self.machinery = MACHINERY[self.machinery_id]
        except KeyError:
            self.machinery = DeprecatedMachinery(self.machinery_id)
        self.project = None
        self.workspace = None
        self.post_setup(request, kwargs)
        if (
            self.installation
            and self.project is None
            and self.workspace is None
            and (self.installation.project_id or self.installation.workspace_id)
        ):
            msg = "Invalid installation scope"
            raise Http404(msg)
        if (
            self.installation
            and self.project is not None
            and not (
                self.installation.project_id == self.project.pk
                or (
                    self.installation.project_id is None
                    and self.installation.workspace_id
                    in {None, self.project.workspace_id}
                )
            )
        ):
            msg = "Invalid installation scope"
            raise Http404(msg)
        if (
            self.installation
            and self.workspace is not None
            and not (
                self.installation.project_id is None
                and self.installation.workspace_id in {None, self.workspace.pk}
            )
        ):
            msg = "Invalid installation scope"
            raise Http404(msg)

    def get_form_class(self):
        return self.machinery.settings_form

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["machinery"] = self.machinery
        result["allow_private_targets"] = self.allow_private_targets
        return result

    @property
    def allow_private_targets(self) -> bool:
        return True

    @cached_property
    def settings_dict(self) -> dict[str, SettingsDict]:
        raise NotImplementedError

    def post_setup(self, request: AuthenticatedHttpRequest, kwargs) -> None:
        return

    def get_initial(self):
        if self.installation and (
            (self.project and self.installation.project_id == self.project.pk)
            or (self.workspace and self.installation.workspace_id == self.workspace.pk)
            or (self.project is None and self.workspace is None)
        ):
            return self.installation.configuration
        return {}

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["machinery_id"] = self.machinery.get_identifier()
        result["machinery_name"] = self.machinery.name
        result["machinery_doc_anchor"] = self.machinery.get_doc_anchor()
        result["machinery_sends_data_to_third_party"] = (
            self.machinery.sends_data_to_third_party
        )
        result["installation"] = self.installation
        result["workspace"] = self.workspace
        return result

    def install_service(self) -> None:
        self.save_settings({})

    def form_valid(self, form):
        try:
            self.save_settings(form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
            return self.form_invalid(form)
        return super().form_valid(form)

    def save_settings(self, data) -> None:
        raise NotImplementedError

    def delete_service(self) -> None:
        raise NotImplementedError

    def enable_service(self) -> None:
        return

    def get_success_url(self):
        if self.project:
            return reverse("machinery-list", kwargs={"project": self.project.slug})
        if self.workspace:
            return reverse(
                "workspace-machinery", kwargs={"workspace": self.workspace.pk}
            )
        return reverse("manage-machinery")

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        if "delete" in request.POST:
            self.delete_service()
            return HttpResponseRedirect(self.get_success_url())

        if "pause" in request.POST:
            self.pause_service()
            return HttpResponseRedirect(self.get_success_url())

        if "exclude_engine" in request.POST:
            self.exclude_engine()
            return HttpResponseRedirect(self.get_success_url())

        if not self.machinery.is_available:
            msg = "Invalid service specified"
            raise Http404(msg)

        if "enable" in request.POST:
            try:
                self.enable_service()
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages))
            return HttpResponseRedirect(self.get_success_url())

        if "install" in request.POST:
            if self.machinery.settings_form is not None:
                return HttpResponseRedirect(request.path)
            try:
                self.install_service()
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages))
            return HttpResponseRedirect(self.get_success_url())
        return super().post(request, *args, **kwargs)

    def pause_service(self) -> None:
        if self.installation:
            self.installation.enabled = False
            self.installation.save(update_fields=["enabled"])

    def exclude_engine(self) -> None:
        raise PermissionDenied

    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        if not self.machinery.is_available:
            msg = "Invalid service specified"
            raise Http404(msg)
        return super().get(request, *args, **kwargs)


class EditMachineryGlobalView(MachineryGlobalMixin, EditMachineryView):
    def save_settings(self, data: SettingsDict) -> None:
        if self.installation:
            self.installation.configuration = data
            self.installation.slug = self.request.POST.get("slug", "")
            self.installation.save()
        else:
            MachineryInstallation.objects.create(
                engine=self.machinery_id,
                slug=self.request.POST.get("slug", ""),
                configuration=data,
            )

    def delete_service(self) -> None:
        if self.installation:
            self.installation.delete()

    def enable_service(self) -> None:
        if self.installation:
            self.installation.enabled = True
            self.installation.save(update_fields=["enabled"])

    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        if not request.user.has_perm("machinery.edit"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def enable_inherited_installation(
    installation: MachineryInstallation,
    *,
    project: Project | None = None,
    workspace: Workspace | None = None,
) -> None:
    """Enable one inherited installation without exposing its siblings."""
    scope = {"project": project} if project is not None else {"workspace": workspace}
    inherited = MachineryInstallation.objects.filter(
        engine=installation.engine, project__isnull=True
    )
    if project is not None and project.workspace_id:
        inherited = inherited.filter(
            Q(workspace__isnull=True) | Q(workspace_id=project.workspace_id)
        )
    else:
        inherited = inherited.filter(workspace__isnull=True)

    with transaction.atomic():
        engine_exclusions = MachineryExclusion.objects.filter(
            **scope, engine=installation.engine
        )
        if engine_exclusions.exists():
            for sibling in inherited.exclude(pk=installation.pk):
                MachineryExclusion.objects.get_or_create(**scope, installation=sibling)
            engine_exclusions.delete()
        MachineryExclusion.objects.filter(**scope, installation=installation).delete()


class EditMachineryProjectView(MachineryProjectMixin, EditMachineryView):
    @property
    def allow_private_targets(self) -> bool:
        return False

    def save_settings(self, data: SettingsDict | None) -> None:
        if self.installation:
            if self.installation.project_id != self.project.pk:
                raise PermissionDenied
            self.installation.configuration = data
            self.installation.slug = self.request.POST.get("slug", "")
            self.installation.save()
        elif data is not None:
            MachineryInstallation.objects.create(
                project=self.project,
                engine=self.machinery_id,
                slug=self.request.POST.get("slug", ""),
                configuration=data,
            )

    def delete_service(self) -> None:
        if self.installation:
            if self.installation.project_id == self.project.pk:
                self.installation.delete()
            else:
                MachineryExclusion.objects.get_or_create(
                    project=self.project, installation=self.installation
                )

    def enable_service(self) -> None:
        if self.installation:
            if self.installation.project_id == self.project.pk:
                self.installation.enabled = True
                self.installation.save(update_fields=["enabled"])
            else:
                enable_inherited_installation(self.installation, project=self.project)

    def pause_service(self) -> None:
        if not self.installation or self.installation.project_id != self.project.pk:
            raise PermissionDenied
        super().pause_service()

    def exclude_engine(self) -> None:
        MachineryExclusion.objects.get_or_create(
            project=self.project, engine=self.machinery_id
        )

    def setup(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:  # type: ignore[override]
        super().setup(request, *args, **kwargs)
        self.project = parse_path(request, [kwargs["project"]], (Project,))

    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["project"] = self.project
        return result


class EditMachineryWorkspaceView(MachineryWorkspaceMixin, EditMachineryView):
    @property
    def allow_private_targets(self) -> bool:
        return False

    def save_settings(self, data: SettingsDict) -> None:
        if self.installation:
            if self.installation.workspace_id != self.workspace.pk:
                raise PermissionDenied
            self.installation.configuration = data
            self.installation.slug = self.request.POST.get("slug", "")
            self.installation.save()
        else:
            MachineryInstallation.objects.create(
                workspace=self.workspace,
                engine=self.machinery_id,
                slug=self.request.POST.get("slug", ""),
                configuration=data,
            )

    def delete_service(self) -> None:
        if self.installation:
            if self.installation.workspace_id == self.workspace.pk:
                self.installation.delete()
            else:
                MachineryExclusion.objects.get_or_create(
                    workspace=self.workspace, installation=self.installation
                )

    def enable_service(self) -> None:
        if self.installation:
            if self.installation.workspace_id == self.workspace.pk:
                self.installation.enabled = True
                self.installation.save(update_fields=["enabled"])
            else:
                enable_inherited_installation(
                    self.installation, workspace=self.workspace
                )

    def pause_service(self) -> None:
        if not self.installation or self.installation.workspace_id != self.workspace.pk:
            raise PermissionDenied
        super().pause_service()

    def exclude_engine(self) -> None:
        MachineryExclusion.objects.get_or_create(
            workspace=self.workspace, engine=self.machinery_id
        )

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not request.user.has_perm("workspace.edit", self.workspace):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def format_string_helper(
    source: str, translation: Translation, diff: str | None = None
):
    return format_language_string(source, translation, diff=diff)["items"][0]["content"]


def format_results_helper(
    item: dict,
    targets: list[str],
    plural_form: int,
    translation: Translation,
    source_translation: Translation,
    *,
    multivalue: bool = False,
) -> None:
    item["plural_form"] = plural_form
    if multivalue:
        item["multivalue"] = True
    target = None if multivalue else targets[plural_form]
    item["diff"] = format_string_helper(item["text"], translation, target)
    item["source_diff"] = format_string_helper(
        item["source"], source_translation, item["original_source"]
    )
    item["html"] = format_string_helper(item["text"], translation)


def get_machinery_translations(
    request: AuthenticatedHttpRequest,
    translation_service,
    unit: Unit,
    search: str | None,
    targets: list[str],
    translation: Translation,
    source_translation: Translation,
) -> list[dict]:
    if search:
        translations = translation_service.search(unit, search, request.user)
        return format_machinery_translations(
            translations,
            translation_service=translation_service,
            multivalue=unit.is_multivalue
            or unit.has_multiple_values(unit.plural_map, targets),
            search=True,
            targets=targets,
            translation=translation,
            source_translation=source_translation,
        )

    translations = translation_service.translate(unit, request.user)
    return format_machinery_translations(
        translations,
        translation_service=translation_service,
        multivalue=unit.is_multivalue
        or unit.has_multiple_values(unit.plural_map, targets),
        search=False,
        targets=targets,
        translation=translation,
        source_translation=source_translation,
    )


async def get_machinery_translations_async(
    request: AuthenticatedHttpRequest,
    translation_service: BatchMachineTranslation,
    unit: Unit,
    search: str | None,
    targets: list[str],
    translation: Translation,
    source_translation: Translation,
) -> list[dict]:
    if search:
        translations = await translation_service.asearch(unit, search, request.user)
        is_search = True
    else:
        translations = await translation_service.atranslate(unit, request.user)
        is_search = False
    return await sync_to_async(format_machinery_translations)(
        translations,
        translation_service=translation_service,
        multivalue=unit.is_multivalue
        or unit.has_multiple_values(unit.plural_map, targets),
        search=is_search,
        targets=targets,
        translation=translation,
        source_translation=source_translation,
    )


def format_machinery_translations(
    translations,
    *,
    translation_service: BatchMachineTranslation,
    search: bool,
    multivalue: bool = False,
    targets: list[str],
    translation: Translation,
    source_translation: Translation,
) -> list[dict]:
    installation_slug = translation_service.settings.get("_installation_slug")
    if search:
        for item in translations:
            item["installation_slug"] = installation_slug
            format_results_helper(
                item, targets, 0, translation, source_translation, multivalue=multivalue
            )
        return translations

    for plural_form, possible_translations in enumerate(translations):
        for item in possible_translations:
            item["installation_slug"] = installation_slug
            format_results_helper(
                item,
                targets,
                plural_form,
                translation,
                source_translation,
                multivalue=multivalue,
            )
    return list(chain.from_iterable(translations))


def get_machinery_source_translation(translation_service, unit: Unit) -> Translation:
    if translation_service.uses_custom_source(unit):
        source_unit = unit.effective_source_unit
        if source_unit is None:
            raise PermissionDenied
        return source_unit.translation
    component = unit.translation.component
    language = translation_service.get_unit_source_language(unit)
    if language.pk != component.source_language_id:
        source = component.translation_set.filter(language=language).first()
        if source is not None:
            return source
    return component.source_translation


def handle_machinery(request: AuthenticatedHttpRequest, service, unit, search=None):
    translation = unit.translation
    component = translation.component
    if not request.user.has_perm("machinery.view", translation):
        raise PermissionDenied

    try:
        translation_service_class = MACHINERY[service.partition(":")[0]]
    except KeyError as error:
        msg = "Invalid service specified"
        raise Http404(msg) from error

    # Error response
    response = {
        "responseStatus": 500,
        "responseDetails": "",
        "translations": [],
        "lang": translation.language.code,
        "dir": translation.language.direction,
        "service": translation_service_class.name,
    }

    machinery_settings = component.project.get_machinery_settings()
    targets = unit.get_target_plurals()

    try:
        installation = resolve_installation(service, component.project)
        translation_service = translation_service_class(
            machinery_settings[installation.selector]
        )
    except (KeyError, ValueError):
        response["responseDetails"] = gettext("Service is currently not available.")
    else:
        response["service"] = translation_service.name
        source_translation = get_machinery_source_translation(translation_service, unit)
        try:
            translations = get_machinery_translations(
                request,
                translation_service,
                unit,
                search,
                targets,
                translation,
                source_translation,
            )
            response["translations"] = translations
            response["responseStatus"] = 200
        except MachineTranslationError as exc:
            response["responseDetails"] = sanitize_machinery_error(str(exc))
        except Exception as error:
            report_error("Machinery failed", project=component.project, exception=error)
            response["responseDetails"] = gettext("Service is currently not available.")

    if response["responseStatus"] != 200:
        translation.log_info(
            "machinery %s failed: %s", service, response["responseDetails"]
        )

    return JsonResponse(data=response)


def get_machinery_unit(user, unit_id: int) -> Unit:
    return get_object_or_404(
        Unit.objects.filter_access(user).select_related(
            "translation__component__project",
            "translation__language",
        ),
        pk=unit_id,
    )


@require_POST
async def translate(request: AuthenticatedHttpRequest, unit_id: int, service: str):
    """AJAX handler for translating."""
    unit = await sync_to_async(get_machinery_unit)(request.user, unit_id)
    translation = await sync_to_async(lambda: unit.translation)()
    component = await sync_to_async(lambda: translation.component)()
    if not await sync_to_async(request.user.has_perm)("machinery.view", translation):
        raise PermissionDenied

    try:
        translation_service_class = MACHINERY[service.partition(":")[0]]
    except KeyError as error:
        msg = "Invalid service specified"
        raise Http404(msg) from error

    response = {
        "responseStatus": 500,
        "responseDetails": "",
        "translations": [],
        "lang": translation.language.code,
        "dir": translation.language.direction,
        "service": translation_service_class.name,
    }

    machinery_settings, targets = await sync_to_async(
        lambda: (
            component.project.get_machinery_settings(),
            unit.get_target_plurals(),
        )
    )()
    try:
        installation = await sync_to_async(resolve_installation)(
            service, component.project
        )
        translation_service = translation_service_class(
            machinery_settings[installation.selector]
        )
    except (KeyError, ValueError):
        response["responseDetails"] = gettext("Service is currently not available.")
    else:
        response["service"] = translation_service.name
        source_translation = await sync_to_async(get_machinery_source_translation)(
            translation_service, unit
        )
        try:
            response["translations"] = await get_machinery_translations_async(
                request,
                translation_service,
                unit,
                None,
                targets,
                translation,
                source_translation,
            )
            response["responseStatus"] = 200
        except MachineTranslationError as exc:
            response["responseDetails"] = sanitize_machinery_error(str(exc))
        except Exception as error:
            await sync_to_async(report_error)(
                "Machinery failed",
                project=component.project,
                exception=error,
            )
            response["responseDetails"] = gettext("Service is currently not available.")

    if response["responseStatus"] != 200:
        await sync_to_async(translation.log_info)(
            "machinery %s failed: %s", service, response["responseDetails"]
        )

    return JsonResponse(data=response)


@require_POST
def memory(request: AuthenticatedHttpRequest, unit_id: int):
    """AJAX handler for translation memory."""
    unit = get_object_or_404(Unit.objects.filter_access(request.user), pk=unit_id)
    query = request.POST.get("q")
    if not query:
        return HttpResponseBadRequest("Missing search string")

    installations = [
        installation
        for installation in applicable_installations(unit.translation.component.project)
        if installation.engine == "weblate-translation-memory"
    ]
    service = (
        min(
            installations,
            key=lambda installation: (
                0 if installation.project_id else 1 if installation.workspace_id else 2,
                installation.pk,
            ),
        ).selector
        if installations
        else "weblate-translation-memory"
    )
    return handle_machinery(request, service, unit, search=query)
