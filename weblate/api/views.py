# Copyright © Michal Čihař <michal@weblate.org>
# SPDX-FileCopyrightText: 2025 Javier Pérez <jdbp@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os.path
from datetime import datetime
from typing import TYPE_CHECKING, cast
from urllib.parse import unquote

from celery.result import AsyncResult
from django.conf import settings
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Model, Q
from django.forms.utils import from_current_timezone
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy
from django_filters import rest_framework as filters
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from drf_standardized_errors.handler import ExceptionHandler
from rest_framework import parsers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, UpdateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_423_LOCKED,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from rest_framework.utils import formatting
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from weblate.accounts.models import Subscription
from weblate.accounts.utils import remove_user
from weblate.addons.models import Addon
from weblate.api.pagination import LargePagination
from weblate.api.serializers import (
    AddonSerializer,
    BasicUserSerializer,
    BilingualSourceUnitSerializer,
    BilingualUnitSerializer,
    CategorySerializer,
    ChangeSerializer,
    ComponentListSerializer,
    ComponentSerializer,
    FullUserSerializer,
    GroupSerializer,
    LabelSerializer,
    LanguageSerializer,
    LockRequestSerializer,
    LockSerializer,
    MemorySerializer,
    MetricsSerializer,
    MonolingualUnitSerializer,
    NewUnitSerializer,
    NotificationSerializer,
    ProjectMachinerySettingsSerializer,
    ProjectSerializer,
    RepoRequestSerializer,
    RoleSerializer,
    ScreenshotCreateSerializer,
    ScreenshotFileSerializer,
    ScreenshotSerializer,
    SingleServiceConfigSerializer,
    StatisticsSerializer,
    TranslationSerializer,
    UnitSerializer,
    UnitWriteSerializer,
    UploadRequestSerializer,
    UserStatisticsSerializer,
    edit_service_settings_response_serializer,
    get_reverse_kwargs,
)
from weblate.auth.models import AuthenticatedHttpRequest, Group, Role, User
from weblate.formats.models import EXPORTERS
from weblate.lang.models import Language
from weblate.machinery.models import validate_service_configuration
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.autotranslate import AutoTranslate
from weblate.trans.exceptions import FileParseError
from weblate.trans.forms import AutoForm
from weblate.trans.models import (
    Category,
    Change,
    Component,
    ComponentList,
    Project,
    Unit,
)
from weblate.trans.models.translation import Translation, TranslationQuerySet
from weblate.trans.tasks import (
    category_removal,
    component_removal,
    project_removal,
)
from weblate.trans.views.files import download_multi
from weblate.trans.views.reports import generate_credits
from weblate.utils.celery import get_task_progress
from weblate.utils.docs import get_doc_url
from weblate.utils.errors import report_error
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.search import parse_query
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_TRANSLATED,
)
from weblate.utils.stats import GlobalStats, prefetch_stats
from weblate.utils.views import download_translation_file, zip_download

from .renderers import FlatJsonRenderer, OpenMetricsRenderer

if TYPE_CHECKING:
    from rest_framework.request import Request

REPO_OPERATIONS = {
    "push": ("vcs.push", "do_push", (), True),
    "pull": ("vcs.update", "do_update", (), True),
    "reset": ("vcs.reset", "do_reset", (), True),
    "cleanup": ("vcs.reset", "do_cleanup", (), True),
    "commit": ("vcs.commit", "commit_pending", ("api",), False),
    "file-sync": ("vcs.reset", "do_file_sync", (), True),
    "file-scan": ("vcs.reset", "do_file_scan", (), True),
}

DOC_TEXT = """
<p>See <a href="{0}">the Weblate's Web API documentation</a> for detailed
description of the API.</p>
"""


class LockedError(APIException):
    status_code = HTTP_423_LOCKED
    default_detail = gettext_lazy("Could not obtain the lock to perform the operation.")
    default_code = "unknown-locked"


class NotSourceUnit(APIException):
    status_code = HTTP_400_BAD_REQUEST
    default_detail = gettext_lazy("Specified unit id is not a translation source unit.")
    default_code = "not-a-source-unit"


class WeblateExceptionHandler(ExceptionHandler):
    def convert_known_exceptions(self, exc: Exception) -> Exception:
        if isinstance(exc, WeblateLockTimeoutError):
            if exc.lock.scope == "repo":
                return LockedError(
                    code="repository-locked",
                    detail=gettext(
                        "Could not obtain the repository lock for %s to perform the operation."
                    )
                    % exc.lock.origin,
                )
            if exc.lock.scope == "component-update":
                return LockedError(
                    code="component-locked",
                    detail=gettext(
                        "Could not obtain the update lock for component %s to perform the operation."
                    )
                    % exc.lock.origin,
                )
            if exc.lock.origin:
                return LockedError(
                    detail=gettext(
                        "Could not obtain the %(scope)s lock for %(origin)s to perform the operation."
                    )
                    % {"scope": exc.lock.scope, "origin": exc.lock.origin},
                )
            return LockedError()
        return super().convert_known_exceptions(exc)


def get_view_description(view, html=False):
    """
    Given a view class, return a textual description to represent the view.

    This name is used in the browsable API, and in OPTIONS responses. This function is
    the default for the `VIEW_DESCRIPTION_FUNCTION` setting.
    """
    description = view.__doc__ or ""
    description = formatting.dedent(description)

    if hasattr(getattr(view, "serializer_class", "None"), "Meta"):
        model_name = view.serializer_class.Meta.model.__name__.lower()
        doc_name = "categories" if model_name == "category" else f"{model_name}s"
        doc_url = get_doc_url("api", doc_name, user=view.request.user)
    else:
        doc_url = get_doc_url("api", user=view.request.user)

    if html:
        return formatting.markup_description(description) + format_html(
            DOC_TEXT, doc_url
        )
    return description


class DownloadViewSet(viewsets.ReadOnlyModelViewSet):
    raw_urls: tuple[str, ...] = ()
    raw_formats: tuple[str, ...] = tuple(EXPORTERS)

    def perform_content_negotiation(self, request: Request, force=False):
        """Perform custom content negotiation."""
        if (
            request.resolver_match is not None
            and request.resolver_match.url_name in self.raw_urls
        ):
            fmt = self.format_kwarg
            if fmt is None or fmt in self.raw_formats:
                renderers = self.get_renderers()
                return (renderers[0], renderers[0].media_type)
            msg = "Not supported format"
            raise Http404(msg)
        return super().perform_content_negotiation(request, force)

    def download_file(self, filename, content_type, component=None):
        """Download file."""
        if os.path.isdir(filename):
            response = zip_download(filename, [filename])
            basename = component.slug if component else "weblate"
            filename = f"{basename}.zip"
        else:
            try:
                response = FileResponse(
                    open(filename, "rb"),  # noqa: SIM115
                    content_type=content_type,
                )
            except FileNotFoundError as error:
                msg = "File not found"
                raise Http404(msg) from error
            filename = os.path.basename(filename)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class WeblateViewSet(DownloadViewSet):
    """Allow to skip content negotiation for certain requests."""

    def repository_operation(
        self, request: Request, obj, project: Project, operation: str
    ):
        permission, method, args, takes_request = REPO_OPERATIONS[operation]

        if not request.user.has_perm(permission, project):
            raise PermissionDenied

        obj.acting_user = request.user

        if takes_request:
            return getattr(obj, method)(*args, request)
        return getattr(obj, method)(*args, request.user)

    @extend_schema(
        description="Return information about VCS repository status.", methods=["get"]
    )
    @extend_schema(
        description="Perform given operation on the VCS repository.", methods=["post"]
    )
    @action(
        detail=True, methods=["get", "post"], serializer_class=RepoRequestSerializer
    )
    def repository(self, request: Request, **kwargs):
        obj = self.get_object()

        if isinstance(obj, Translation):
            project = obj.component.project
        elif isinstance(obj, Component):
            project = obj.project
        else:
            project = obj

        if request.method == "POST":
            serializer = RepoRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            data = {
                "result": self.repository_operation(
                    request, obj, project, serializer.validated_data["operation"]
                )
            }

            storage = get_messages(request)
            if storage:
                data["detail"] = "\n".join(m.message for m in storage)

            return Response(data)

        if not request.user.has_perm("meta:vcs.status", project):
            raise PermissionDenied

        data = {
            "needs_commit": obj.needs_commit(),
            "needs_merge": obj.repo_needs_merge(),
            "needs_push": obj.repo_needs_push(),
        }

        if isinstance(obj, Project):
            data["url"] = reverse(
                "api:project-repository", kwargs={"slug": obj.slug}, request=request
            )
        else:
            if isinstance(obj, Translation):
                component = obj.component
                data["url"] = reverse(
                    "api:translation-repository",
                    kwargs=get_reverse_kwargs(
                        obj,
                        (
                            "component__project__slug",
                            "component__slug",
                            "language__code",
                        ),
                    ),
                    request=request,
                )
            else:
                component = obj
                data["url"] = reverse(
                    "api:component-repository",
                    kwargs=get_reverse_kwargs(obj, ("project__slug", "slug")),
                    request=request,
                )

            data["remote_commit"] = component.get_last_remote_commit()
            data["weblate_commit"] = component.get_last_commit()
            data["status"] = component.repository.status()
            changes = component.change_set.filter(
                action__in=Change.ACTIONS_REPOSITORY
            ).order_by("-id")

            if changes.exists() and changes[0].is_merge_failure():
                data["merge_failure"] = changes[0].target
            else:
                data["merge_failure"] = None

        return Response(data)


