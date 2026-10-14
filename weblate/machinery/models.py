# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from appconf import AppConf
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy

from weblate.utils.classloader import ClassRegistry

from .base import BatchMachineTranslation
from .defaults import DEFAULT_WEBLATE_MACHINERY

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from django.db.models.base import ModelBase

    from weblate.trans.models import Project

    from .types import SettingsDict

MACHINERY = ClassRegistry(
    "WEBLATE_MACHINERY",
    collect_errors=True,
    base_class=BatchMachineTranslation,
)

MAX_INSTALLATIONS_PER_SCOPE = 20


class WeblateConf(AppConf):
    """Machine-translation settings."""

    # List of machinery classes
    WEBLATE_MACHINERY = DEFAULT_WEBLATE_MACHINERY

    class Meta:
        prefix = ""


class MachineryInstallation(models.Model):
    """One configured instance of an automatic suggestion service."""

    engine = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    configuration = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace", null=True, blank=True, on_delete=models.CASCADE
    )
    project = models.ForeignKey(
        "trans.Project", null=True, blank=True, on_delete=models.CASCADE
    )

    class Meta:
        # ruff: ignore[mutable-class-default]
        constraints = [
            models.CheckConstraint(
                condition=Q(workspace__isnull=True) | Q(project__isnull=True),
                name="machinery_one_scope",
            ),
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(slug__gt="", workspace__isnull=True, project__isnull=True),
                name="machinery_site_slug",
            ),
            models.UniqueConstraint(
                fields=["workspace", "slug"],
                condition=Q(slug__gt="", workspace__isnull=False),
                name="machinery_workspace_slug",
            ),
            models.UniqueConstraint(
                fields=["project", "slug"],
                condition=Q(slug__gt="", project__isnull=False),
                name="machinery_project_slug",
            ),
        ]

    def __str__(self) -> str:
        return self.selector

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        self.full_clean()
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def clean(self) -> None:
        super().clean()
        if self.workspace_id and self.project_id:
            raise ValidationError(gettext_lazy("Choose only one installation scope."))
        if self.slug and self.slug.isdecimal():
            raise ValidationError(
                {
                    "slug": gettext_lazy(
                        "A numeric slug is reserved for installation IDs."
                    )
                }
            )
        scope = MachineryInstallation.objects.all()
        scope = (
            scope.filter(project_id=self.project_id)
            if self.project_id is not None
            else scope.filter(project__isnull=True)
        )
        scope = (
            scope.filter(workspace_id=self.workspace_id)
            if self.workspace_id is not None
            else scope.filter(workspace__isnull=True)
        )
        if (
            not self.pk or not MachineryInstallation.objects.filter(pk=self.pk).exists()
        ) and scope.count() >= MAX_INSTALLATIONS_PER_SCOPE:
            raise ValidationError(
                gettext_lazy("This scope already has 20 service installations.")
            )
        try:
            service = MACHINERY[self.engine]
        except KeyError:
            service = None
        if service is not None and service.settings_form is None:
            duplicate = scope.filter(engine=self.engine).exclude(pk=self.pk)
            if duplicate.exists():
                raise ValidationError(
                    {"engine": gettext_lazy("This service is already installed here.")}
                )
            if self.enabled:
                for other in MachineryInstallation.objects.filter(
                    engine=self.engine, enabled=True
                ).exclude(pk=self.pk):
                    if _internal_installations_overlap(self, other):
                        raise ValidationError(
                            {
                                "engine": gettext_lazy(
                                    "Exclude the inherited installation before enabling this service."
                                )
                            }
                        )
        if not self.slug:
            return
        candidates = MachineryInstallation.objects.filter(slug=self.slug).exclude(
            pk=self.pk
        )
        if self.project_id:
            workspace_id = self.project.workspace_id if self.project else None
            candidates = candidates.filter(
                Q(project_id=self.project_id)
                | Q(workspace_id=workspace_id, project__isnull=True)
                | Q(workspace__isnull=True, project__isnull=True)
            )
        elif self.workspace_id:
            candidates = candidates.filter(
                Q(workspace_id=self.workspace_id)
                | Q(project__workspace_id=self.workspace_id)
                | Q(workspace__isnull=True, project__isnull=True)
            )
        if candidates.exists():
            raise ValidationError(
                {
                    "slug": gettext_lazy(
                        "This slug is already used in an affected project."
                    )
                }
            )

    @property
    def selector(self) -> str:
        return f"{self.engine}:{self.id}"


