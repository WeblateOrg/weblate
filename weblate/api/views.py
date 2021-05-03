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

import os.path
from typing import Optional, Tuple

from celery.result import AsyncResult
from django.conf import settings
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe
from django_filters import rest_framework as filters
from rest_framework import parsers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ParseError
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, UpdateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_204_NO_CONTENT
from rest_framework.utils import formatting
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from weblate.accounts.models import Subscription
from weblate.accounts.utils import remove_user
from weblate.addons.models import Addon
from weblate.api.serializers import (
    AddonSerializer,
    BasicUserSerializer,
    BilingualUnitSerializer,
    ChangeSerializer,
    ComponentListSerializer,
    ComponentSerializer,
    FullUserSerializer,
    GroupSerializer,
    LanguageSerializer,
    LockRequestSerializer,
    LockSerializer,
    MonolingualUnitSerializer,
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
)
from weblate.auth.models import Group, Role, User
from weblate.checks.models import Check
from weblate.formats.models import EXPORTERS
from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.trans.forms import AutoForm
from weblate.trans.models import (
    Change,
    Component,
    ComponentList,
    Project,
    Suggestion,
    Translation,
    Unit,
)
from weblate.trans.stats import get_project_stats
from weblate.trans.tasks import auto_translate, component_removal, project_removal
from weblate.utils.celery import get_queue_stats, get_task_progress, is_task_ready
from weblate.utils.docs import get_doc_url
from weblate.utils.errors import report_error
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_TRANSLATED,
)
from weblate.utils.stats import GlobalStats
from weblate.utils.views import download_translation_file, zip_download
from weblate.wladmin.models import ConfigurationError

REPO_OPERATIONS = {
    "push": ("vcs.push", "do_push", (), True),
    "pull": ("vcs.update", "do_update", (), True),
    "reset": ("vcs.reset", "do_reset", (), True),
    "cleanup": ("vcs.reset", "do_cleanup", (), True),
    "commit": ("vcs.commit", "commit_pending", ("api",), False),
    "file-sync": ("vcs.reset", "do_file_sync", (), True),
}

DOC_TEXT = """
<p>See <a href="{0}">the Weblate's Web API documentation</a> for detailed
description of the API.</p>
"""


def get_view_description(view, html=False):
    """Given a view class, return a textual description to represent the view.

    This name is used in the browsable API, and in OPTIONS responses. This function is
    the default for the `VIEW_DESCRIPTION_FUNCTION` setting.
    """
    description = view.__doc__ or ""
    description = formatting.dedent(description)

    if hasattr(getattr(view, "serializer_class", "None"), "Meta"):
        doc_url = get_doc_url(
            "api",
            f"{view.serializer_class.Meta.model.__name__.lower()}s",
            user=view.request.user,
        )
    else:
        doc_url = get_doc_url("api", user=view.request.user)

    if html:
        return formatting.markup_description(description) + mark_safe(
            DOC_TEXT.format(doc_url)
        )
    return description


class MultipleFieldMixin:
    """Multiple field filtering mixin.

    Apply this mixin to any view or viewset to get multiple field filtering based on a
    `lookup_fields` attribute, instead of the default single field filtering.
    """

    def get_object(self):
        # Get the base queryset
        queryset = self.get_queryset()
        # Apply any filter backends
        queryset = self.filter_queryset(queryset)
        lookup = {}
        for field in self.lookup_fields:
            lookup[field] = self.kwargs[field]
        # Lookup the object
        return get_object_or_404(queryset, **lookup)