class MultipleFieldViewSet(WeblateViewSet):
    """
    Multiple field filtering mixin.

    Apply this mixin to any view or viewset to get multiple field filtering based on a
    `lookup_fields` attribute, instead of the default single field filtering.
    """

    def get_object(self):
        # Get the base queryset
        queryset = self.get_queryset()
        # Apply any filter backends
        queryset = self.filter_queryset(queryset)
        # Generate lookup
        lookup = {}
        category_path = ""
        for field in reversed(self.lookup_fields):
            if field not in {"component__slug", "slug"}:
                lookup[field] = self.kwargs[field]
            else:
                category_prefix = field[:-4]
                was_category = False
                was_slug = False
                # Fetch component part for possible category
                for category in reversed(unquote(self.kwargs[field]).split("/")):
                    if not was_slug:
                        # Component filter
                        lookup[field] = category
                        was_slug = True
                    else:
                        # Strip "slug" from category field
                        category_path = f"category__{category_path}"
                        lookup[f"{category_prefix}{category_path}slug"] = category
                        was_category = True
                if not was_category:
                    # No category
                    lookup[f"{category_prefix}category"] = None

        # Lookup the object
        return get_object_or_404(queryset, **lookup)


class UserFilter(filters.FilterSet):
    username = filters.CharFilter(field_name="username", lookup_expr="startswith")

    class Meta:
        model = User
        fields = ["username", "id"]