class MachineryExclusionQuerySet(models.QuerySet["MachineryExclusion"]):
    def delete(self) -> tuple[int, dict[str, int]]:
        with transaction.atomic():
            engines = set()
            for item in self.select_related("installation"):
                engine = item.engine or (
                    item.installation.engine if item.installation is not None else ""
                )
                if engine:
                    engines.add(engine)
            result = super().delete()
            for engine in engines:
                _validate_unconfigured_engine(engine)
            return result


class MachineryExclusion(models.Model):
    """Hide inherited installations at a workspace or project scope."""

    workspace = models.ForeignKey(
        "workspaces.Workspace", null=True, blank=True, on_delete=models.CASCADE
    )
    project = models.ForeignKey(
        "trans.Project", null=True, blank=True, on_delete=models.CASCADE
    )
    installation = models.ForeignKey(
        MachineryInstallation, null=True, blank=True, on_delete=models.CASCADE
    )
    engine = models.CharField(max_length=100, blank=True)
    objects = MachineryExclusionQuerySet.as_manager()

    class Meta:
        # ruff: ignore[mutable-class-default]
        constraints = [
            models.CheckConstraint(
                condition=(Q(workspace__isnull=True) & Q(project__isnull=False))
                | (Q(workspace__isnull=False) & Q(project__isnull=True)),
                name="machinery_exclusion_one_scope",
            ),
            models.CheckConstraint(
                condition=(Q(installation__isnull=True) & ~Q(engine=""))
                | (Q(installation__isnull=False) & Q(engine="")),
                name="machinery_exclusion_one_target",
            ),
            models.UniqueConstraint(
                fields=["workspace", "installation"],
                name="machinery_workspace_installation_exclusion",
            ),
            models.UniqueConstraint(
                fields=["project", "installation"],
                name="machinery_project_installation_exclusion",
            ),
            models.UniqueConstraint(
                fields=["workspace", "engine"],
                condition=~Q(engine=""),
                name="machinery_workspace_engine_exclusion",
            ),
            models.UniqueConstraint(
                fields=["project", "engine"],
                condition=~Q(engine=""),
                name="machinery_project_engine_exclusion",
            ),
        ]

    def __str__(self) -> str:
        target = self.installation_id or self.engine
        scope = self.project_id or self.workspace_id
        return f"{scope}:{target}"

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        self.full_clean()
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def delete(
        self, using: str | None = None, keep_parents: bool = False
    ) -> tuple[int, dict[str, int]]:
        engine = self.engine or (
            self.installation.engine if self.installation is not None else ""
        )
        with transaction.atomic(using=using):
            result = super().delete(using=using, keep_parents=keep_parents)
            _validate_unconfigured_engine(engine)
            return result

    def clean(self) -> None:
        super().clean()
        if bool(self.workspace_id) == bool(self.project_id):
            raise ValidationError(gettext_lazy("Choose one exclusion scope."))
        if bool(self.installation_id) == bool(self.engine):
            raise ValidationError(gettext_lazy("Choose an installation or an engine."))
        if self.installation_id:
            target = self.installation
            if target is None:
                raise ValidationError(
                    gettext_lazy("Choose an installation or an engine.")
                )
            if self.workspace_id and (target.project_id or target.workspace_id):
                raise ValidationError(
                    gettext_lazy(
                        "Only site installations can be excluded by a workspace."
                    )
                )
            if self.project_id and (
                target.project_id
                or (
                    target.workspace_id
                    and target.workspace_id
                    != (self.project.workspace_id if self.project else None)
                )
            ):
                raise ValidationError(
                    gettext_lazy("Only inherited installations can be excluded.")
                )


def _unconfigured_engine(engine: str) -> bool:
    try:
        return MACHINERY[engine].settings_form is None
    except KeyError:
        return False


