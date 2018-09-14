# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
"""Helper methods for views."""

from django.core.paginator import Paginator, EmptyPage
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.views.generic.edit import FormView
from django.shortcuts import get_object_or_404
from django.utils.translation import activate, ugettext as _

from weblate.utils import messages
from weblate.formats.exporters import get_exporter
from weblate.trans.models import Project, Component, Translation


def get_page_limit(request, default):
    """Return page and limit as integers."""
    try:
        limit = int(request.GET.get('limit', default))
    except ValueError:
        limit = default
    # Cap it to range 10 - 200
    limit = min(max(10, limit), 200)
    try:
        page = int(request.GET.get('page', 1))
    except ValueError:
        page = 1
    page = max(1, page)
    return page, limit


def get_paginator(request, object_list, default_page_limit=50):
    """Return paginator and current page."""
    page, limit = get_page_limit(request, default_page_limit)
    paginator = Paginator(object_list, limit)
    try:
        return paginator.page(page)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


class ComponentViewMixin(object):
    def get_component(self):
        return get_component(
            self.request,
            self.kwargs['project'],
            self.kwargs['component']
        )


def get_translation(request, project, component, lang, skip_acl=False):
    """Return translation matching parameters."""
    translation = get_object_or_404(
        Translation.objects.prefetch(),
        language__code=lang,
        component__slug=component,
        component__project__slug=project
    )
    if not skip_acl:
        request.user.check_access(translation.component.project)
    return translation


def get_component(request, project, component, skip_acl=False):
    """Return component matching parameters."""
    component = get_object_or_404(
        Component.objects.prefetch(),
        project__slug=project,
        slug=component
    )
    if not skip_acl:
        request.user.check_access(component.project)
    return component


def get_project(request, project, skip_acl=False):
    """Return project matching parameters."""
    project = get_object_or_404(
        Project,
        slug=project,
    )
    if not skip_acl:
        request.user.check_access(project)
    return project


def get_project_translation(request, project=None, component=None, lang=None):
    """Return project, component, translation tuple for given parameters."""

    if lang is not None and component is not None:
        # Language defined? We can get all
        translation = get_translation(request, project, component, lang)
        component = translation.component
        project = component.project
    else:
        translation = None
        if component is not None:
            # Component defined?
            component = get_component(request, project, component)
            project = component.project
        elif project is not None:
            # Only project defined?
            project = get_project(request, project)

    # Return tuple
    return project, component, translation


def try_set_language(lang):
    """Try to activate language"""

    try:
        activate(lang)
    except Exception:
        # Ignore failure on activating language
        activate('en')


def import_message(request, count, message_none, message_ok):
    if count == 0:
        messages.warning(request, message_none)
    else:
        messages.success(request, message_ok % count)


def download_translation_file(translation, fmt=None, units=None):
    if fmt is not None:
        try:
            exporter = get_exporter(fmt)(translation=translation)
        except KeyError:
            raise Http404('File format not supported')
        if units is None:
            units = translation.unit_set.all()
        exporter.add_units(units)
        return exporter.get_response(
            '{{project}}-{0}-{{language}}.{{extension}}'.format(
                translation.component.slug
            )
        )

    # Force flushing pending units
    translation.commit_pending('download', None)

    srcfilename = translation.get_filename()

    # Construct file name (do not use real filename as it is usually not
    # that useful)
    filename = '{0}-{1}-{2}.{3}'.format(
        translation.component.project.slug,
        translation.component.slug,
        translation.language.code,
        translation.store.extension
    )

    # Create response
    with open(srcfilename) as handle:
        response = HttpResponse(
            handle.read(),
            content_type=translation.store.mimetype
        )

    # Fill in response headers
    response['Content-Disposition'] = 'attachment; filename={0}'.format(
        filename
    )

    return response


def show_form_errors(request, form):
    """Show all form errors as a message."""
    for error in form.non_field_errors():
        messages.error(request, error)
    for field in form:
        for error in field.errors:
            messages.error(
                request,
                _('Error in parameter %(field)s: %(error)s') % {
                    'field': field.name,
                    'error': error
                }
            )


class ErrorFormView(FormView):
    def form_invalid(self, form):
        """If the form is invalid, redirect to the supplied URL."""
        show_form_errors(self.request, form)
        return HttpResponseRedirect(self.get_success_url())

    def get(self, request, *args, **kwargs):
        """There is no GET view here."""
        return HttpResponseRedirect(self.get_success_url())
