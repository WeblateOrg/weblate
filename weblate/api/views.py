# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.http import Http404

from rest_framework import parsers, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response

from weblate.api.serializers import (
    ProjectSerializer, ComponentSerializer, TranslationSerializer,
    LanguageSerializer, LockRequestSerializer, LockSerializer,
    RepoRequestSerializer,
)
from weblate.trans.exporters import EXPORTERS
from weblate.trans.models import Project, SubProject, Translation
from weblate.trans.permissions import (
    can_upload_translation, can_lock_subproject, can_see_repository_status,
    can_commit_translation, can_update_translation, can_reset_translation,
    can_push_translation,
)
from weblate.lang.models import Language
from weblate.trans.views.helper import download_translation_file


class MultipleFieldMixin(object):
    """
    Apply this mixin to any view or viewset to get multiple field filtering
    based on a `lookup_fields` attribute, instead of the default single field
    filtering.
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


class WeblateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Allows to skip content negotiation for certain requests.
    """
    raw_urls = ()

    def perform_content_negotiation(self, request, force=False):
        """Custom content negotiation"""
        if request.resolver_match.url_name in self.raw_urls:
            fmt = self.format_kwarg or request.query_params.get('format')
            if fmt is None or fmt in EXPORTERS:
                renderers = self.get_renderers()
                return (renderers[0], renderers[0].media_type)
            raise Http404('Not supported exporter')
        return super(WeblateViewSet, self).perform_content_negotiation(
            request, force
        )

    def repository_operation(self, request, obj, project, operation):
        OPERATIONS = {
            'push': (can_push_translation, 'do_push'),
            'pull': (can_update_translation, 'do_update'),
            'reset': (can_reset_translation, 'do_reset'),
            'commit': (can_commit_translation, 'commit_pending'),
        }
        permission_check, method = OPERATIONS[operation]

        if not permission_check(request.user, project):
            raise PermissionDenied()

        getattr(obj, method)(request)

    @detail_route(methods=['get', 'post'])
    def repository(self, request, **kwargs):
        obj = self.get_object()

        if hasattr(obj, 'subproject'):
            project = obj.subproject.project
        elif hasattr(obj, 'project'):
            project = obj.project
        else:
            project = obj

        if not can_see_repository_status(request.user, project):
            raise PermissionDenied()

        if request.method == 'POST':
            serializer = RepoRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            self.repository_operation(
                request, obj, project, serializer.validated_data['operation']
            )

        return Response(
            data={
                'needs_commit': obj.repo_needs_commit(),
                'needs_merge': obj.repo_needs_merge(),
                'needs_push': obj.repo_needs_push(),
            }
        )


class ProjectViewSet(WeblateViewSet):
    """Translation projects API.
    """
    queryset = Project.objects.none()
    serializer_class = ProjectSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Project.objects.all_acl(self.request.user).prefetch_related(
            'source_language'
        )


class ComponentViewSet(MultipleFieldMixin, WeblateViewSet):
    """Translation components API.
    """
    queryset = SubProject.objects.none()
    serializer_class = ComponentSerializer
    lookup_fields = ('project__slug', 'slug')

    def get_queryset(self):
        acl_projects, filtered = Project.objects.get_acl_status(
            self.request.user
        )
        if filtered:
            result = SubProject.objects.filter(project__in=acl_projects)
        else:
            result = SubProject.objects.all()
        return result.prefetch_related(
            'project',
            'project__source_language'
        )

    @detail_route(methods=['get', 'post'])
    def lock(self, request, **kwargs):
        obj = self.get_object()

        if request.method == 'POST':
            if not can_lock_subproject(request.user, obj.project):
                raise PermissionDenied()

            serializer = LockRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            if serializer.validated_data['lock']:
                obj.do_lock(request.user)
            else:
                obj.do_unlock(request.user)

        return Response(data=LockSerializer(obj).data)


class TranslationViewSet(MultipleFieldMixin, WeblateViewSet):
    """Translation components API.
    """
    queryset = Translation.objects.none()
    serializer_class = TranslationSerializer
    lookup_fields = (
        'subproject__project__slug', 'subproject__slug', 'language__code',
    )
    raw_urls = (
        'translation-file',
    )

    def get_queryset(self):
        acl_projects, filtered = Project.objects.get_acl_status(
            self.request.user
        )
        if filtered:
            result = Translation.objects.filter(
                subproject__project__in=acl_projects
            )
        else:
            result = Translation.objects.all()
        return result.prefetch_related(
            'subproject', 'subproject__project',
            'subproject__project__source_language',
            'language',
        )

    @detail_route(
        methods=['get', 'put', 'post'],
        parser_classes=(
            parsers.MultiPartParser,
            parsers.FormParser,
            parsers.FileUploadParser,
        ),
    )
    def file(self, request, **kwargs):
        obj = self.get_object()
        if request.method == 'GET':
            fmt = self.format_kwarg or request.query_params.get('format')
            return download_translation_file(obj, fmt)

        if (not can_upload_translation(request.user, obj) or
                obj.is_locked(request.user)):
            raise PermissionDenied()

        ret, count = obj.merge_upload(
            request,
            request.data['file'],
            False
        )

        return Response(data={'result': ret, 'count': count})


class LanguageViewSet(viewsets.ReadOnlyModelViewSet):
    """Languages API.
    """
    queryset = Language.objects.none()
    serializer_class = LanguageSerializer
    lookup_field = 'code'

    def get_queryset(self):
        return Language.objects.have_translation()