def _exclusion_target(installation: MachineryInstallation) -> Q:
    target = Q(engine=installation.engine)
    if installation.pk is not None:
        target |= Q(installation_id=installation.pk)
    return target


def _internal_installations_overlap(
    first: MachineryInstallation,
    second: MachineryInstallation,
    *,
    project_override: Project | None = None,
) -> bool:
    if first.project_id and second.project_id:
        return first.project_id == second.project_id
    if first.project_id or second.project_id:
        local = first if first.project_id else second
        inherited = second if local is first else first
        project = (
            project_override
            if project_override is not None and project_override.pk == local.project_id
            else local.project
        )
        if project is None or (
            inherited.workspace_id and inherited.workspace_id != project.workspace_id
        ):
            return False
        target = _exclusion_target(inherited)
        if (
            MachineryExclusion.objects.filter(project_id=project.pk)
            .filter(target)
            .exists()
        ):
            return False
        if inherited.workspace_id is None and project.workspace_id:
            return (
                not MachineryExclusion.objects.filter(workspace_id=project.workspace_id)
                .filter(target)
                .exists()
            )
        return True
    if first.workspace_id and second.workspace_id:
        return first.workspace_id == second.workspace_id
    if first.workspace_id or second.workspace_id:
        shared = first if first.workspace_id else second
        inherited = second if shared is first else first
        if shared.workspace_id is None:
            return False
        return (
            not MachineryExclusion.objects.filter(workspace_id=shared.workspace_id)
            .filter(_exclusion_target(inherited))
            .exists()
        )
    return True


def _validate_unconfigured_engine(engine: str) -> None:
    if not _unconfigured_engine(engine):
        return
    installations = list(
        MachineryInstallation.objects.filter(
            engine=engine, enabled=True
        ).select_related("project")
    )
    for index, first in enumerate(installations):
        for second in installations[index + 1 :]:
            if _internal_installations_overlap(first, second):
                raise ValidationError(
                    gettext_lazy(
                        "Exclude the inherited installation before enabling this service."
                    )
                )


def validate_internal_installations_for_project(project: Project) -> None:
    """Check a project's installations before changing its workspace."""
    scopes = Q(project_id=project.pk) | Q(project__isnull=True, workspace__isnull=True)
    if project.workspace_id:
        scopes |= Q(project__isnull=True, workspace_id=project.workspace_id)
    installations = list(
        MachineryInstallation.objects.filter(scopes, enabled=True).select_related(
            "project"
        )
    )
    for index, first in enumerate(installations):
        if not _unconfigured_engine(first.engine):
            continue
        for second in installations[index + 1 :]:
            if first.engine == second.engine and _internal_installations_overlap(
                first, second, project_override=project
            ):
                raise ValidationError(
                    gettext_lazy(
                        "Automatic suggestion services conflict with the new workspace."
                    )
                )


def _without_duplicate_internal_installations(
    installations: list[MachineryInstallation],
) -> list[MachineryInstallation]:
    selected: dict[str, MachineryInstallation] = {}
    for installation in installations:
        if not _unconfigured_engine(installation.engine):
            continue
        previous = selected.get(installation.engine)
        rank = (bool(installation.project_id), bool(installation.workspace_id))
        if previous is None or rank > (
            bool(previous.project_id),
            bool(previous.workspace_id),
        ):
            selected[installation.engine] = installation
    return [
        installation
        for installation in installations
        if not _unconfigured_engine(installation.engine)
        or selected[installation.engine] is installation
    ]


def applicable_installations(
    project: Project | None = None,
) -> list[MachineryInstallation]:
    """Return enabled installations visible to a project in stable order."""
    scopes = Q(workspace__isnull=True, project__isnull=True)
    if project is not None:
        scopes |= Q(project=project)
        if project.workspace_id:
            scopes |= Q(workspace_id=project.workspace_id, project__isnull=True)
    installations = list(
        MachineryInstallation.objects.filter(scopes, enabled=True).order_by("id")
    )
    if project is None:
        return _without_duplicate_internal_installations(installations)
    exclusions = list(
        MachineryExclusion.objects.filter(
            Q(project=project)
            | Q(workspace_id=project.workspace_id, project__isnull=True)
        )
    )
    result = []
    for installation in installations:
        hidden = any(
            (
                (rule.project_id == project.pk and installation.project_id is None)
                or (
                    rule.workspace_id == project.workspace_id
                    and installation.project_id is None
                    and installation.workspace_id is None
                )
            )
            and (
                rule.installation_id == installation.pk
                or rule.engine == installation.engine
            )
            for rule in exclusions
        )
        if not hidden:
            result.append(installation)
    return _without_duplicate_internal_installations(result)


