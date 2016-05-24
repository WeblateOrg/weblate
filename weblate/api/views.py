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

import os.path

from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.http import Http404, HttpResponse
from django.utils.encoding import smart_text

from rest_framework import parsers, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.utils import formatting

from weblate.api.serializers import (
    ProjectSerializer, ComponentSerializer, TranslationSerializer,
    LanguageSerializer, LockRequestSerializer, LockSerializer,
    RepoRequestSerializer, StatisticsSerializer,
)
from weblate.trans.exporters import EXPORTERS
from weblate.trans.models import Project, SubProject, Translation, Change
from weblate.trans.permissions import (
    can_upload_translation, can_lock_subproject, can_see_repository_status,
    can_commit_translation, can_update_translation, can_reset_translation,
    can_push_translation,
)
from weblate.lang.models import Language
from weblate.trans.views.helper import download_translation_file
from weblate import get_doc_url

REPO_OPERATIONS = {
    'push': (can_push_translation, 'do_push'),
    'pull': (can_update_translation, 'do_update'),
    'reset': (can_reset_translation, 'do_reset'),
    'commit': (can_commit_translation, 'commit_pending'),
}

DOC_TEXT = """
See <a href="{0}">the Weblate's Web API documentation</a> for detailed
description of the API.
"""


def get_view_description(view_cls, html=False):
    """
    Given a view class, return a textual description to represent the view.
    This name is used in the browsable API, and in OPTIONS responses.

    This function is the default for the `VIEW_DESCRIPTION_FUNCTION` setting.
    """
    description = view_cls.__doc__ or ''
    description = formatting.dedent(smart_text(description))

    if hasattr(view_cls, 'serializer_class'):
        doc_url = get_doc_url(
            'api'
            '{0}s'.format(
                view_cls.serializer_class.Meta.model.__name__.lower()
            )
        )
    else:
        doc_url = get_doc_url('api')

    description = '\n\n'.join((
        description,
        DOC_TEXT.format(doc_url)
    ))

    if html:
        return formatting.markup_description(description)
    return description


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
        permission_check, method = REPO_OPERATIONS[operation]

        if not permission_check(request.user, project):
            raise PermissionDenied()

        return getattr(obj, method)(request)

    @detail_route(
        methods=['get', 'post'],
        serializer_class=RepoRequestSerializer
    )
    def repository(self, request, **kwargs):
        obj = self.get_object()

        if isinstance(obj, Translation):
            project = obj.subproject.project
        elif isinstance(obj, SubProject):
            project = obj.project
        else:
            project = obj

        if request.method == 'POST':
            serializer = RepoRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            data = {
                'result': self.repository_operation(
                    request, obj, project,
                    serializer.validated_data['operation']
                )
            }

            storage = get_messages(request)
            if storage:
                data['detail'] = '\n'.join([m.message for m in storage])

            return Response(data)

        if not can_see_repository_status(request.user, project):
            raise PermissionDenied()

        data = {
            'needs_commit': obj.repo_needs_commit(),
            'needs_merge': obj.repo_needs_merge(),
            'needs_push': obj.repo_needs_push(),
        }

        if isinstance(obj, Project):
            data['url'] = reverse(
                'api:project-repository',
                kwargs={'slug': obj.slug},
                request=request
            )
        else:
            data['remote_commit'] = obj.get_last_remote_commit()

            if isinstance(obj, Translation):
                subproject = obj.subproject
                data['url'] = reverse(
                    'api:translation-repository',
                    kwargs={
                        'subproject__project__slug': subproject.project.slug,
                        'subproject__slug': subproject.slug,
                        'language__code': obj.language.code,
                    },
                    request=request
                )
                data['status'] = obj.subproject.repository.status()
                changes = Change.objects.filter(
                    action__in=Change.ACTIONS_REPOSITORY,
                    subproject=obj.subproject,
                )
            else:
                data['url'] = reverse(
                    'api:component-repository',
                    kwargs={
                        'project__slug': obj.project.slug,
                        'slug': obj.slug,
                    },
                    request=request
                )
                data['status'] = obj.repository.status()
                changes = Change.objects.filter(
                    action__in=Change.ACTIONS_REPOSITORY,
                    subproject=obj,
                )

            if changes.exists() and changes[0].is_merge_failure():
                data['merge_failure'] = changes[0].target
            else:
                data['merge_failure'] = None

        return Response(data)


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

    @detail_route(methods=['get'])
    def components(self, request, **kwargs):
        obj = self.get_object()

        queryset = obj.subproject_set.all()
        page = self.paginate_queryset(queryset)

        serializer = ComponentSerializer(
            page,
            many=True,
            context={'request': request},
            remove_fields=('project',),
        )

        return self.get_paginated_response(serializer.data)


class ComponentViewSet(MultipleFieldMixin, WeblateViewSet):
    """Translation components API.
    """
    queryset = SubProject.objects.none()
    serializer_class = ComponentSerializer
    lookup_fields = ('project__slug', 'slug')

    def get_queryset(self):
        return SubProject.objects.prefetch().filter(
            project_id__in=Project.objects.get_acl_ids(self.request.user)
        ).prefetch_related(
            'project__source_language'
        )

    @detail_route(
        methods=['get', 'post'],
        serializer_class=LockRequestSerializer
    )
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

    def download_file(self, filename, content_type):
        """Wrapper for file download"""
        with open(filename, 'rb') as handle:
            response = HttpResponse(
                handle.read(),
                content_type=content_type
            )
        response['Content-Disposition'] = 'attachment; filename="{0}"'.format(
            os.path.basename(filename)
        )
        return response

    @detail_route(methods=['get'])
    def monolingual_base(self, request, **kwargs):
        obj = self.get_object()

        if not obj.template:
            raise Http404('No template found!')

        return self.download_file(
            obj.get_template_filename(),
            obj.template_store.mimetype
        )

    @detail_route(methods=['get'])
    def new_template(self, request, **kwargs):
        obj = self.get_object()

        if not obj.new_base:
            raise Http404('No file found!')

        return self.download_file(
            obj.get_new_base_filename(),
            'application/binary',
        )

    @detail_route(methods=['get'])
    def translations(self, request, **kwargs):
        obj = self.get_object()

        queryset = obj.translation_set.all()
        page = self.paginate_queryset(queryset)

        serializer = TranslationSerializer(
            page,
            many=True,
            context={'request': request},
            remove_fields=('component',),
        )

        return self.get_paginated_response(serializer.data)

    @detail_route(methods=['get'])
    def statistics(self, request, **kwargs):
        obj = self.get_object()

        queryset = obj.translation_set.all()
        page = self.paginate_queryset(queryset)

        serializer = StatisticsSerializer(
            page,
            many=True,
            context={'request': request},
        )

        return self.get_paginated_response(serializer.data)


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
        return Translation.objects.prefetch().filter(
            subproject__project_id__in=Project.objects.get_acl_ids(
                self.request.user
            )
        ).prefetch_related(
            'subproject__project__source_language',
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

    @detail_route(methods=['get'])
    def statistics(self, request, **kwargs):
        obj = self.get_object()

        serializer = StatisticsSerializer(
            obj,
            context={'request': request},
        )

        return Response(serializer.data)


class LanguageViewSet(viewsets.ReadOnlyModelViewSet):
    """Languages API.
    """
    queryset = Language.objects.none()
    serializer_class = LanguageSerializer
    lookup_field = 'code'

    def get_queryset(self):
        return Language.objects.have_translation()
