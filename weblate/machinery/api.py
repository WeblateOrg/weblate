# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from weblate.machinery.models import (
    MachineryExclusion,
    MachineryInstallation,
    validate_service_configuration,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser
    from django.db.models import QuerySet

    from weblate.auth.models import User
    from weblate.trans.models import Project
    from weblate.workspaces.models import Workspace


def can_edit_scope(
    user: User | AnonymousUser,
    *,
    project: Project | None = None,
    workspace: Workspace | None = None,
) -> bool:
    if project is not None:
        return bool(user.has_perm("project.edit", project))
    if workspace is not None:
        return bool(user.has_perm("workspace.edit", workspace))
    return bool(user.has_perm("machinery.edit"))


def editable_scopes(user: User | AnonymousUser) -> Q:
    """Limit installation and exclusion lists to scopes the user can edit."""
    if not user.is_authenticated:
        return Q(pk__in=[])
    if user.is_superuser:
        return Q()
    projects = user.projects_with_perm("project.edit").filter(
        user.get_project_access_query()
    )
    if not user.is_bot and not user.profile.has_2fa:
        projects = projects.exclude(enforced_2fa=True)
    scopes = Q(project__in=projects) | Q(
        workspace_id__in=user.workspace_ids_with_perm("workspace.edit")
    )
    if user.has_perm("machinery.edit"):
        scopes |= Q(project__isnull=True, workspace__isnull=True)
    return scopes


class InstallationSerializer(serializers.ModelSerializer):
    selector = serializers.CharField(read_only=True)
    configuration = serializers.JSONField(required=False)

    class Meta:
        model = MachineryInstallation
        fields = (
            "id",
            "selector",
            "engine",
            "slug",
            "configuration",
            "enabled",
            "workspace",
            "project",
        )
        read_only_fields = ("id", "selector")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        engine = attrs.get("engine", instance.engine if instance else "")
        configuration = attrs.get(
            "configuration", instance.configuration if instance else {}
        )
        workspace = attrs.get("workspace", instance.workspace if instance else None)
        project = attrs.get("project", instance.project if instance else None)
        if not can_edit_scope(
            self.context["request"].user, project=project, workspace=workspace
        ):
            msg = "Cannot manage this installation scope."
            raise PermissionDenied(msg)
        if instance and (
            workspace != instance.workspace or project != instance.project
        ):
            msg = "Installation scope cannot be changed."
            raise serializers.ValidationError(msg)
        if instance and "engine" in attrs and engine != instance.engine:
            msg = "Installation engine cannot be changed."
            raise serializers.ValidationError({"engine": msg})
        if instance is None or "configuration" in attrs:
            if not isinstance(configuration, (dict, str)):
                msg = "Expected a JSON object."
                raise serializers.ValidationError({"configuration": msg})
            service, validated_configuration, errors = validate_service_configuration(
                engine, configuration, allow_private_targets=not (project or workspace)
            )
            if service is None or errors:
                raise serializers.ValidationError({"configuration": errors})
            if not isinstance(validated_configuration, dict):
                msg = "Expected a JSON object."
                raise serializers.ValidationError({"configuration": msg})
            configuration = attrs["configuration"] = validated_configuration
        candidate = copy(instance) if instance is not None else MachineryInstallation()
        candidate.engine = engine
        candidate.slug = attrs.get("slug", instance.slug if instance else "")
        candidate.configuration = configuration
        candidate.enabled = attrs.get("enabled", instance.enabled if instance else True)
        candidate.workspace = workspace
        candidate.project = project
        try:
            candidate.full_clean(exclude=["id"])
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                error.message_dict if hasattr(error, "message_dict") else error.messages
            ) from error
        return attrs


class InstallationViewSet(viewsets.ModelViewSet):
    serializer_class = InstallationSerializer
    queryset = MachineryInstallation.objects.all()

    def get_queryset(self) -> QuerySet[MachineryInstallation]:
        return self.queryset.filter(editable_scopes(self.request.user)).order_by("id")


class ExclusionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineryExclusion
        fields = ("id", "workspace", "project", "installation", "engine")
        read_only_fields = ("id",)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        workspace = attrs.get("workspace", instance.workspace if instance else None)
        project = attrs.get("project", instance.project if instance else None)
        if not can_edit_scope(
            self.context["request"].user, project=project, workspace=workspace
        ):
            msg = "Cannot manage this exclusion scope."
            raise PermissionDenied(msg)
        if instance and (
            workspace != instance.workspace or project != instance.project
        ):
            msg = "Exclusion scope cannot be changed."
            raise serializers.ValidationError(msg)
        candidate = copy(instance) if instance is not None else MachineryExclusion()
        candidate.workspace = workspace
        candidate.project = project
        candidate.installation = attrs.get(
            "installation", instance.installation if instance else None
        )
        candidate.engine = attrs.get("engine", instance.engine if instance else "")
        if instance and (
            candidate.installation_id != instance.installation_id
            or candidate.engine != instance.engine
        ):
            msg = "Exclusion target cannot be changed."
            raise serializers.ValidationError(msg)
        try:
            candidate.full_clean(exclude=["id"])
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                error.message_dict if hasattr(error, "message_dict") else error.messages
            ) from error
        return attrs


class ExclusionViewSet(viewsets.ModelViewSet):
    serializer_class = ExclusionSerializer
    queryset = MachineryExclusion.objects.all()

    def perform_destroy(self, instance: MachineryExclusion) -> None:
        try:
            instance.delete()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error

    def get_queryset(self) -> QuerySet[MachineryExclusion]:
        return self.queryset.filter(editable_scopes(self.request.user)).order_by("id")