def machinery_settings_for_project(
    project: Project | None = None,
) -> dict[str, SettingsDict]:
    result = {}
    for installation in applicable_installations(project):
        configuration = dict(installation.configuration)
        if project is not None and (
            installation.project_id or installation.workspace_id
        ):
            configuration["_project"] = project
        configuration["_installation_id"] = installation.pk
        configuration["_installation_slug"] = installation.slug
        result[installation.selector] = cast("SettingsDict", configuration)
    return result


def resolve_installation(
    selector: str, project: Project | None = None
) -> MachineryInstallation:
    """Resolve a bare engine, numeric ID, or optional slug in the effective scope."""
    engine, separator, identifier = selector.partition(":")
    matches = [
        item for item in applicable_installations(project) if item.engine == engine
    ]
    if separator:
        matches = [
            item
            for item in matches
            if str(item.pk) == identifier or item.slug == identifier
        ]
    if not matches:
        msg = gettext_lazy("Service is currently not available.")
        raise MachineryUnavailableError(msg)
    if len(matches) != 1:
        msg = format_lazy(
            gettext_lazy("Select an available installation using {}:<id>"), engine
        )
        raise MachineryAmbiguousError(msg)
    return matches[0]


class MachineryUnavailableError(ValueError):
    """The requested installation does not apply to this project."""


class MachineryAmbiguousError(ValueError):
    """A bare engine name matches several installations."""


def selected_machinery_settings(
    project: Project, selectors: list[str]
) -> dict[str, SettingsDict]:
    """Resolve saved selectors, including legacy bare engine names."""
    configured = project.get_machinery_settings()
    result = {}
    for selector in selectors:
        try:
            installation = resolve_installation(selector, project)
        except MachineryUnavailableError:
            continue
        result[installation.selector] = configured[installation.selector]
    return result


def validate_service_configuration(
    service_name: str,
    configuration: str | Mapping[str, object],
    *,
    allow_private_targets: bool = True,
) -> tuple[type[BatchMachineTranslation] | None, SettingsDict, list[str]]:
    """
    Validate given service configuration.

    :param service_name: Name of the service as defined in WEBLATE_MACHINERY
    :param configuration: JSON encoded configuration for the service
    :return: A tuple containing the validated service class, configuration
             and a list of errors
    :raises ValueError: When service is not found or configuration is invalid
    """
    try:
        service = MACHINERY[service_name]
    except KeyError:
        msg = f"Service not found: {service_name}"
        return None, {}, [msg]

    service_configuration: SettingsDict

    if isinstance(configuration, str):
        try:
            parsed_configuration = json.loads(configuration)
        except json.JSONDecodeError as error:
            msg = f"Invalid service configuration ({service_name}): {error}"
            return service, {}, [msg]
        if not isinstance(parsed_configuration, dict):
            msg = f"Invalid service configuration ({service_name}): expected a JSON object"
            return service, {}, [msg]
        service_configuration = cast("SettingsDict", parsed_configuration)
    else:
        service_configuration = cast("SettingsDict", dict(configuration))

    errors = []
    if service.settings_form is not None:
        form = service.settings_form(
            service,
            data=service_configuration,
            allow_private_targets=allow_private_targets,
        )
        # validate form
        if not form.is_valid():
            errors.extend([str(error) for error in form.non_field_errors()])

            for field in form:
                errors.extend(
                    [
                        f"Error in {field.name} ({service_name}): {error}"
                        for error in field.errors
                    ]
                )
        else:
            serialized = form.serialize_form()
            service_configuration = cast(
                "SettingsDict",
                {
                    key: serialized.get(key, value)
                    for key, value in service_configuration.items()
                    if key not in form.fields or key in serialized
                },
            )
    return service, service_configuration, errors