class DownloadViewSet(viewsets.ReadOnlyModelViewSet):
    raw_urls: Tuple[str, ...] = ()
    raw_formats = EXPORTERS

    def perform_content_negotiation(self, request, force=False):
        """Custom content negotiation."""
        if request.resolver_match.url_name in self.raw_urls:
            fmt = self.format_kwarg or request.query_params.get("format")
            if fmt is None or fmt in self.raw_formats:
                renderers = self.get_renderers()
                return (renderers[0], renderers[0].media_type)
            raise Http404("Not supported format")
        return super().perform_content_negotiation(request, force)

    def download_file(self, filename, content_type, component=None):
        """Wrapper for file download."""
        if os.path.isdir(filename):
            response = zip_download(filename, filename)
            filename = "{}.zip".format(component.slug if component else "weblate")
        else:
            with open(filename, "rb") as handle:
                response = HttpResponse(handle.read(), content_type=content_type)
            filename = os.path.basename(filename)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class WeblateViewSet(DownloadViewSet):
    """Allow to skip content negotiation for certain requests."""

    def repository_operation(self, request, obj, project, operation):
        permission, method, args, takes_request = REPO_OPERATIONS[operation]

        if not request.user.has_perm(permission, project):
            raise PermissionDenied()

        obj.acting_user = request.user

        if takes_request:
            args = args + (request,)
        else:
            args = args + (request.user,)

        return getattr(obj, method)(*args)

    @action(
        detail=True, methods=["get", "post"], serializer_class=RepoRequestSerializer
    )
    def repository(self, request, **kwargs):
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
            raise PermissionDenied()

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
                    kwargs={
                        "component__project__slug": component.project.slug,
                        "component__slug": component.slug,
                        "language__code": obj.language.code,
                    },
                    request=request,
                )
            else:
                component = obj
                data["url"] = reverse(
                    "api:component-repository",
                    kwargs={"project__slug": obj.project.slug, "slug": obj.slug},
                    request=request,
                )

            data["remote_commit"] = component.get_last_remote_commit()
            data["status"] = component.repository.status()
            changes = component.change_set.filter(
                action__in=Change.ACTIONS_REPOSITORY
            ).order_by("-id")

            if changes.exists() and changes[0].is_merge_failure():
                data["merge_failure"] = changes[0].target
            else:
                data["merge_failure"] = None

        return Response(data)


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

    def perm_check(self, request):
        if not request.user.has_perm("user.edit"):
            self.permission_denied(request, "Can not manage Users")

    def update(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.perm_check(request)
        instance = self.get_object()
        remove_user(instance, request)
        return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def groups(self, request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "group_id" not in request.data:
            raise ParseError("Missing group_id parameter")

        try:
            group = Group.objects.get(pk=int(request.data["group_id"]))
        except (Group.DoesNotExist, ValueError) as error:
            raise ParseError(str(error), "invalid")

        obj.groups.add(group)
        serializer = self.get_serializer_class()(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(
        detail=True, methods=["get", "post"], serializer_class=NotificationSerializer
    )
    def notifications(self, request, **kwargs):
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
    def notifications_details(self, request, username, subscription_id):
        obj = self.get_object()

        try:
            subscription = obj.subscription_set.get(id=subscription_id)
        except Subscription.DoesNotExist as error:
            raise Http404(str(error))

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
    def statistics(self, request, **kwargs):
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
        return self.request.user.groups.order_by("id")

    def perm_check(self, request):
        if not request.user.has_perm("group.edit"):
            self.permission_denied(request, "Can not manage groups")

    def update(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def roles(self, request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "role_id" not in request.data:
            raise ParseError("Missing role_id parameter")

        try:
            role = Role.objects.get(pk=int(request.data["role_id"]))
        except (Role.DoesNotExist, ValueError) as error:
            raise ParseError(str(error), "invalid")

        obj.roles.add(role)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
    )
    def languages(self, request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "language_code" not in request.data:
            raise ParseError("Missing language_code parameter")

        try:
            language = Language.objects.get(code=request.data["language_code"])
        except (Language.DoesNotExist, ValueError) as error:
            raise ParseError(str(error), "invalid")

        obj.languages.add(language)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(
        detail=True, methods=["delete"], url_path="languages/(?P<language_code>[^/.]+)"
    )
    def delete_languages(self, request, id, language_code):
        obj = self.get_object()
        self.perm_check(request)

        try:
            language = obj.languages.get(code=language_code)
        except Language.DoesNotExist as error:
            raise Http404(str(error))
        obj.languages.remove(language)
        return Response(status=HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["post"],
    )
    def projects(self, request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "project_id" not in request.data:
            raise ParseError("Missing project_id parameter")

        try:
            project = Project.objects.get(
                pk=int(request.data["project_id"]),
            )
        except (Project.DoesNotExist, ValueError) as error:
            raise ParseError(str(error), "invalid")
        obj.projects.add(project)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(detail=True, methods=["delete"], url_path="projects/(?P<project_id>[0-9]+)")
    def delete_projects(self, request, id, project_id):
        obj = self.get_object()
        self.perm_check(request)

        try:
            project = obj.projects.get(pk=project_id)
        except Project.DoesNotExist as error:
            raise Http404(str(error))
        obj.projects.remove(project)
        return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def componentlists(self, request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "component_list_id" not in request.data:
            raise ParseError("Missing component_list_id parameter")

        try:
            component_list = ComponentList.objects.get(
                pk=int(request.data["component_list_id"]),
            )
        except (ComponentList.DoesNotExist, ValueError) as error:
            raise ParseError(str(error), "invalid")
        obj.componentlists.add(component_list)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(
        detail=True,
        methods=["delete"],
        url_path="componentlists/(?P<component_list_id>[0-9]+)",
    )
    def delete_componentlists(self, request, id, component_list_id):
        obj = self.get_object()
        self.perm_check(request)
        try:
            component_list = obj.componentlists.get(pk=component_list_id)
        except ComponentList.DoesNotExist as error:
            raise Http404(str(error))
        obj.componentlists.remove(component_list)
        return Response(status=HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["post"],
    )
    def components(self, request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)
        if "component_id" not in request.data:
            raise ParseError("Missing component_id parameter")

        try:
            component = Component.objects.filter_access(request.user).get(
                pk=int(request.data["component_id"])
            )
        except (Component.DoesNotExist, ValueError) as error:
            raise ParseError(str(error), "invalid")
        obj.components.add(component)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(
        detail=True, methods=["delete"], url_path="components/(?P<component_id>[0-9]+)"
    )
    def delete_components(self, request, id, component_id):
        obj = self.get_object()
        self.perm_check(request)

        try:
            component = obj.components.get(pk=component_id)
        except Component.DoesNotExist as error:
            raise Http404(str(error))
        obj.components.remove(component)
        return Response(status=HTTP_204_NO_CONTENT)


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
            .all()
        )

    def perm_check(self, request):
        if not request.user.has_perm("role.edit"):
            self.permission_denied(request, "Can not manage roles")

    def update(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)


class ProjectViewSet(
    WeblateViewSet, UpdateModelMixin, CreateModelMixin, DestroyModelMixin
):
    """Translation projects API."""

    queryset = Project.objects.none()
    serializer_class = ProjectSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return self.request.user.allowed_projects.order_by("id")

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
    def components(self, request, **kwargs):
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
    def statistics(self, request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def languages(self, request, **kwargs):
        obj = self.get_object()

        return Response(get_project_stats(obj))

    @action(detail=True, methods=["get"])
    def changes(self, request, **kwargs):
        obj = self.get_object()

        queryset = Change.objects.prefetch().filter(project=obj).order_by("id")
        queryset = ChangesFilterBackend().filter_queryset(request, queryset, self)
        page = self.paginate_queryset(queryset)

        serializer = ChangeSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        if not request.user.has_perm("project.add"):
            self.permission_denied(request, "Can not create projects")
        self.request = request
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
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

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.has_perm("project.edit", instance):
            self.permission_denied(request, "Can not edit project")
        instance.acting_user = request.user
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.has_perm("project.edit", instance):
            self.permission_denied(request, "Can not delete project")
        instance.acting_user = request.user
        project_removal.delay(instance.pk, request.user.pk)
        return Response(status=HTTP_204_NO_CONTENT)


class ComponentViewSet(
    MultipleFieldMixin, WeblateViewSet, UpdateModelMixin, DestroyModelMixin
):
    """Translation components API."""

    queryset = Component.objects.none()
    serializer_class = ComponentSerializer
    lookup_fields = ("project__slug", "slug")

    def get_queryset(self):
        return (
            Component.objects.prefetch()
            .filter_access(self.request.user)
            .prefetch_related("source_language")
            .order_by("id")
        )

    @action(
        detail=True, methods=["get", "post"], serializer_class=LockRequestSerializer
    )
    def lock(self, request, **kwargs):
        obj = self.get_object()

        if request.method == "POST":
            if not request.user.has_perm("component.lock", obj):
                raise PermissionDenied()

            serializer = LockRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            obj.do_lock(request.user, serializer.validated_data["lock"])

        return Response(data=LockSerializer(obj).data)

    @action(detail=True, methods=["get"])
    def monolingual_base(self, request, **kwargs):
        obj = self.get_object()

        if not obj.has_template():
            raise Http404("No template found!")

        return self.download_file(
            obj.get_template_filename(), obj.template_store.mimetype(), component=obj
        )

    @action(detail=True, methods=["get"])
    def new_template(self, request, **kwargs):
        obj = self.get_object()

        if not obj.new_base:
            raise Http404("No file found!")

        return self.download_file(obj.get_new_base_filename(), "application/binary")

    @action(detail=True, methods=["get", "post"])
    def translations(self, request, **kwargs):
        obj = self.get_object()

        if request.method == "POST":
            if not request.user.has_perm("translation.add", obj):
                self.permission_denied(request, "Can not create translation")

            if "language_code" not in request.data:
                raise ParseError("Missing 'language_code' parameter")

            language_code = request.data["language_code"]

            try:
                language = Language.objects.get(code=language_code)
            except Language.DoesNotExist:
                raise ParseError(
                    f"No language code '{language_code}' found!", "invalid"
                )

            if not obj.can_add_new_language(request.user):
                self.permission_denied(
                    request, message="Could not add new translation file."
                )

            translation = obj.add_new_language(language, request)
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
    def addons(self, request, **kwargs):
        obj = self.get_object()

        if not request.user.has_perm("component.edit", obj):
            self.permission_denied(request, "Can not create addon")

        serializer = AddonSerializer(
            data=request.data, context={"request": request, "component": obj}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(component=obj)
        return Response(serializer.data, status=HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def statistics(self, request, **kwargs):
        obj = self.get_object()

        queryset = obj.translation_set.all().order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = StatisticsSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def changes(self, request, **kwargs):
        obj = self.get_object()

        queryset = Change.objects.prefetch().filter(component=obj).order_by("id")
        queryset = ChangesFilterBackend().filter_queryset(request, queryset, self)
        page = self.paginate_queryset(queryset)

        serializer = ChangeSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def screenshots(self, request, **kwargs):
        obj = self.get_object()

        queryset = Screenshot.objects.filter(translation__component=obj).order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = ScreenshotSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.has_perm("component.edit", instance):
            self.permission_denied(request, "Can not edit component")
        instance.acting_user = request.user
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.has_perm("component.edit", instance):
            self.permission_denied(request, "Can not delete component")
        instance.acting_user = request.user
        component_removal.delay(instance.pk, request.user.pk)
        return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"])
    def links(self, request, **kwargs):
        instance = self.get_object()
        if request.method == "POST":
            if not request.user.has_perm("component.edit", instance):
                self.permission_denied(request, "Can not edit component")
            if "project_slug" not in request.data:
                raise ParseError("Missing 'project_slug' parameter")

            project_slug = request.data["project_slug"]

            try:
                project = request.user.allowed_projects.exclude(
                    pk=instance.project_id
                ).get(slug=project_slug)
            except Project.DoesNotExist:
                raise ParseError(f"No project slug '{project_slug}' found!")

            instance.links.add(project)
            serializer = self.serializer_class(instance, context={"request": request})

            return Response(data={"data": serializer.data}, status=HTTP_201_CREATED)

        queryset = instance.links.order_by("id")
        page = self.paginate_queryset(queryset)

        serializer = ProjectSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["delete"], url_path="links/(?P<project_slug>[^/.]+)")
    def delete_links(self, request, project__slug, slug, project_slug):
        instance = self.get_object()
        if not request.user.has_perm("component.edit", instance):
            self.permission_denied(request, "Can not edit component")

        try:
            project = instance.links.get(slug=project_slug)
        except Project.DoesNotExist:
            raise Http404("Project not found")
        instance.links.remove(project)
        return Response(status=HTTP_204_NO_CONTENT)


class TranslationViewSet(MultipleFieldMixin, WeblateViewSet, DestroyModelMixin):
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
    def file(self, request, **kwargs):
        obj = self.get_object()
        user = request.user
        if request.method == "GET":
            fmt = self.format_kwarg or request.query_params.get("format")
            return download_translation_file(request, obj, fmt)

        if not user.has_perm("upload.perform", obj):
            raise PermissionDenied()

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
            not_found, skipped, accepted, total = obj.merge_upload(
                request,
                data["file"],
                data["conflicts"],
                author_name,
                author_email,
                data["method"],
                data["fuzzy"],
            )

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
        except Exception as error:
            report_error(cause="Upload error", print_tb=True)
            raise ParseError(str(error), "invalid")

    @action(detail=True, methods=["get"])
    def statistics(self, request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def changes(self, request, **kwargs):
        obj = self.get_object()

        queryset = Change.objects.prefetch().filter(translation=obj).order_by("id")
        queryset = ChangesFilterBackend().filter_queryset(request, queryset, self)
        page = self.paginate_queryset(queryset)

        serializer = ChangeSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get", "post"])
    def units(self, request, **kwargs):
        obj = self.get_object()

        if obj.component.template:
            serializer_class = MonolingualUnitSerializer
        else:
            serializer_class = BilingualUnitSerializer

        if request.method == "POST":
            if not request.user.has_perm("unit.add", obj):
                self.permission_denied(request, "Can not add unit")
            serializer = serializer_class(
                data=request.data, context={"translation": obj}
            )
            serializer.is_valid(raise_exception=True)

            obj.add_unit(request, **serializer.as_kwargs())
            serializer = self.serializer_class(obj, context={"request": request})
            return Response(serializer.data, status=HTTP_200_OK)

        queryset = (
            obj.unit_set.search(request.GET.get("q", "")).order_by("id").prefetch()
        )
        page = self.paginate_queryset(queryset)

        serializer = UnitSerializer(page, many=True, context={"request": request})

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"])
    def autotranslate(self, request, **kwargs):
        translation = self.get_object()
        if not request.user.has_perm("translation.auto", translation):
            self.permission_denied(request, "Can not auto translate")
        autoform = AutoForm(translation.component, request.data)
        if translation.component.locked or not autoform.is_valid():
            raise ParseError("Failed to process autotranslation data!", "invalid")
        args = (
            request.user.id,
            translation.id,
            autoform.cleaned_data["mode"],
            autoform.cleaned_data["filter_type"],
            autoform.cleaned_data["auto_source"],
            autoform.cleaned_data["component"],
            autoform.cleaned_data["engines"],
            autoform.cleaned_data["threshold"],
        )
        return Response(
            data={"details": auto_translate(*args)},
            status=HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
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
            return Language.objects.order_by("id")
        return Language.objects.have_translation().order_by("id")

    def perm_check(self, request):
        if not request.user.has_perm("language.edit"):
            self.permission_denied(request, "Can not manage languages")

    def update(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def statistics(self, request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(obj, context={"request": request})

        return Response(serializer.data)


class UnitViewSet(viewsets.ReadOnlyModelViewSet, UpdateModelMixin, DestroyModelMixin):
    """Units API."""

    queryset = Unit.objects.none()

    def get_serializer(self, instance, *args, **kwargs):
        # Get correct serializer based on action and instance
        if self.action in ("list", "retrieve"):
            serializer_class = UnitSerializer
        else:
            serializer_class = UnitWriteSerializer
        kwargs["context"] = self.get_serializer_context()
        return serializer_class(instance, *args, **kwargs)

    def get_queryset(self):
        return Unit.objects.filter_access(self.request.user).order_by("id")

    def perform_update(self, serializer):
        data = serializer.validated_data
        do_translate = "target" in data or "state" in data
        do_source = "extra_flags" in data or "explanation" in data
        unit = serializer.instance
        translation = unit.translation
        user = self.request.user

        new_target = data.get("target", [])
        new_state = data.get("state", None)

        # Sanity and permission checks
        if do_source and (
            not unit.is_source or not user.has_perm("source.edit", translation)
        ):
            raise PermissionDenied()

        if do_translate:
            if unit.readonly:
                raise PermissionDenied()
            if not new_target or new_state is None:
                raise ParseError(
                    "Please provide both state and target for a partial update"
                )

            if new_state not in (
                STATE_APPROVED,
                STATE_TRANSLATED,
                STATE_FUZZY,
                STATE_EMPTY,
            ):
                raise ParseError("Invalid state")

            if new_state == STATE_EMPTY and any(new_target):
                raise ParseError("Can not use empty state with non empty target")

            if new_state != STATE_EMPTY and not any(new_target):
                raise ParseError("Can not use non empty state with empty target")

            if not user.has_perm("unit.edit", unit):
                raise PermissionDenied()

            if new_state == STATE_APPROVED and not user.has_perm(
                "unit.review", translation
            ):
                raise PermissionDenied()

        # Update attributes
        if do_source:
            fields = ["extra_flags", "explanation"]
            for name in fields:
                try:
                    setattr(unit, name, data[name])
                except KeyError:
                    continue
            unit.save(update_fields=fields)

        # Handle translate
        if do_translate:
            unit.translate(user, new_target, new_state)

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if not request.user.has_perm("unit.delete", obj):
            self.permission_denied(request, "Can not remove string")
        obj.translation.delete_unit(request, obj)
        return Response(status=HTTP_204_NO_CONTENT)


class ScreenshotViewSet(DownloadViewSet, viewsets.ModelViewSet):
    """Screenshots API."""

    queryset = Screenshot.objects.none()
    serializer_class = ScreenshotSerializer
    raw_urls = ("screenshot-file",)

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
    def file(self, request, **kwargs):
        obj = self.get_object()
        if request.method == "GET":
            return self.download_file(obj.image.path, "application/binary")

        if not request.user.has_perm("screenshot.edit", obj.translation):
            raise PermissionDenied()

        serializer = ScreenshotFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        obj.image.save(
            serializer.validated_data["image"].name, serializer.validated_data["image"]
        )

        return Response(data={"result": True})

    @action(detail=True, methods=["post"])
    def units(self, request, **kwargs):
        obj = self.get_object()

        if not request.user.has_perm("screenshot.edit", obj.translation):
            raise PermissionDenied()

        if "unit_id" not in request.data:
            raise ParseError("Missing unit_id parameter")

        try:
            unit = obj.translation.unit_set.get(pk=int(request.data["unit_id"]))
        except (Unit.DoesNotExist, ValueError) as error:
            raise ParseError(str(error), "invalid")

        obj.units.add(unit)
        serializer = ScreenshotSerializer(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(detail=True, methods=["delete"], url_path="units/(?P<unit_id>[0-9]+)")
    def delete_units(self, request, pk, unit_id):
        obj = self.get_object()
        if not request.user.has_perm("screenshot.edit", obj.translation):
            raise PermissionDenied()

        try:
            unit = obj.translation.unit_set.get(pk=unit_id)
        except Unit.DoesNotExist as error:
            raise Http404(str(error))
        obj.units.remove(unit)
        return Response(status=HTTP_204_NO_CONTENT)

    def create(self, request, *args, **kwargs):
        required_params = ["project_slug", "component_slug", "language_code"]
        for param in required_params:
            if param not in request.data:
                raise ParseError(f"Missing {param} parameter")

        try:
            translation = Translation.objects.get(
                component__project__slug=request.data["project_slug"],
                component__slug=request.data["component_slug"],
                language__code=request.data["language_code"],
            )
        except Translation.DoesNotExist as error:
            raise ParseError(str(error), "invalid")

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

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not request.user.has_perm("screenshot.edit", instance.translation):
            self.permission_denied(request, "Can not edit screenshot.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
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
        return Change.objects.last_changes(self.request.user).order_by("id")


class ComponentListViewSet(viewsets.ModelViewSet):
    """Component lists API."""

    queryset = ComponentList.objects.none()
    serializer_class = ComponentListSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return (
            ComponentList.objects.filter(
                Q(components__project_id__in=self.request.user.allowed_project_ids)
                | Q(components__isnull=True)
            )
            .order_by("id")
            .distinct()
        )

    def perm_check(self, request):
        if not request.user.has_perm("componentlist.edit"):
            self.permission_denied(request, "Can not manage component lists")

    def update(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.perm_check(request)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def components(self, request, **kwargs):
        obj = self.get_object()
        self.perm_check(request)

        if "component_id" not in request.data:
            raise ParseError("Missing component_id parameter")

        try:
            component = Component.objects.filter_access(self.request.user).get(
                pk=int(request.data["component_id"]),
            )
        except (Component.DoesNotExist, ValueError) as error:
            raise ParseError(str(error), "invalid")

        obj.components.add(component)
        serializer = self.serializer_class(obj, context={"request": request})

        return Response(serializer.data, status=HTTP_200_OK)

    @action(
        detail=True,
        methods=["delete"],
        url_path="components/(?P<component_slug>[^/.]+)",
    )
    def delete_components(self, request, slug, component_slug):
        obj = self.get_object()
        self.perm_check(request)

        try:
            component = obj.components.get(slug=component_slug)
        except Component.DoesNotExist as error:
            raise Http404(str(error))
        obj.components.remove(component)
        return Response(status=HTTP_204_NO_CONTENT)


class Metrics(APIView):
    """Metrics view for monitoring."""

    permission_classes = (IsAuthenticated,)

    # pylint: disable=redefined-builtin
    def get(self, request, format=None):
        """Return a list of all users."""
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


class TasksViewSet(ViewSet):
    def get_task(self, request, pk, permission: Optional[str] = None) -> AsyncResult:
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
                    raise PermissionDenied()
            elif not request.user.can_access_component(component):
                raise PermissionDenied()

        return task, component

    def retrieve(self, request, pk=None):
        task, _component = self.get_task(request, pk)
        result = task.result
        return Response(
            {
                "completed": is_task_ready(task),
                "progress": get_task_progress(task),
                "result": str(result) if isinstance(result, Exception) else result,
                "log": "\n".join(cache.get(f"task-log-{task.id}", [])),
            }
        )

    def destroy(self, request, pk=None):
        task, component = self.get_task(request, pk, "component.edit")
        if not is_task_ready(task) and component is not None:
            task.revoke(terminate=True)
            # Unlink task from component
            if component.background_task_id == pk:
                component.delete_background_task()
        return Response(status=HTTP_204_NO_CONTENT)


class AddonViewSet(viewsets.ReadOnlyModelViewSet, UpdateModelMixin, DestroyModelMixin):

    queryset = Addon.objects.all()
    serializer_class = AddonSerializer

    def perm_check(self, request, instance: Addon):
        if not request.user.has_perm("component.edit", instance.component):
            self.permission_denied(request, "Can not manage addons")

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perm_check(request, instance)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perm_check(request, instance)
        return super().destroy(request, *args, **kwargs)