@extend_schema_view(
    retrieve=extend_schema(description="Return information about users."),
    partial_update=extend_schema(description="Change the user parameters."),
)
class UserViewSet(viewsets.ModelViewSet):
    """Users API."""

    queryset = User.objects.none()
    lookup_field = "username"
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = UserFilter

    def get_serializer_class(self):
        if self.request.user.has_perm("user.edit"):
            return FullUserSerializer
        return BasicUserSerializer

    def get_queryset(self):
        queryset = User.objects.order_by("id")
        if not self.request.user.has_perm("user.edit"):
            return queryset
        return queryset.prefetch_related("groups")

    def perm_check(self, request: Request) -> None:
        if not request.user.has_perm("user.edit"):
            self.permission_denied(request, "Can not manage Users")

    def update(self, request: Request, *args, **kwargs):
        """Change the user parameters."""
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        """Create a new user."""
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete all user information and mark the user inactive."""
        self.perm_check(request)
        instance = self.get_object()
        remove_user(instance, cast("AuthenticatedHttpRequest", request))
        return Response(status=HTTP_204_NO_CONTENT)

    @extend_schema(description="Associate groups with a user.", methods=["post"])
    @extend_schema(description="Remove a user from a group.", methods=["delete"])
    @action(detail=True, methods=["post", "delete"])
    def groups(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "group_id" not in request.data:
            msg = "Missing group_id parameter"
            raise ValidationError({"group_id": msg})

        try:
            group = Group.objects.get(pk=int(request.data["group_id"]))
        except (Group.DoesNotExist, ValueError) as error:
            raise ValidationError({"group_id": str(error)}) from error

        if request.method == "POST":
            obj.add_team(request, group)
        if request.method == "DELETE":
            obj.remove_team(request, group)
        serializer = self.get_serializer_class()(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @extend_schema(description="List subscriptions of a user.", methods=["get"])
    @extend_schema(description="Associate subscriptions with a user.", methods=["post"])
    @extend_schema(
        request=NotificationSerializer,
        responses=NotificationSerializer(many=True),
    )
    @action(
        detail=True,
        methods=["get", "post"],
        serializer_class=NotificationSerializer(many=True),
    )
    def notifications(self, request: Request, username: str):
        obj = self.get_object()
        if request.method == "POST":
            self.perm_check(request)
            with transaction.atomic():
                serializer = NotificationSerializer(
                    data=request.data, context={"request": request}
                )
                serializer.is_valid(raise_exception=True)
                serializer.save(user=obj)
                return Response(serializer.data, status=HTTP_201_CREATED)
        queryset = obj.subscription_set.order_by("id")
        page = self.paginate_queryset(queryset)
        serializer = NotificationSerializer(
            page, many=True, context={"request": request}
        )
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        description="Get a subscription associated with a user.", methods=["get"]
    )
    @extend_schema(
        description="Edit a subscription associated with a user.",
        methods=["put", "patch"],
    )
    @extend_schema(
        description="Delete a subscription associated with a user.", methods=["delete"]
    )
    @extend_schema(
        parameters=[
            OpenApiParameter("subscription_id", int, OpenApiParameter.PATH),
        ],
        responses=NotificationSerializer,
        request=NotificationSerializer,
    )
    @action(
        detail=True,
        methods=["get", "put", "patch", "delete"],
        url_path="notifications/(?P<subscription_id>[0-9]+)",
        serializer_class=NotificationSerializer,
    )
    def notifications_details(
        self, request: Request, username: str, subscription_id: int
    ):
        obj = self.get_object()

        try:
            subscription = obj.subscription_set.get(id=subscription_id)
        except Subscription.DoesNotExist as error:
            raise Http404(str(error)) from error

        if request.method == "DELETE":
            self.perm_check(request)
            subscription.delete()
            return Response(status=HTTP_204_NO_CONTENT)

        if request.method == "GET":
            serializer = NotificationSerializer(
                subscription, context={"request": request}
            )
        else:
            self.perm_check(request)
            serializer = NotificationSerializer(
                subscription,
                data=request.data,
                context={"request": request},
                partial=request.method == "PATCH",
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

        return Response(serializer.data, status=HTTP_200_OK)

    @extend_schema(
        description="List statistics of a user.",
        methods=["get"],
        tags=["users", "statistics"],
    )
    @action(
        detail=True,
        methods=["get"],
        renderer_classes=(*api_settings.DEFAULT_RENDERER_CLASSES, FlatJsonRenderer),
    )
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = UserStatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)


@extend_schema_view(
    retrieve=extend_schema(description="Return information about a group."),
    partial_update=extend_schema(description="Change the group parameters."),
)
class GroupViewSet(viewsets.ModelViewSet):
    """Groups API."""

    queryset = Group.objects.none()
    serializer_class = GroupSerializer
    lookup_field = "id"

    def get_queryset(self):
        if self.request.user.has_perm("group.edit"):
            return Group.objects.order_by("id")
        return self.request.user.groups.order_by(
            "id"
        ) | self.request.user.administered_group_set.order_by("id")

    def perm_check(self, request: Request, group: Group | None = None) -> None:
        if (group is None and not self.request.user.has_perm("group.edit")) or (
            group is not None and not request.user.has_perm("meta:team.edit", group)
        ):
            self.permission_denied(request, "Can not manage groups")

    def update(self, request: Request, *args, **kwargs):
        """Change the group parameters."""
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        """Create a new group."""
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete the group."""
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(description="Associate roles with a group.", methods=["post"])
    @action(detail=True, methods=["post"])
    def roles(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "role_id" not in request.data:
            msg = "Missing role_id parameter"
            raise ValidationError({"role_id": msg})

        try:
            role = Role.objects.get(pk=int(request.data["role_id"]))
        except (Role.DoesNotExist, ValueError) as error:
            raise ValidationError({"role_id": str(error)}) from error

        obj.roles.add(role)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @extend_schema(
        description="Delete a role from a group.",
        methods=["delete"],
        parameters=[OpenApiParameter("role_id", int, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["delete"], url_path="roles/(?P<role_id>[0-9]+)")
    def delete_roles(self, request: Request, id, role_id):  # noqa: A002
        obj = self.get_object()
        self.perm_check(request)

        try:
            role = obj.roles.get(pk=role_id)
        except Role.DoesNotExist as error:
            raise Http404(str(error)) from error

        obj.roles.remove(role)
        return Response(status=HTTP_204_NO_CONTENT)

    @extend_schema(description="Associate languages with a group.", methods=["post"])
    @action(
        detail=True,
        methods=["post"],
    )
    def languages(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "language_code" not in request.data:
            msg = "Missing language_code parameter"
            raise ValidationError({"language_code": msg})

        try:
            language = Language.objects.get(code=request.data["language_code"])
        except (Language.DoesNotExist, ValueError) as error:
            raise ValidationError({"language_code": str(error)}) from error

        obj.languages.add(language)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @extend_schema(
        description="Delete a language from a group.",
        methods=["delete"],
        parameters=[OpenApiParameter("language_code", str, OpenApiParameter.PATH)],
    )
    @action(
        detail=True, methods=["delete"], url_path="languages/(?P<language_code>[^/.]+)"
    )
    def delete_languages(self, request: Request, id, language_code):  # noqa: A002
        obj = self.get_object()
        self.perm_check(request)

        try:
            language = obj.languages.get(code=language_code)
        except Language.DoesNotExist as error:
            raise Http404(str(error)) from error
        obj.languages.remove(language)
        return Response(status=HTTP_204_NO_CONTENT)

    @extend_schema(description="Associate projects with a group.", methods=["post"])
    @action(
        detail=True,
        methods=["post"],
    )
    def projects(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "project_id" not in request.data:
            msg = "Missing project_id parameter"
            raise ValidationError({"project_id": msg})

        try:
            project = Project.objects.get(
                pk=int(request.data["project_id"]),
            )
        except (Project.DoesNotExist, ValueError) as error:
            raise ValidationError({"project_id": str(error)}) from error
        obj.projects.add(project)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @extend_schema(description="Delete a project from a group.", methods=["delete"])
    @action(detail=True, methods=["delete"], url_path="projects/(?P<project_id>[0-9]+)")
    def delete_projects(self, request: Request, id, project_id):  # noqa: A002
        obj = self.get_object()
        self.perm_check(request)

        try:
            project = obj.projects.get(pk=project_id)
        except Project.DoesNotExist as error:
            raise Http404(str(error)) from error
        obj.projects.remove(project)
        return Response(status=HTTP_204_NO_CONTENT)

    @extend_schema(
        description="Associate componentlists with a group.", methods=["post"]
    )
    @action(detail=True, methods=["post"])
    def componentlists(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "component_list_id" not in request.data:
            msg = "Missing component_list_id parameter"
            raise ValidationError({"component_list_id": msg})

        try:
            component_list = ComponentList.objects.get(
                pk=int(request.data["component_list_id"]),
            )
        except (ComponentList.DoesNotExist, ValueError) as error:
            raise ValidationError({"component_list_id": str(error)}) from error
        obj.componentlists.add(component_list)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @extend_schema(
        description="Delete a componentlist from a group.", methods=["delete"]
    )
    @action(
        detail=True,
        methods=["delete"],
        url_path="componentlists/(?P<component_list_id>[0-9]+)",
    )
    def delete_componentlists(
        self,
        request: Request,
        id,  # noqa: A002
        component_list_id,
    ):
        obj = self.get_object()
        self.perm_check(request)
        try:
            component_list = obj.componentlists.get(pk=component_list_id)
        except ComponentList.DoesNotExist as error:
            raise Http404(str(error)) from error
        obj.componentlists.remove(component_list)
        return Response(status=HTTP_204_NO_CONTENT)

    @extend_schema(description="Associate components with a group.", methods=["post"])
    @action(
        detail=True,
        methods=["post"],
    )
    def components(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)
        if "component_id" not in request.data:
            msg = "Missing component_id parameter"
            raise ValidationError({"component_id": msg})

        try:
            component = Component.objects.filter_access(request.user).get(
                pk=int(request.data["component_id"])
            )
        except (Component.DoesNotExist, ValueError) as error:
            raise ValidationError({"component_id": str(error)}) from error
        obj.components.add(component)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @extend_schema(description="Delete a component from a group.", methods=["delete"])
    @action(
        detail=True, methods=["delete"], url_path="components/(?P<component_id>[0-9]+)"
    )
    def delete_components(self, request: Request, id, component_id):  # noqa: A002
        obj = self.get_object()
        self.perm_check(request)

        try:
            component = obj.components.get(pk=component_id)
        except Component.DoesNotExist as error:
            raise Http404(str(error)) from error
        obj.components.remove(component)
        return Response(status=HTTP_204_NO_CONTENT)

    @extend_schema(description="Make user a group admin.", methods=["post"])
    @action(detail=True, methods=["post"], url_path="admins")
    def grant_admin(self, request: Request, id):  # noqa: A002
        group = self.get_object()
        self.perm_check(request, group)
        user_id = request.data.get("user_id")
        if not user_id:
            msg = "User ID is required"
            raise ValidationError({"user_id": msg})

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist as error:
            msg = "User not found"
            raise ValidationError({"user_id": msg}) from error
        group.admins.add(user)
        user.add_team(cast("AuthenticatedHttpRequest", request), group)
        return Response({"Administration rights granted."}, status=HTTP_200_OK)

    @extend_schema(description="Delete a user from group admins.", methods=["delete"])
    @action(detail=True, methods=["delete"], url_path="admins/(?P<user_pk>[0-9]+)")
    def revoke_admin(self, request: Request, id, user_pk):  # noqa: A002
        group = self.get_object()
        self.perm_check(request, group)
        try:
            user = group.admins.get(pk=user_pk)  # Using user_pk from the URL path
        except User.DoesNotExist as error:
            msg = "User not found"
            raise ValidationError(msg) from error

        group.admins.remove(user)
        serializer = GroupSerializer(group, context={"request": request})
        return Response(serializer.data, status=HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        description="Return a list of all roles associated with the user."
    ),
    retrieve=extend_schema(description="Return information about a role."),
    partial_update=extend_schema(description="Change the role parameters."),
)
class RoleViewSet(viewsets.ModelViewSet):
    """Roles API."""

    queryset = Role.objects.none()
    serializer_class = RoleSerializer
    lookup_field = "id"

    def get_queryset(self):
        if self.request.user.has_perm("role.edit"):
            return Role.objects.order_by("id").all()
        return (
            Role.objects.filter(group__in=self.request.user.groups.all())
            .order_by("id")
            .distinct()
        )

    def perm_check(self, request: Request) -> None:
        if not request.user.has_perm("role.edit"):
            self.permission_denied(request, "Can not manage roles")

    def update(self, request: Request, *args, **kwargs):
        """Change the role parameters."""
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        """Create a new role."""
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete a role."""
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)


class CreditsMixin:
    @action(detail=True, methods=["get"])
    def credits(self, request, **kwargs):
        if request.user.is_anonymous:
            self.permission_denied(request, "Must be authenticated to get credits")

        obj = self.get_object()

        try:
            start_date = from_current_timezone(
                datetime.fromisoformat(request.query_params["start"])
            )
        except (ValueError, MultiValueDictKeyError) as err:
            msg = "Invalid format for `start`"
            raise ValidationError({"start": msg}) from err

        try:
            end_date = from_current_timezone(
                datetime.fromisoformat(request.query_params["end"])
            )
        except (ValueError, MultiValueDictKeyError) as err:
            msg = "Invalid format for `end`"
            raise ValidationError({"end": msg}) from err

        language = None

        if "lang" in request.query_params:
            language = request.query_params["lang"]

        data = generate_credits(
            None if request.user.has_perm("reports.view", obj) else request.user,
            start_date,
            end_date,
            language,
            obj,
            "count",
            "descending",
        )
        return Response(data=data)


@extend_schema_view(
    list=extend_schema(description="Return a list of all projects."),
    retrieve=extend_schema(description="Return information about a project."),
    partial_update=extend_schema(description="Edit a project by a PATCH request."),
    credits=extend_schema(description="Return contributor credits for a project."),
)
class ProjectViewSet(
    WeblateViewSet, UpdateModelMixin, CreateModelMixin, DestroyModelMixin, CreditsMixin
):
    """Translation projects API."""

    raw_urls: tuple[str, ...] = "project-file"
    raw_formats = ("zip", *(f"zip:{exporter}" for exporter in EXPORTERS))

    queryset = Project.objects.none()
    serializer_class = ProjectSerializer
    lookup_field = "slug"
    request: Request  # type: ignore[assignment]

    def get_queryset(self):
        return self.request.user.allowed_projects.prefetch_related(
            "addon_set"
        ).order_by("id")

    @extend_schema(
        description="Return a list of translation components in the given project.",
        methods=["get"],
    )
    @extend_schema(
        description="Create translation components in the given project.",
        methods=["post"],
    )
    @action(
        detail=True,
        methods=["get", "post"],
        parser_classes=(
            parsers.JSONParser,
            parsers.MultiPartParser,
            parsers.FormParser,
            parsers.FileUploadParser,
        ),
        serializer_class=ComponentSerializer,
    )
    def components(self, request: Request, **kwargs):
        obj = self.get_object()
        if request.method == "POST":
            if not request.user.has_perm("project.edit", obj):
                self.permission_denied(request, "Can not create components")
            with transaction.atomic():
                serializer = ComponentSerializer(
                    data=request.data, context={"request": request, "project": obj}
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
                serializer.instance.post_create(self.request.user)
                return Response(
                    serializer.data,
                    status=HTTP_201_CREATED,
                    headers={
                        "Location": str(serializer.data[api_settings.URL_FIELD_NAME])
                    },
                )

        queryset = obj.component_set.filter_access(self.request.user).order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = ComponentSerializer(
            page, many=True, context={"request": request}, remove_fields=("project",)
        )

        return self.get_paginated_response(serializer.data)

    @extend_schema(description="Return categories for a project.", methods=["get"])
    @action(detail=True, methods=["get"])
    def categories(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.category_set.order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = CategorySerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @extend_schema(
        description="Return statistics for a project.",
        methods=["get"],
        tags=["projects", "statistics"],
    )
    @action(
        detail=True,
        methods=["get"],
        renderer_classes=(*api_settings.DEFAULT_RENDERER_CLASSES, FlatJsonRenderer),
    )
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)

    @extend_schema(
        description="Return paginated statistics for all languages within a project.",
        methods=["get"],
        tags=["projects", "statistics"],
    )
    @action(
        detail=True,
        methods=["get"],
        renderer_classes=(*api_settings.DEFAULT_RENDERER_CLASSES, FlatJsonRenderer),
    )
    def languages(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(
            obj.stats.get_language_stats(), many=True, context={"request": request}
        )

        return Response(serializer.data)

    @extend_schema(description="Return a list of project changes.", methods=["get"])
    @action(detail=True, methods=["get"])
    def changes(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.change_set.prefetch().order()
        queryset = ChangesFilterBackend().filter_queryset(request, queryset, self)
        page = self.paginate_queryset(queryset)

        serializer = ChangeSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @extend_schema(description="Return labels for a project.", methods=["get"])
    @extend_schema(description="Create a label for a project.", methods=["post"])
    @action(detail=True, methods=["get", "post"])
    def labels(self, request: Request, **kwargs):
        obj = self.get_object()

        if request.method == "POST":
            if not request.user.has_perm("project.edit", obj):
                self.permission_denied(request, "Can not create labels")
            with transaction.atomic():
                serializer = LabelSerializer(
                    data=request.data, context={"request": request, "project": obj}
                )
                serializer.is_valid(raise_exception=True)
                serializer.save(project=obj)
                return Response(
                    serializer.data,
                    status=HTTP_201_CREATED,
                )

        queryset = obj.label_set.all().order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = LabelSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"])
    def addons(self, request: Request, **kwargs):
        obj = self.get_object()
        obj.acting_user = request.user

        if not request.user.has_perm("project.edit", obj):
            self.permission_denied(request, "Can not create addon")

        serializer = AddonSerializer(
            data=request.data, context={"request": request, "project": obj}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(project=obj)
        return Response(serializer.data, status=HTTP_201_CREATED)

    def create(self, request: Request, *args, **kwargs):
        """Create a new project."""
        if not request.user.has_perm("project.add"):
            self.permission_denied(request, "Can not create projects")
        self.request = request
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer) -> None:
        with transaction.atomic():
            super().perform_create(serializer)
            if (
                not self.request.user.is_superuser
                and "weblate.billing" in settings.INSTALLED_APPS
            ):
                from weblate.billing.models import Billing

                try:
                    billing = Billing.objects.get_valid().for_user(self.request.user)[0]
                except IndexError:
                    billing = None
            else:
                billing = None
            serializer.instance.post_create(self.request.user, billing)

    def update(self, request: Request, *args, **kwargs):
        """Edit a project by a PUT request."""
        instance = self.get_object()
        if not request.user.has_perm("project.edit", instance):
            self.permission_denied(request, "Can not edit project")
        instance.acting_user = request.user
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete a project."""
        instance = self.get_object()
        if not request.user.has_perm("project.edit", instance):
            self.permission_denied(request, "Can not delete project")
        instance.acting_user = request.user
        project_removal.delay(instance.pk, request.user.pk)
        return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def file(self, request: Request, **kwargs):
        instance = self.get_object()

        if not request.user.has_perm("translation.download", instance):
            raise PermissionDenied

        components = instance.component_set.filter_access(request.user)
        requested_format = request.query_params.get("format", "zip")
        requested_language = request.query_params.get("language_code", None)

        if requested_language:
            translations = Translation.objects.filter(
                language__code=requested_language, component__in=components
            )
        else:
            translations = Translation.objects.filter(component__in=components)

        return download_multi(
            cast("AuthenticatedHttpRequest", request),
            translations.prefetch(),
            [instance],
            requested_format,
            name=instance.slug,
        )

    @extend_schema(
        responses=ProjectMachinerySettingsSerializer,
        methods=["GET"],
        description="List machinery settings for a project.",
    )
    @extend_schema(
        request=SingleServiceConfigSerializer,
        responses=edit_service_settings_response_serializer("post", 201, 400),
        methods=["POST"],
        description="Install a new machinery service.",
    )
    @extend_schema(
        request=SingleServiceConfigSerializer,
        responses=edit_service_settings_response_serializer("patch", 200, 400),
        methods=["PATCH"],
        description="Partially update a single service. Leave configuration blank to remove the service.",
    )
    @extend_schema(
        request=ProjectMachinerySettingsSerializer,
        responses=edit_service_settings_response_serializer("put", 200, 400),
        methods=["PUT"],
        description="Replace configuration for all services.",
    )
    @action(detail=True, methods=["get", "post", "patch", "put"])
    def machinery_settings(self, request: Request, **kwargs):
        """List or create/update machinery configuration for a project."""
        project = self.get_object()

        if not request.user.has_perm("project.edit", project):
            self.permission_denied(
                request, "Can not retrieve/edit machinery configuration"
            )

        if request.method in {"POST", "PATCH"}:
            try:
                service_name = request.data["service"]
            except KeyError as error:
                raise ValidationError({"service": "Missing service name"}) from error

            service, configuration, errors = validate_service_configuration(
                service_name, request.data.get("configuration", "{}")
            )

            if service is None or errors:
                raise ValidationError({"configuration": errors})

            if request.method == "PATCH":
                if configuration:
                    # update a configuration
                    project.machinery_settings[service_name] = configuration
                    project.save(update_fields=["machinery_settings"])
                    return Response(
                        {"message": f"Service updated: {service.name}"},
                        status=HTTP_200_OK,
                    )
                # remove a configuration
                project.machinery_settings.pop(service_name, None)
                project.save(update_fields=["machinery_settings"])
                return Response(
                    {"message": f"Service removed: {service.name}"},
                    status=HTTP_200_OK,
                )

            if request.method == "POST":
                if service_name in project.machinery_settings:
                    raise ValidationError({"service": ["Service already exists"]})

                project.machinery_settings[service_name] = configuration
                project.save(update_fields=["machinery_settings"])
                return Response(
                    {"message": f"Service installed: {service.name}"},
                    status=HTTP_201_CREATED,
                )

        elif request.method == "PUT":
            # replace all service configuration
            valid_configurations: dict[str, dict] = {}
            for service_name, configuration in request.data.items():
                service, configuration, errors = validate_service_configuration(
                    service_name, configuration
                )

                if service is None or errors:
                    raise ValidationError({"configuration": errors})

                valid_configurations[service_name] = configuration

            project.machinery_settings = valid_configurations
            project.save(update_fields=["machinery_settings"])
            return Response(
                {
                    "message": f"Services installed: {', '.join(valid_configurations.keys())}"
                },
                status=HTTP_201_CREATED,
            )

        # GET method
        return Response(
            data=ProjectMachinerySettingsSerializer(project).data,
            status=HTTP_200_OK,
        )


@extend_schema_view(
    list=extend_schema(description="Return a list of translation components."),
    retrieve=extend_schema(
        description="Return information about translation component."
    ),
    partial_update=extend_schema(description="Edit a component by a PATCH request."),
)
class ComponentViewSet(
    MultipleFieldViewSet, UpdateModelMixin, DestroyModelMixin, CreditsMixin
):
    """Translation components API."""

    raw_urls: tuple[str, ...] = ("component-file",)
    raw_formats = ("zip", *(f"zip:{exporter}" for exporter in EXPORTERS))

    queryset = Component.objects.none()
    serializer_class = ComponentSerializer
    lookup_fields = ("project__slug", "slug")

    def get_queryset(self):
        return (
            Component.objects.prefetch(defer=False)
            .filter_access(self.request.user)
            .prefetch_related("source_language", "addon_set")
            .order_by("id")
        )

    @extend_schema(description="Return component lock status.", methods=["get"])
    @extend_schema(description="Sets component lock status.", methods=["post"])
    @action(
        detail=True, methods=["get", "post"], serializer_class=LockRequestSerializer
    )
    def lock(self, request: Request, **kwargs):
        obj = self.get_object()

        if request.method == "POST":
            if not request.user.has_perm("component.lock", obj):
                raise PermissionDenied

            serializer = LockRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            obj.do_lock(request.user, serializer.validated_data["lock"])

        return Response(data=LockSerializer(obj).data)

    @extend_schema(
        description="Download base file for monolingual translations.", methods=["get"]
    )
    @action(detail=True, methods=["get"])
    def monolingual_base(self, request: Request, **kwargs):
        obj = self.get_object()

        if not obj.has_template():
            msg = "No template found!"
            raise Http404(msg)

        return self.download_file(
            obj.get_template_filename(), obj.template_store.mimetype(), component=obj
        )

    @extend_schema(
        description="Download template file for new translations.", methods=["get"]
    )
    @action(detail=True, methods=["get"])
    def new_template(self, request: Request, **kwargs):
        obj = self.get_object()

        if not obj.new_base:
            msg = "No file found!"
            raise Http404(msg)

        return self.download_file(obj.get_new_base_filename(), "application/binary")

    @extend_schema(
        description="Return a list of translation objects in the given component.",
        methods=["get"],
    )
    @extend_schema(
        description="Create a new translation in the given component.", methods=["post"]
    )
    @action(detail=True, methods=["get", "post"])
    def translations(self, request: Request, **kwargs):
        obj = self.get_object()

        if request.method == "POST":
            if not request.user.has_perm("translation.add", obj):
                self.permission_denied(request, "Can not create translation")

            if "language_code" not in request.data:
                msg = "Missing 'language_code' parameter"
                raise ValidationError({"languge_code": msg})

            language_code = request.data["language_code"]

            try:
                language = Language.objects.get(code=language_code)
            except Language.DoesNotExist as error:
                msg = f"No language code {language_code!r} found!"
                raise ValidationError({"language_code": msg}) from error

            if not obj.can_add_new_language(request.user):
                self.permission_denied(request, message=obj.new_lang_error_message)

            translation = obj.add_new_language(language, request)
            if translation is None:
                storage = get_messages(request)
                if storage:
                    message = "\n".join(m.message for m in storage)
                else:
                    message = f"Could not add {language_code!r}!"
                raise ValidationError({"language_code": message})

            serializer = TranslationSerializer(
                translation, context={"request": request}, remove_fields=("component",)
            )

            return Response(data={"data": serializer.data}, status=HTTP_201_CREATED)

        queryset = obj.translation_set.prefetch().prefetch_plurals().order_by("id")
        page = self.paginate_queryset(queryset)

        # Prefetch workflow settings
        if page:
            page[0].component.project.project_languages.preload_workflow_settings()

        serializer = TranslationSerializer(
            prefetch_stats(page),
            many=True,
            context={"request": request},
            remove_fields=("component",),
        )

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"])
    def addons(self, request: Request, **kwargs):
        obj = self.get_object()
        obj.acting_user = request.user

        if not request.user.has_perm("component.edit", obj):
            self.permission_denied(request, "Can not create addon")

        serializer = AddonSerializer(
            data=request.data, context={"request": request, "component": obj}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(component=obj)
        return Response(serializer.data, status=HTTP_201_CREATED)

    @extend_schema(
        description="Return paginated statistics for all translations within component.",
        methods=["get"],
        tags=["components", "statistics"],
    )
    @action(
        detail=True,
        methods=["get"],
        renderer_classes=(*api_settings.DEFAULT_RENDERER_CLASSES, FlatJsonRenderer),
    )
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.translation_set.all().prefetch_meta().order_by("id")

        paginator = LargePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        serializer = StatisticsSerializer(
            prefetch_stats(page), many=True, context={"request": request}
        )

        return paginator.get_paginated_response(serializer.data)

    @extend_schema(description="Return a list of component changes.", methods=["get"])
    @action(detail=True, methods=["get"])
    def changes(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.change_set.prefetch().order()
        queryset = ChangesFilterBackend().filter_queryset(request, queryset, self)
        page = self.paginate_queryset(queryset)

        serializer = ChangeSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @extend_schema(
        description="Return a list of component screenshots.", methods=["get"]
    )
    @action(detail=True, methods=["get"])
    def screenshots(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = Screenshot.objects.filter(translation__component=obj).order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = ScreenshotSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    def update(self, request: Request, *args, **kwargs):
        """Edit a component by a PUT request."""
        instance = self.get_object()
        if not request.user.has_perm("component.edit", instance):
            self.permission_denied(request, "Can not edit component")
        instance.acting_user = request.user
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete a component."""
        instance = self.get_object()
        if not request.user.has_perm("component.edit", instance):
            self.permission_denied(request, "Can not delete component")
        instance.acting_user = request.user
        component_removal.delay(instance.pk, request.user.pk)
        return Response(status=HTTP_204_NO_CONTENT)

    def add_link(self, request: Request, instance: Component):
        if not request.user.has_perm("component.edit", instance):
            self.permission_denied(request, "Can not edit component")
        if "project_slug" not in request.data:
            msg = "Missing 'project_slug' parameter"
            raise ValidationError({"project_slug": msg})

        project_slug = request.data["project_slug"]

        try:
            project = request.user.allowed_projects.exclude(pk=instance.project_id).get(
                slug=project_slug
            )
        except Project.DoesNotExist as error:
            msg = f"No project slug {project_slug!r} found!"
            raise ValidationError({"project_slug": msg}) from error

        instance.links.add(project)
        serializer = self.serializer_class(instance, context={"request": request})

        return Response(data={"data": serializer.data}, status=HTTP_201_CREATED)

    @extend_schema(
        description="Return projects linked with a component.", methods=["get"]
    )
    @extend_schema(description="Associate project with a component.", methods=["post"])
    @action(detail=True, methods=["get", "post"])
    def links(self, request: Request, **kwargs):
        instance = self.get_object()
        if request.method == "POST":
            return self.add_link(request, instance)

        queryset = instance.links.order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = ProjectSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @extend_schema(
        description="Remove association of a project with a component.",
        methods=["delete"],
        parameters=[OpenApiParameter("project_slug", str, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["delete"], url_path="links/(?P<project_slug>[^/.]+)")
    def delete_links(self, request: Request, project__slug, slug, project_slug):
        instance = self.get_object()
        if not request.user.has_perm("component.edit", instance):
            self.permission_denied(request, "Can not edit component")

        try:
            project = instance.links.get(slug=project_slug)
        except Project.DoesNotExist as error:
            msg = "Project not found"
            raise Http404(msg) from error
        instance.links.remove(project)
        return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def file(self, request: Request, **kwargs):
        # Implementation is analogous to files#download_component, but we can't reuse
        #  that here because the lookup for the component is different
        instance = self.get_object()
        if not request.user.has_perm("translation.download", instance):
            self.permission_denied(
                request, "Can not download all translations for the component"
            )

        requested_format = request.query_params.get("format", "zip")
        return download_multi(
            cast("AuthenticatedHttpRequest", request),
            instance.translation_set.prefetch_meta(),
            [instance],
            requested_format,
            name=instance.full_slug.replace("/", "-"),
        )


@extend_schema_view(
    list=extend_schema(description="Return a list of memory results."),
)
class MemoryViewSet(viewsets.ModelViewSet, DestroyModelMixin):
    """Memory API."""

    queryset = Memory.objects.none()
    serializer_class = MemorySerializer

    def get_queryset(self):
        if not self.request.user.is_superuser:
            self.permission_denied(self.request, "Access not allowed")
        # Use default database connection and not memory_db one (in case
        # a custom router is used).
        return Memory.objects.using("default").order_by("id")

    def perm_check(self, request: Request, instance) -> None:
        if not request.user.has_perm("memory.delete", instance):
            self.permission_denied(request, "Can not delete memory entry")

    def destroy(self, request: Request, *args, **kwargs):
        """Delete a memory object."""
        instance = self.get_object()
        self.perm_check(request, instance)
        return super().destroy(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(description="Return a list of translations."),
    retrieve=extend_schema(description="Return information about a translation."),
)
class TranslationViewSet(MultipleFieldViewSet, DestroyModelMixin):
    """Translation components API."""

    queryset = Translation.objects.none()
    serializer_class = TranslationSerializer
    lookup_fields = ("component__project__slug", "component__slug", "language__code")
    raw_urls = ("translation-file",)

    def get_queryset(self):
        return (
            Translation.objects.filter_access(self.request.user)
            .prefetch(defer_huge=False)
            .prefetch_related("component__source_language")
            .prefetch_related("component__addon_set")
            .prefetch_plurals()
            .order_by("id")
        )

    def paginate_queryset(self, queryset):
        result = super().paginate_queryset(queryset)
        if isinstance(queryset, TranslationQuerySet):
            result = prefetch_stats(result)
            processed: set[int] = set()
            for translation in result:
                project = translation.component.project
                if project.id in processed:
                    continue
                # Prefetch workflow settings
                project.project_languages.preload_workflow_settings()
                processed.add(project.id)
        return result

    @extend_schema(description="Upload new file with translations.", methods=["post"])
    @action(
        detail=True,
        methods=["get", "put", "post"],
        parser_classes=(
            parsers.MultiPartParser,
            parsers.FormParser,
            parsers.FileUploadParser,
        ),
        serializer_class=UploadRequestSerializer,
    )
    def file(self, request: Request, **kwargs):
        obj = self.get_object()
        user = request.user
        if request.method == "GET":
            if obj.get_filename() is None:
                msg = "No translation file!"
                raise Http404(msg)
            if not user.has_perm("translation.download", obj):
                raise PermissionDenied
            fmt = self.format_kwarg or request.query_params.get("format")
            query_string = request.GET.get("q", "")
            if query_string and not fmt:
                raise ValidationError({"q": "Query string is ignored without format"})
            try:
                parse_query(query_string)
            except Exception as error:
                raise ValidationError(
                    {"q": f"Could not parse query string: {error}"}
                ) from error
            try:
                return download_translation_file(request, obj, fmt, query_string)
            except Http404 as error:
                raise ValidationError({"format": str(error)}) from error

        if not (can_upload := user.has_perm("upload.perform", obj)):
            self.permission_denied(request, can_upload.reason)

        serializer = UploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.check_perms(request.user, obj)

        data = serializer.validated_data

        if obj.get_filename() is None and data["method"] != "source":
            raise ValidationError(
                {"method": "No translation file, try using method=source."}
            )

        author_name = None
        author_email = None
        if request.user.has_perm("upload.authorship", obj):
            author_name = data.get("author_name")
            author_email = data.get("author_email")

        try:
            not_found, skipped, accepted, total = obj.handle_upload(
                request,
                data["file"],
                data["conflicts"],
                author_name,
                author_email,
                data["method"],
                data["fuzzy"],
            )
        except Exception as error:
            report_error("Upload error", print_tb=True, project=obj.component.project)
            raise ValidationError({"file": str(error)}) from error

        return Response(
            data={
                "not_found": not_found,
                "skipped": skipped,
                "accepted": accepted,
                "total": total,
                # Compatibility with older less detailed API
                "result": accepted > 0,
                "count": total,
            }
        )

    @extend_schema(
        description="Return detailed translation statistics.",
        methods=["get"],
        tags=["translations", "statistics"],
    )
    @action(
        detail=True,
        methods=["get"],
        renderer_classes=(*api_settings.DEFAULT_RENDERER_CLASSES, FlatJsonRenderer),
    )
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)

    @extend_schema(description="Return a list of translation changes.", methods=["get"])
    @action(detail=True, methods=["get"])
    def changes(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.change_set.prefetch().order()
        queryset = ChangesFilterBackend().filter_queryset(request, queryset, self)
        page = self.paginate_queryset(queryset)

        serializer = ChangeSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @extend_schema(description="Return a list of translation units.", methods=["get"])
    @extend_schema(description="Add a new unit.", methods=["post"])
    @action(detail=True, methods=["get", "post"])
    def units(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer_class: type[NewUnitSerializer]
        if obj.component.template:
            serializer_class = MonolingualUnitSerializer
        elif obj.is_source:
            serializer_class = BilingualSourceUnitSerializer
        else:
            serializer_class = BilingualUnitSerializer

        if request.method == "POST":
            with transaction.atomic():
                if not (can_add := request.user.has_perm("unit.add", obj)):
                    self.permission_denied(request, can_add.reason)
                serializer = serializer_class(
                    data=request.data, context={"translation": obj}
                )
                serializer.is_valid(raise_exception=True)

                unit = obj.add_unit(request, **serializer.as_kwargs())
                outserializer = UnitSerializer(unit, context={"request": request})
                return Response(outserializer.data, status=HTTP_200_OK)

        query_string = request.GET.get("q", "")
        try:
            parse_query(query_string)
        except Exception as error:
            msg = f"Could not parse query string: {error}"
            raise ValidationError({"q": msg}) from error

        queryset = obj.unit_set.search(query_string).order_by("id").prefetch_full()
        page = self.paginate_queryset(queryset)

        serializer = UnitSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @extend_schema(description="Trigger automatic translation.", methods=["post"])
    @action(detail=True, methods=["post"])
    def autotranslate(self, request: Request, **kwargs):
        translation = self.get_object()
        if not request.user.has_perm("translation.auto", translation):
            self.permission_denied(request, "Can not auto translate")
        if translation.component.locked:
            self.permission_denied(request, "Component is locked")

        autoform = AutoForm(translation.component, request.user, request.data)
        if not autoform.is_valid():
            errors: dict[str, str] = {}
            for field in autoform:
                for error in field.errors:
                    if field.name in errors:
                        errors[field.name] += f", {error}"
                    else:
                        errors[field.name] = str(error)
            raise ValidationError(errors)

        auto = AutoTranslate(
            user=request.user,
            translation=translation,
            filter_type=autoform.cleaned_data["filter_type"],
            mode=autoform.cleaned_data["mode"],
        )
        message = auto.perform(
            auto_source=autoform.cleaned_data["auto_source"],
            source=autoform.cleaned_data["component"],
            engines=autoform.cleaned_data["engines"],
            threshold=autoform.cleaned_data["threshold"],
        )

        return Response(
            data={"details": message},
            status=HTTP_200_OK,
        )

    def destroy(self, request: Request, *args, **kwargs):
        """Delete a translation."""
        instance = self.get_object()
        if not request.user.has_perm("translation.delete", instance):
            self.permission_denied(request, "Can not delete translation")
        instance.remove(request.user)
        return Response(status=HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        description="Return a list of all languages the user has access to."
    ),
    retrieve=extend_schema(description="Return information about a language."),
    partial_update=extend_schema(description="Change the language parameters."),
)
class LanguageViewSet(viewsets.ModelViewSet):
    """Languages API."""

    queryset = Language.objects.none()
    serializer_class = LanguageSerializer
    lookup_field = "code"

    def get_queryset(self):
        if self.request.user.has_perm("language.edit"):
            return Language.objects.order_by("id").prefetch()
        return Language.objects.have_translation().order_by("id").prefetch()

    def perm_check(self, request: Request) -> None:
        if not request.user.has_perm("language.edit"):
            self.permission_denied(request, "Can not manage languages")

    def update(self, request: Request, *args, **kwargs):
        """Change the language parameters."""
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        """Create a new language."""
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete the language."""
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        description="Return statistics for a language.",
        methods=["get"],
        tags=["languages", "statistics"],
    )
    @action(
        detail=True,
        methods=["get"],
        renderer_classes=(*api_settings.DEFAULT_RENDERER_CLASSES, FlatJsonRenderer),
    )
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(description="Return a list of translation units."),
    retrieve=extend_schema(description="Return information about translation unit."),
    update=extend_schema(description="Perform full update on translation unit."),
    partial_update=extend_schema(
        description="Perform partial update on translation unit."
    ),
)
class UnitViewSet(viewsets.ReadOnlyModelViewSet, UpdateModelMixin, DestroyModelMixin):
    """Units API."""

    pagination_class = LargePagination

    queryset = Unit.objects.none()

    def get_serializer_class(self):
        """Get correct serializer based on action."""
        if self.action in {"list", "retrieve"}:
            return UnitSerializer
        return UnitWriteSerializer

    def get_queryset(self):
        return (
            Unit.objects.filter_access(self.request.user)
            .prefetch()
            .prefetch_full()
            .order_by("id")
        )

    def filter_queryset(self, queryset):
        result = super().filter_queryset(queryset)
        query_string = self.request.GET.get("q", "")
        try:
            parse_query(query_string)
        except Exception as error:
            msg = f"Could not parse query string: {error}"
            raise ValidationError({"q": msg}) from error
        if query_string:
            result = result.search(query_string)
        return result

    @transaction.atomic
    def perform_update(self, serializer) -> None:  # noqa: C901
        data = serializer.validated_data
        do_translate = "target" in data or "state" in data
        do_source = "extra_flags" in data or "explanation" in data or "labels" in data
        unit = serializer.instance
        translation = unit.translation
        request = self.request
        user = request.user

        new_target = data.get("target", [])
        new_state = data.get("state", None)

        # Sanity and permission checks
        if do_source and (
            not unit.is_source or not user.has_perm("source.edit", translation)
        ):
            self.permission_denied(
                request, "Source strings properties can be set only on source strings"
            )

        if do_translate:
            new_target_copy = new_target[:]
            if new_target_copy != unit.adjust_plurals(new_target):
                raise ValidationError({"target": "Number of plurals does not match"})

            if unit.readonly:
                self.permission_denied(request, "The string is read-only.")
            if not new_target or new_state is None:
                msg = "Please provide both state and target for a partial update"
                raise ValidationError({"state": msg, "target": msg})

            if new_state not in {
                STATE_APPROVED,
                STATE_TRANSLATED,
                STATE_FUZZY,
                STATE_EMPTY,
            }:
                raise ValidationError({"state": "Invalid state"})

            if new_state == STATE_EMPTY and any(new_target):
                raise ValidationError(
                    {"state": "Can not use empty state with non empty target"}
                )

            if new_state != STATE_EMPTY and not any(new_target):
                raise ValidationError(
                    {"state": "Can not use non empty state with empty target"}
                )

            can_edit = user.has_perm("unit.edit", unit)
            if not can_edit:
                self.permission_denied(request, can_edit.reason)

            if new_state == STATE_APPROVED:
                can_review = user.has_perm("unit.review", translation)
                if not can_review:
                    raise ValidationError({"state": can_review.reason})

        # Update attributes
        if do_source:
            fields = ["extra_flags", "explanation"]
            for name in fields:
                try:
                    setattr(unit, name, data[name])
                except KeyError:
                    continue
            if "labels" in data:
                unit.labels.set(data["labels"])
            unit.save(update_fields=fields)

        # Handle translate
        if do_translate:
            unit.translate(user, new_target, new_state)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete a translation unit."""
        obj = self.get_object()
        can_delete = request.user.has_perm("unit.delete", obj)
        if not can_delete:
            self.permission_denied(request, can_delete.reason)
        try:
            obj.translation.delete_unit(request, obj)
        except FileParseError as error:
            obj.translation.component.update_import_alerts(delete=False)
            return Response(
                data={"error": f"Could not remove the string: {error}"},
                status=HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def translations(self, request: Request, *args, **kwargs):
        unit = self.get_object()
        user = request.user
        user.check_access_component(unit.translation.component)

        if not unit.is_source:
            raise NotSourceUnit

        translation_units = (
            unit.source_unit.unit_set.exclude(pk=unit.pk).prefetch().prefetch_full()
        )
        serializer = UnitSerializer(
            translation_units, many=True, context={"request": request}
        )
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(description="Return a list of screenshot string information."),
    retrieve=extend_schema(
        description="Return information about screenshot information."
    ),
    partial_update=extend_schema(
        description="Edit partial information about screenshot."
    ),
)
class ScreenshotViewSet(DownloadViewSet, viewsets.ModelViewSet):
    """Screenshots API."""

    queryset = Screenshot.objects.none()
    serializer_class = ScreenshotSerializer
    raw_urls = ("screenshot-file",)
    raw_formats = ()

    def get_queryset(self):
        return Screenshot.objects.filter_access(self.request.user).order_by("id")

    @extend_schema(description="Download the screenshot image.", methods=["get"])
    @extend_schema(description="Replace screenshot image.", methods=["post"])
    @action(
        detail=True,
        methods=["get", "put", "post"],
        parser_classes=(
            parsers.MultiPartParser,
            parsers.FormParser,
            parsers.FileUploadParser,
        ),
        serializer_class=ScreenshotFileSerializer,
    )
    def file(self, request: Request, **kwargs):
        obj = self.get_object()
        if request.method == "GET":
            return self.download_file(obj.image.path, "application/binary")

        if not request.user.has_perm("screenshot.edit", obj.translation):
            raise PermissionDenied

        serializer = ScreenshotFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        obj.image.save(
            serializer.validated_data["image"].name, serializer.validated_data["image"]
        )

        return Response(data={"result": True})

    @extend_schema(
        description="Associate source string with screenshot.", methods=["post"]
    )
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def units(self, request: Request, **kwargs):
        obj = self.get_object()

        if not request.user.has_perm("screenshot.edit", obj.translation):
            raise PermissionDenied

        if "unit_id" not in request.data:
            raise ValidationError({"unit_id": "This field is required."})

        try:
            unit = obj.translation.unit_set.get(pk=int(request.data["unit_id"]))
        except (Unit.DoesNotExist, ValueError) as error:
            raise ValidationError({"unit_id": str(error)}) from error

        obj.units.add(unit)
        serializer = ScreenshotSerializer(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @extend_schema(
        description="Remove source string association with screenshot.",
        methods=["delete"],
    )
    @action(detail=True, methods=["delete"], url_path="units/(?P<unit_id>[0-9]+)")
    def delete_units(self, request: Request, pk, unit_id):
        obj = self.get_object()
        if not request.user.has_perm("screenshot.edit", obj.translation):
            raise PermissionDenied

        try:
            unit = obj.translation.unit_set.get(pk=unit_id)
        except Unit.DoesNotExist as error:
            raise Http404(str(error)) from error
        obj.units.remove(unit)
        return Response(status=HTTP_204_NO_CONTENT)

    def create(self, request: Request, *args, **kwargs):
        """Create a new screenshot."""
        required_params = ["project_slug", "component_slug", "language_code"]
        for param in required_params:
            if param not in request.data:
                raise ValidationError({param: "This field is required."})

        try:
            translation = Translation.objects.get(
                component__project__slug=request.data["project_slug"],
                component__slug=request.data["component_slug"],
                language__code=request.data["language_code"],
            )
        except Translation.DoesNotExist as error:
            raise ValidationError(
                {key: str(error) for key in required_params}
            ) from error

        if not request.user.has_perm("screenshot.add", translation):
            self.permission_denied(request, "Can not add screenshot.")

        with transaction.atomic():
            serializer = ScreenshotCreateSerializer(
                data=request.data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            instance = serializer.save(translation=translation, user=request.user)
            instance.change_set.create(
                action=ActionEvents.SCREENSHOT_ADDED,
                user=request.user,
                target=instance.name,
            )
            return Response(serializer.data, status=HTTP_201_CREATED)

    def update(self, request: Request, *args, **kwargs):
        """Edit full information about screenshot."""
        instance = self.get_object()
        if not request.user.has_perm("screenshot.edit", instance.translation):
            self.permission_denied(request, "Can not edit screenshot.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete screenshot."""
        instance = self.get_object()
        if not request.user.has_perm("screenshot.delete", instance.translation):
            self.permission_denied(request, "Can not delete screenshot.")
        return super().destroy(request, *args, **kwargs)


class ChangeFilter(filters.FilterSet):
    timestamp = filters.IsoDateTimeFromToRangeFilter()
    action = filters.MultipleChoiceFilter(choices=ActionEvents.choices)
    user = filters.CharFilter(field_name="user__username")

    class Meta:
        model = Change
        fields = ["action", "user", "timestamp"]


class ChangesFilterBackend(filters.DjangoFilterBackend):
    def get_filterset_class(self, view, queryset=None):
        return ChangeFilter


@extend_schema_view(
    list=extend_schema(description="Return a list of translation changes."),
    retrieve=extend_schema(
        description="Return information about a translation change."
    ),
)
class ChangeViewSet(viewsets.ReadOnlyModelViewSet):
    """Changes API."""

    queryset = Change.objects.none()
    serializer_class = ChangeSerializer
    filter_backends = (ChangesFilterBackend,)

    def get_queryset(self):
        return Change.objects.last_changes(self.request.user)

    def paginate_queryset(self, queryset):
        result = super().paginate_queryset(queryset)
        return Change.objects.preload_list(result)


@extend_schema_view(
    list=extend_schema(description="Return a list of component lists."),
    retrieve=extend_schema(description="Return information about component list."),
    partial_update=extend_schema(description="Change the component list parameters."),
)
class ComponentListViewSet(viewsets.ModelViewSet):
    """Component lists API."""

    queryset = ComponentList.objects.none()
    serializer_class = ComponentListSerializer
    lookup_field = "slug"
    request: Request  # type: ignore[assignment]

    def get_queryset(self):
        return (
            ComponentList.objects.filter(
                Q(components__project__in=self.request.user.allowed_projects)
                | Q(components__isnull=True)
            )
            .prefetch_related("components__project", "autocomponentlist_set")
            .order_by("id")
            .distinct()
        )

    def perm_check(self, request: Request) -> None:
        if not request.user.has_perm("componentlist.edit"):
            self.permission_denied(request, "Can not manage component lists")

    def update(self, request: Request, *args, **kwargs):
        """Change the component list parameters."""
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        """Create a new component list."""
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete the component list."""
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        description="Associate component with a component list.", methods=["post"]
    )
    @action(detail=True, methods=["post", "get"])
    def components(self, request: Request, **kwargs):
        obj = self.get_object()
        if request.method == "POST":
            self.perm_check(request)

            if "component_id" not in request.data:
                raise ValidationError({"component_id": "This field is required."})

            try:
                component = Component.objects.filter_access(self.request.user).get(
                    pk=int(request.data["component_id"]),
                )
            except (Component.DoesNotExist, ValueError) as error:
                raise ValidationError({"component_id": str(error)}) from error

            obj.components.add(component)
            serializer = self.serializer_class(obj, context={"request": request})

            return Response(serializer.data, status=HTTP_200_OK)

        queryset = (
            obj.components.filter_access(self.request.user).prefetch().order_by("id")
        )
        page = self.paginate_queryset(queryset)

        serializer = ComponentSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @extend_schema(
        description="Disassociate a component from the component list.",
        methods=["delete"],
        parameters=[OpenApiParameter("component_slug", str, OpenApiParameter.PATH)],
    )
    @action(
        detail=True,
        methods=["delete"],
        url_path="components/(?P<component_slug>[^/.]+)",
    )
    def delete_components(self, request: Request, slug, component_slug):
        obj = self.get_object()
        self.perm_check(request)

        try:
            component = obj.components.get(slug=component_slug)
        except Component.DoesNotExist as error:
            raise Http404(str(error)) from error
        obj.components.remove(component)
        return Response(status=HTTP_204_NO_CONTENT)


@extend_schema_view(list=extend_schema(description="List available categories."))
class CategoryViewSet(viewsets.ModelViewSet):
    """Category API."""

    queryset = Category.objects.none()
    serializer_class = CategorySerializer
    lookup_field = "pk"
    request: Request  # type: ignore[assignment]

    def get_queryset(self):
        return Category.objects.filter(
            project__in=self.request.user.allowed_projects
        ).order_by("id")

    def perm_check(self, request: Request, instance) -> None:
        if not request.user.has_perm("project.edit", instance):
            self.permission_denied(request, "Can not manage categories")

    def update(self, request: Request, *args, **kwargs):
        """Edit full information about category."""
        self.perm_check(request, self.get_object())
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete category."""
        instance = self.get_object()
        self.perm_check(request, instance)
        category_removal.delay(instance.pk, request.user.pk)
        return Response(status=HTTP_204_NO_CONTENT)

    def perform_create(self, serializer) -> None:
        """Create a new category."""
        if not self.request.user.has_perm(
            "project.edit", serializer.validated_data["project"]
        ):
            self.permission_denied(
                self.request, "Can not manage categories in this project"
            )
        serializer.save()

    def perform_update(self, serializer) -> None:
        if not self.request.user.has_perm(
            "project.edit",
            serializer.validated_data.get("project", serializer.instance.project),
        ):
            self.permission_denied(
                self.request, "Can not manage categories in this project"
            )
        serializer.instance.acting_user = self.request.user
        serializer.save()

    @extend_schema(
        description="""Return statistics for a category.""",
        methods=["get"],
        tags=["categories", "statistics"],
    )
    @action(
        detail=True,
        methods=["get"],
        renderer_classes=(*api_settings.DEFAULT_RENDERER_CLASSES, FlatJsonRenderer),
    )
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)


class Metrics(APIView):
    """Metrics view for monitoring."""

    permission_classes = (IsAuthenticated,)
    renderer_classes = (*api_settings.DEFAULT_RENDERER_CLASSES, OpenMetricsRenderer)
    serializer_class = MetricsSerializer

    def get(self, request: Request, format=None):  # noqa: A002
        """Return server metrics."""
        stats = GlobalStats()
        serializer = self.serializer_class(stats)
        return Response(serializer.data)


class Search(APIView):
    """Site-wide search endpoint."""

    serializer_class = None

    def get(self, request: Request, format=None):  # noqa: A002
        """Return site-wide search results as a list."""
        user = request.user
        projects = user.allowed_projects
        components = Component.objects.filter(project__in=projects)
        category = Category.objects.filter(project__in=projects)
        results: list[dict[str, str]] = []
        query = request.GET.get("q")
        if query and "\x00" not in query:
            results.extend(
                {
                    "url": project.get_absolute_url(),
                    "name": project.name,
                    "category": gettext("Project"),
                }
                for project in projects.search(query).order()[:5]
            )
            results.extend(
                {
                    "url": category.get_absolute_url(),
                    "name": str(category),
                    "category": gettext("Category"),
                }
                for category in category.search(query).order()[:5]
            )
            results.extend(
                {
                    "url": component.get_absolute_url(),
                    "name": str(component),
                    "category": gettext("Component"),
                }
                for component in components.search(query).order()[:5]
            )
            results.extend(
                {
                    "url": user.get_absolute_url(),
                    "name": user.username,
                    "category": gettext("User"),
                }
                for user in User.objects.search(query, parser="plain").order()[:5]
            )
            results.extend(
                {
                    "url": language.get_absolute_url(),
                    "name": language.name,
                    "category": gettext("Language"),
                }
                for language in Language.objects.search(query).order()[:5]
            )

        return Response(results)


class TasksViewSet(ViewSet):
    # Task-related data is handled and queried to Celery.
    # There is no Django model associated with tasks.
    serializer_class = None

    def get_task(
        self, request, pk, permission: str | None = None
    ) -> tuple[AsyncResult, Component | None]:
        obj: Model
        component: Component
        task = AsyncResult(str(pk))
        result = task.result
        if task.state == "PENDING" or isinstance(result, Exception):
            component = None
        else:
            if result is None:
                msg = "Task not found"
                raise Http404(msg)

            # Extract related object for permission check
            if "translation" in result:
                obj = get_object_or_404(Translation, pk=result["translation"])
                component = obj.component
            elif "component" in result:
                component = obj = get_object_or_404(Component, pk=result["component"])
            else:
                msg = "Invalid task"
                raise Http404(msg)

            # Check access or permission
            if permission:
                if not request.user.has_perm(permission, obj):
                    raise PermissionDenied
            elif not request.user.can_access_component(component):
                raise PermissionDenied

        return task, component

    @extend_schema(description="Return information about a task", methods=["get"])
    def retrieve(self, request: Request, pk=None):
        task, _component = self.get_task(request, pk)
        result = task.result
        return Response(
            {
                "completed": task.ready(),
                "progress": get_task_progress(task),
                "result": str(result) if isinstance(result, Exception) else result,
                "log": "\n".join(cache.get(f"task-log-{task.id}", [])),
            }
        )

    def destroy(self, request: Request, pk=None):
        task, component = self.get_task(request, pk, "component.edit")
        if not task.ready() and component is not None:
            task.revoke(terminate=True)
            # Unlink task from component
            if component.background_task_id == pk:
                component.delete_background_task()
        return Response(status=HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(description="Return a list of add-ons."),
    retrieve=extend_schema(description="Returns information about add-on information."),
    partial_update=extend_schema(description="Edit partial information about add-on."),
)
class AddonViewSet(viewsets.ReadOnlyModelViewSet, UpdateModelMixin, DestroyModelMixin):
    queryset = Addon.objects.all()
    serializer_class = AddonSerializer

    def perm_check(self, request: Request, instance: Addon) -> None:
        if instance.component and not request.user.has_perm(
            "component.edit", instance.component
        ):
            self.permission_denied(request, "Can not manage addons")
        if instance.project and not request.user.has_perm(
            "project.edit", instance.project
        ):
            self.permission_denied(request, "Can not manage addons")

    def update(self, request: Request, *args, **kwargs):
        """Edit full information about add-on."""
        instance = self.get_object()
        if instance.component:
            instance.component.acting_user = request.user
        if instance.project:
            instance.project.acting_user = request.user
        self.perm_check(request, instance)
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        """Delete add-on."""
        instance = self.get_object()
        if instance.component:
            instance.component.acting_user = request.user
        if instance.project:
            instance.project.acting_user = request.user
        self.perm_check(request, instance)
        return super().destroy(request, *args, **kwargs)
