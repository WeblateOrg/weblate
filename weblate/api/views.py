# Copyright © Michal Čihař <michal@weblate.org>
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
from django.core.exceptions import BadRequest, PermissionDenied
from django.db import transaction
from django.db.models import Model, Q
from django.forms.utils import from_current_timezone
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.html import format_html
from django.utils.translation import gettext
from django_filters import rest_framework as filters
from rest_framework import parsers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, UpdateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_423_LOCKED,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from rest_framework.utils import formatting
from rest_framework.views import APIView, exception_handler
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
    MonolingualUnitSerializer,
    NewUnitSerializer,
    NotificationSerializer,
    ProjectSerializer,
    RepoRequestSerializer,
    RoleSerializer,
    ScreenshotCreateSerializer,
    ScreenshotFileSerializer,
    ScreenshotSerializer,
    StatisticsSerializer,
    TranslationSerializer,
    UnitSerializer,
    UnitWriteSerializer,
    UploadRequestSerializer,
    UserStatisticsSerializer,
    get_reverse_kwargs,
)
from weblate.auth.models import AuthenticatedHttpRequest, Group, Role, User
from weblate.checks.models import Check
from weblate.formats.models import EXPORTERS
from weblate.lang.models import Language
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.exceptions import FileParseError
from weblate.trans.forms import AutoForm
from weblate.trans.models import (
    Category,
    Change,
    Component,
    ComponentList,
    Project,
    Suggestion,
    Translation,
    Unit,
)
from weblate.trans.tasks import (
    auto_translate,
    category_removal,
    component_removal,
    project_removal,
)
from weblate.trans.views.files import download_multi
from weblate.trans.views.reports import generate_credits
from weblate.utils.celery import get_queue_stats, get_task_progress
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
from weblate.utils.stats import GlobalStats
from weblate.utils.views import download_translation_file, zip_download
from weblate.wladmin.models import ConfigurationError

from .renderers import OpenMetricsRenderer

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


def weblate_exception_handler(exc, context):
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    if response is None and isinstance(exc, WeblateLockTimeoutError):
        return Response(
            data={"error": "Could not obtain repository lock to delete the string."},
            status=HTTP_423_LOCKED,
        )

    return response


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
            raise Http404("Not supported format")
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
                raise Http404("File not found") from error
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
        fields = ["username"]


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
        return User.objects.order_by("id")

    def perm_check(self, request: Request) -> None:
        if not request.user.has_perm("user.edit"):
            self.permission_denied(request, "Can not manage Users")

    def update(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        instance = self.get_object()
        remove_user(instance, cast(AuthenticatedHttpRequest, request))
        return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post", "delete"])
    def groups(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "group_id" not in request.data:
            raise ValidationError("Missing group_id parameter")

        try:
            group = Group.objects.get(pk=int(request.data["group_id"]))
        except (Group.DoesNotExist, ValueError) as error:
            raise ValidationError(str(error)) from error

        if request.method == "POST":
            obj.add_team(request, group)
        if request.method == "DELETE":
            obj.remove_team(request, group)
        serializer = self.get_serializer_class()(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(
        detail=True, methods=["get", "post"], serializer_class=NotificationSerializer
    )
    def notifications(self, request: Request, **kwargs):
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

    @action(
        detail=True,
        methods=["get", "put", "patch", "delete"],
        url_path="notifications/(?P<subscription_id>[0-9]+)",
        serializer_class=NotificationSerializer,
    )
    def notifications_details(self, request: Request, username, subscription_id):
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

    @action(detail=True, methods=["get"])
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = UserStatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)


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
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def roles(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "role_id" not in request.data:
            raise ValidationError("Missing role_id parameter")

        try:
            role = Role.objects.get(pk=int(request.data["role_id"]))
        except (Role.DoesNotExist, ValueError) as error:
            raise ValidationError(str(error)) from error

        obj.roles.add(role)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
    )
    def languages(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "language_code" not in request.data:
            raise ValidationError("Missing language_code parameter")

        try:
            language = Language.objects.get(code=request.data["language_code"])
        except (Language.DoesNotExist, ValueError) as error:
            raise ValidationError(str(error)) from error

        obj.languages.add(language)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

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

    @action(
        detail=True,
        methods=["post"],
    )
    def projects(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "project_id" not in request.data:
            raise ValidationError("Missing project_id parameter")

        try:
            project = Project.objects.get(
                pk=int(request.data["project_id"]),
            )
        except (Project.DoesNotExist, ValueError) as error:
            raise ValidationError(str(error)) from error
        obj.projects.add(project)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

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

    @action(detail=True, methods=["post"])
    def componentlists(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "component_list_id" not in request.data:
            raise ValidationError("Missing component_list_id parameter")

        try:
            component_list = ComponentList.objects.get(
                pk=int(request.data["component_list_id"]),
            )
        except (ComponentList.DoesNotExist, ValueError) as error:
            raise ValidationError(str(error)) from error
        obj.componentlists.add(component_list)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

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

    @action(
        detail=True,
        methods=["post"],
    )
    def components(self, request: Request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)
        if "component_id" not in request.data:
            raise ValidationError("Missing component_id parameter")

        try:
            component = Component.objects.filter_access(request.user).get(
                pk=int(request.data["component_id"])
            )
        except (Component.DoesNotExist, ValueError) as error:
            raise ValidationError(str(error)) from error
        obj.components.add(component)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

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

    @action(detail=True, methods=["post"], url_path="admins")
    def grant_admin(self, request: Request, id):  # noqa: A002
        group = self.get_object()
        self.perm_check(request, group)
        user_id = request.data.get("user_id")
        if not user_id:
            raise ValidationError("User ID is required")

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist as error:
            raise ValidationError("User not found") from error
        group.admins.add(user)
        user.add_team(cast(AuthenticatedHttpRequest, request), group)
        return Response({"Administration rights granted."}, status=HTTP_200_OK)

    @action(detail=True, methods=["delete"], url_path="admins/(?P<user_pk>[0-9]+)")
    def revoke_admin(self, request: Request, id, user_pk):  # noqa: A002
        group = self.get_object()
        self.perm_check(request, group)
        try:
            user = group.admins.get(pk=user_pk)  # Using user_pk from the URL path
        except User.DoesNotExist as error:
            raise ValidationError("User not found") from error

        group.admins.remove(user)
        serializer = GroupSerializer(group, context={"request": request})
        return Response(serializer.data, status=HTTP_200_OK)


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
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
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
            raise BadRequest("Invalid format for `start`") from err

        try:
            end_date = from_current_timezone(
                datetime.fromisoformat(request.query_params["end"])
            )
        except (ValueError, MultiValueDictKeyError) as err:
            raise BadRequest("Invalid format for `end`") from err

        language = None

        if "lang" in request.query_params:
            language = request.query_params["lang"]

        data = generate_credits(
            None if request.user.has_perm("reports.view", obj) else request.user,
            start_date,
            end_date,
            language,
            obj,
        )
        return Response(data=data)


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

    @action(detail=True, methods=["get"])
    def categories(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.category_set.order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = CategorySerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def languages(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(
            obj.stats.get_language_stats(), many=True, context={"request": request}
        )

        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def changes(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.change_set.prefetch().order()
        queryset = ChangesFilterBackend().filter_queryset(request, queryset, self)
        page = self.paginate_queryset(queryset)

        serializer = ChangeSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

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
        instance = self.get_object()
        if not request.user.has_perm("project.edit", instance):
            self.permission_denied(request, "Can not edit project")
        instance.acting_user = request.user
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
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
            cast(AuthenticatedHttpRequest, request),
            translations,
            [instance],
            requested_format,
            name=instance.slug,
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

    @action(detail=True, methods=["get"])
    def monolingual_base(self, request: Request, **kwargs):
        obj = self.get_object()

        if not obj.has_template():
            raise Http404("No template found!")

        return self.download_file(
            obj.get_template_filename(), obj.template_store.mimetype(), component=obj
        )

    @action(detail=True, methods=["get"])
    def new_template(self, request: Request, **kwargs):
        obj = self.get_object()

        if not obj.new_base:
            raise Http404("No file found!")

        return self.download_file(obj.get_new_base_filename(), "application/binary")

    @action(detail=True, methods=["get", "post"])
    def translations(self, request: Request, **kwargs):
        obj = self.get_object()

        if request.method == "POST":
            if not request.user.has_perm("translation.add", obj):
                self.permission_denied(request, "Can not create translation")

            if "language_code" not in request.data:
                raise ValidationError("Missing 'language_code' parameter")

            language_code = request.data["language_code"]

            try:
                language = Language.objects.get(code=language_code)
            except Language.DoesNotExist as error:
                raise ValidationError(
                    f"No language code {language_code!r} found!"
                ) from error

            if not obj.can_add_new_language(request.user):
                self.permission_denied(request, message=obj.new_lang_error_message)

            translation = obj.add_new_language(language, request)
            if translation is None:
                storage = get_messages(request)
                if storage:
                    message = "\n".join(m.message for m in storage)
                else:
                    message = f"Could not add {language_code!r}!"
                raise ValidationError(message)

            serializer = TranslationSerializer(
                translation, context={"request": request}, remove_fields=("component",)
            )

            return Response(data={"data": serializer.data}, status=HTTP_201_CREATED)

        queryset = obj.translation_set.all().order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = TranslationSerializer(
            page, many=True, context={"request": request}, remove_fields=("component",)
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

    @action(detail=True, methods=["get"])
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.translation_set.all().order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = StatisticsSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def changes(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.change_set.prefetch().order()
        queryset = ChangesFilterBackend().filter_queryset(request, queryset, self)
        page = self.paginate_queryset(queryset)

        serializer = ChangeSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def screenshots(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = Screenshot.objects.filter(translation__component=obj).order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = ScreenshotSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    def update(self, request: Request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.has_perm("component.edit", instance):
            self.permission_denied(request, "Can not edit component")
        instance.acting_user = request.user
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
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
            raise ValidationError("Missing 'project_slug' parameter")

        project_slug = request.data["project_slug"]

        try:
            project = request.user.allowed_projects.exclude(pk=instance.project_id).get(
                slug=project_slug
            )
        except Project.DoesNotExist as error:
            raise ValidationError(f"No project slug {project_slug!r} found!") from error

        instance.links.add(project)
        serializer = self.serializer_class(instance, context={"request": request})

        return Response(data={"data": serializer.data}, status=HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"])
    def links(self, request: Request, **kwargs):
        instance = self.get_object()
        if request.method == "POST":
            return self.add_link(request, instance)

        queryset = instance.links.order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = ProjectSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["delete"], url_path="links/(?P<project_slug>[^/.]+)")
    def delete_links(self, request: Request, project__slug, slug, project_slug):
        instance = self.get_object()
        if not request.user.has_perm("component.edit", instance):
            self.permission_denied(request, "Can not edit component")

        try:
            project = instance.links.get(slug=project_slug)
        except Project.DoesNotExist as error:
            raise Http404("Project not found") from error
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
            cast(AuthenticatedHttpRequest, request),
            instance.translation_set.all(),
            [instance],
            requested_format,
            name=instance.full_slug.replace("/", "-"),
        )


class MemoryViewSet(viewsets.ModelViewSet, DestroyModelMixin):
    """Memory API."""

    queryset = Memory.objects.none()
    serializer_class = MemorySerializer

    def get_queryset(self):
        if not self.request.user.is_superuser:
            self.permission_denied(self.request, "Access not allowed")
        return Memory.objects.order_by("id")

    def perm_check(self, request: Request, instance) -> None:
        if not request.user.has_perm("memory.delete", instance):
            self.permission_denied(request, "Can not delete memory entry")

    def destroy(self, request: Request, *args, **kwargs):
        instance = self.get_object()
        self.perm_check(request, instance)
        return super().destroy(request, *args, **kwargs)


class TranslationViewSet(MultipleFieldViewSet, DestroyModelMixin):
    """Translation components API."""

    queryset = Translation.objects.none()
    serializer_class = TranslationSerializer
    lookup_fields = ("component__project__slug", "component__slug", "language__code")
    raw_urls = ("translation-file",)

    def get_queryset(self):
        return (
            Translation.objects.prefetch()
            .filter_access(self.request.user)
            .prefetch_related("component__source_language")
            .order_by("id")
        )

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
            if not user.has_perm("translation.download", obj):
                raise PermissionDenied
            if obj.get_filename() is None:
                raise Http404("No translation file!")
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

        if not user.has_perm("upload.perform", obj):
            raise PermissionDenied

        serializer = UploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.check_perms(request.user, obj)

        data = serializer.validated_data

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

    @action(detail=True, methods=["get"])
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def changes(self, request: Request, **kwargs):
        obj = self.get_object()

        queryset = obj.change_set.prefetch().order()
        queryset = ChangesFilterBackend().filter_queryset(request, queryset, self)
        page = self.paginate_queryset(queryset)

        serializer = ChangeSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

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
            can_add = request.user.has_perm("unit.add", obj)
            if not can_add:
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
            raise ValidationError(f"Could not parse query string: {error}") from error

        queryset = obj.unit_set.search(query_string).order_by("id").prefetch_full()
        page = self.paginate_queryset(queryset)

        serializer = UnitSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

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

        return Response(
            data={
                "details": auto_translate(
                    request.user.id,
                    translation.id,
                    autoform.cleaned_data["mode"],
                    autoform.cleaned_data["filter_type"],
                    autoform.cleaned_data["auto_source"],
                    autoform.cleaned_data["component"],
                    autoform.cleaned_data["engines"],
                    autoform.cleaned_data["threshold"],
                )
            },
            status=HTTP_200_OK,
        )

    def destroy(self, request: Request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.has_perm("translation.delete", instance):
            self.permission_denied(request, "Can not delete translation")
        instance.remove(request.user)
        return Response(status=HTTP_204_NO_CONTENT)


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
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)


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
            raise ValidationError(f"Could not parse query string: {error}") from error
        if query_string:
            result = result.search(query_string)
        return result

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
                raise ValidationError(
                    "Please provide both state and target for a partial update"
                )

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


class ScreenshotViewSet(DownloadViewSet, viewsets.ModelViewSet):
    """Screenshots API."""

    queryset = Screenshot.objects.none()
    serializer_class = ScreenshotSerializer
    raw_urls = ("screenshot-file",)
    raw_formats = ()

    def get_queryset(self):
        return Screenshot.objects.filter_access(self.request.user).order_by("id")

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

    @action(detail=True, methods=["post"])
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
                action=Change.ACTION_SCREENSHOT_ADDED,
                user=request.user,
                target=instance.name,
            )
            return Response(serializer.data, status=HTTP_201_CREATED)

    def update(self, request: Request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.has_perm("screenshot.edit", instance.translation):
            self.permission_denied(request, "Can not edit screenshot.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.has_perm("screenshot.delete", instance.translation):
            self.permission_denied(request, "Can not delete screenshot.")
        return super().destroy(request, *args, **kwargs)


class ChangeFilter(filters.FilterSet):
    timestamp = filters.IsoDateTimeFromToRangeFilter()
    action = filters.MultipleChoiceFilter(choices=Change.ACTION_CHOICES)
    user = filters.CharFilter(field_name="user__username")

    class Meta:
        model = Change
        fields = ["action", "user", "timestamp"]


class ChangesFilterBackend(filters.DjangoFilterBackend):
    def get_filterset_class(self, view, queryset=None):
        return ChangeFilter


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
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)

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
        self.perm_check(request, self.get_object())
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        instance = self.get_object()
        self.perm_check(request, instance)
        category_removal.delay(instance.pk, request.user.pk)
        return Response(status=HTTP_204_NO_CONTENT)

    def perform_create(self, serializer) -> None:
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

    @action(detail=True, methods=["get"])
    def statistics(self, request: Request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)


class Metrics(APIView):
    """Metrics view for monitoring."""

    permission_classes = (IsAuthenticated,)
    renderer_classes = (JSONRenderer, BrowsableAPIRenderer, OpenMetricsRenderer)

    def get(self, request: Request, format=None):  # noqa: A002
        stats = GlobalStats()
        return Response(
            {
                "units": stats.all,
                "units_translated": stats.translated,
                "users": User.objects.count(),
                "changes": stats.total_changes,
                "projects": Project.objects.count(),
                "components": Component.objects.count(),
                "translations": Translation.objects.count(),
                "languages": stats.languages,
                "checks": Check.objects.count(),
                "configuration_errors": ConfigurationError.objects.filter(
                    ignored=False
                ).count(),
                "suggestions": Suggestion.objects.count(),
                "celery_queues": get_queue_stats(),
                "name": settings.SITE_TITLE,
            }
        )


class Search(APIView):
    """Site-wide search endpoint."""

    def get(self, request: Request, format=None):  # noqa: A002
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
                raise Http404("Task not found")

            # Extract related object for permission check
            if "translation" in result:
                obj = get_object_or_404(Translation, pk=result["translation"])
                component = obj.component
            elif "component" in result:
                component = obj = get_object_or_404(Component, pk=result["component"])
            else:
                raise Http404("Invalid task")

            # Check access or permission
            if permission:
                if not request.user.has_perm(permission, obj):
                    raise PermissionDenied
            elif not request.user.can_access_component(component):
                raise PermissionDenied

        return task, component

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
        instance = self.get_object()
        if instance.component:
            instance.component.acting_user = request.user
        if instance.project:
            instance.project.acting_user = request.user
        self.perm_check(request, instance)
        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args, **kwargs):
        instance = self.get_object()
        if instance.component:
            instance.component.acting_user = request.user
        if instance.project:
            instance.project.acting_user = request.user
        self.perm_check(request, instance)
        return super().destroy(request, *args, **kwargs)
