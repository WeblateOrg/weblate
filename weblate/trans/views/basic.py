# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.cache import never_cache
from django.utils.encoding import force_text
from django.utils.http import urlencode
from django.utils.translation import ugettext as _
import django.views.defaults

from weblate.formats.exporters import list_exporters
from weblate.utils import messages
from weblate.utils.stats import prefetch_stats
from weblate.utils.views import get_paginator
from weblate.trans.models import Translation, ComponentList, Change, Unit
from weblate.lang.models import Language
from weblate.trans.forms import (
    get_upload_form, SearchForm,
    AutoForm, ReviewForm, get_new_language_form,
    ReportsForm, ReplaceForm, NewUnitForm, BulkStateForm, DownloadForm,
    DeleteForm, ProjectRenameForm, ComponentRenameForm, ComponentMoveForm,
    WhiteboardForm,
)
from weblate.accounts.notifications import notify_new_language
from weblate.utils.views import (
    get_project, get_component, get_translation,
    try_set_language,
)
from weblate.trans.util import render, sort_objects, sort_unicode


def optional_form(form, perm_user, perm, perm_obj, **kwargs):
    if not perm_user.has_perm(perm, perm_obj):
        return None
    return form(**kwargs)


@never_cache
def list_projects(request):
    """List all projects"""

    return render(
        request,
        'projects.html',
        {
            'allow_index': True,
            'projects': prefetch_stats(request.user.allowed_projects),
            'title': _('Projects'),
        }
    )


def show_engage(request, project, lang=None):
    # Get project object, skipping ACL
    obj = get_project(request, project, skip_acl=True)

    # Handle language parameter
    if lang is not None:
        language = Language.objects.try_get(code=lang)
    else:
        language = None
    if language:
        try_set_language(lang)
        stats_obj = obj.stats.get_single_language_stats(language)
    else:
        stats_obj = obj.stats

    return render(
        request,
        'engage.html',
        {
            'allow_index': True,
            'object': obj,
            'project': obj,
            'languages': stats_obj.languages,
            'total': obj.stats.source_strings,
            'percent': stats_obj.translated_percent,
            'language': language,
            'title': _('Get involved in {0}!').format(obj),
        }
    )


@never_cache
def show_project(request, project):
    obj = get_project(request, project)
    user = request.user

    dict_langs = Language.objects.filter(
        dictionary__project=obj
    ).annotate(Count('dictionary'))

    last_changes = Change.objects.prefetch().filter(project=obj)[:10]

    language_stats = sort_unicode(
        obj.stats.get_language_stats(), lambda x: force_text(x.language.name)
    )

    # Paginate components of project.
    all_components = obj.component_set.select_related()
    components = prefetch_stats(get_paginator(
        request, all_components
    ))

    return render(
        request,
        'project.html',
        {
            'allow_index': True,
            'object': obj,
            'project': obj,
            'dicts': dict_langs,
            'last_changes': last_changes,
            'last_changes_url': urlencode(
                {'project': obj.slug}
            ),
            'language_stats': language_stats,
            'language_count': Language.objects.filter(
                translation__component__project=obj
            ).distinct().count(),
            'search_form': SearchForm(),
            'whiteboard_form': optional_form(
                WhiteboardForm, user, 'project.edit', obj
            ),
            'delete_form': optional_form(
                DeleteForm, user, 'project.edit', obj, obj=obj
            ),
            'rename_form': optional_form(
                ProjectRenameForm, user, 'project.edit', obj,
                request=request, instance=obj
            ),
            'replace_form': optional_form(ReplaceForm, user, 'unit.edit', obj),
            'mass_state_form': optional_form(
                BulkStateForm, user, 'translation.auto', obj,
                user=user, obj=obj
            ),
            'components': components,
            'licenses': ', '.join(
                sorted(set([x.license for x in all_components if x.license]))
            ),
        }
    )


@never_cache
def show_component(request, project, component):
    obj = get_component(request, project, component)
    user = request.user

    last_changes = Change.objects.prefetch().filter(component=obj)[:10]

    return render(
        request,
        'component.html',
        {
            'allow_index': True,
            'object': obj,
            'project': obj.project,
            'translations': sort_objects(
                prefetch_stats(obj.translation_set.all())
            ),
            'show_language': 1,
            'reports_form': ReportsForm(),
            'last_changes': last_changes,
            'last_changes_url': urlencode(
                {'component': obj.slug, 'project': obj.project.slug}
            ),
            'language_count': Language.objects.filter(
                translation__component=obj
            ).distinct().count(),
            'replace_form': optional_form(ReplaceForm, user, 'unit.edit', obj),
            'mass_state_form': optional_form(
                BulkStateForm, user, 'translation.auto', obj,
                user=user, obj=obj
            ),
            'whiteboard_form': optional_form(
                WhiteboardForm, user, 'component.edit', obj
            ),
            'delete_form': optional_form(
                DeleteForm, user, 'component.edit', obj, obj=obj
            ),
            'rename_form': optional_form(
                ComponentRenameForm, user, 'component.edit', obj,
                request=request, instance=obj
            ),
            'move_form': optional_form(
                ComponentMoveForm, user, 'component.edit', obj,
                request=request, instance=obj
            ),
            'search_form': SearchForm(),
        }
    )


@never_cache
def show_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    obj.stats.ensure_all()
    last_changes = Change.objects.prefetch().filter(translation=obj)[:10]
    user = request.user

    # Get form
    form = get_upload_form(user, obj)

    # Search form for everybody
    search_form = SearchForm()

    # Review form for logged in users
    if user.is_anonymous:
        review_form = None
    else:
        review_form = ReviewForm(
            initial={'exclude_user': user.username}
        )

    return render(
        request,
        'translation.html',
        {
            'allow_index': True,
            'object': obj,
            'project': obj.component.project,
            'form': form,
            'download_form': DownloadForm(),
            'autoform': optional_form(
                AutoForm, user, 'translation.auto', obj,
                user=user, obj=obj
            ),
            'search_form': search_form,
            'review_form': review_form,
            'replace_form': optional_form(ReplaceForm, user, 'unit.edit', obj),
            'mass_state_form': optional_form(
                BulkStateForm, user, 'translation.auto', obj,
                user=user, obj=obj
            ),
            'new_unit_form': NewUnitForm(
                user,
                initial={
                    'value': Unit(translation=obj, id_hash=-1),
                },
            ),
            'whiteboard_form': optional_form(
                WhiteboardForm, user, 'component.edit', obj
            ),
            'delete_form': optional_form(
                DeleteForm, user, 'translation.delete', obj, obj=obj
            ),
            'last_changes': last_changes,
            'last_changes_url': urlencode(obj.get_reverse_url_kwargs()),
            'show_only_component': True,
            'other_translations': prefetch_stats(
                Translation.objects.prefetch().filter(
                    component__project=obj.component.project,
                    language=obj.language,
                ).exclude(
                    pk=obj.pk
                )
            ),
            'exporters': list_exporters(),
        }
    )


def not_found(request, exception=None):
    """Error handler showing list of available projects."""
    return render(
        request,
        '404.html',
        {
            'request_path': request.path,
            'title': _('Page Not Found'),
        },
        status=404
    )


def denied(request, exception=None):
    """Error handler showing list of available projects."""
    return render(
        request,
        '403.html',
        {
            'request_path': request.path,
            'title': _('Permission Denied'),
        },
        status=403
    )


def server_error(request):
    """Error handler for server errors."""
    try:
        if (hasattr(settings, 'RAVEN_CONFIG') and
                'public_dsn' in settings.RAVEN_CONFIG):
            sentry_dsn = settings.RAVEN_CONFIG['public_dsn']
        else:
            sentry_dsn = None
        return render(
            request,
            '500.html',
            {
                'request_path': request.path,
                'title': _('Internal Server Error'),
                'sentry_dsn': sentry_dsn,
            },
            status=500,
        )
    except Exception:
        return django.views.defaults.server_error(request)


@never_cache
def data_project(request, project):
    obj = get_project(request, project)
    return render(
        request,
        'data.html',
        {
            'object': obj,
            'project': obj,
        }
    )


@never_cache
@login_required
def new_language(request, project, component):
    obj = get_component(request, project, component)

    form_class = get_new_language_form(request, obj)

    if request.method == 'POST':
        form = form_class(obj, request.POST)

        if form.is_valid():
            langs = form.cleaned_data['lang']
            for language in Language.objects.filter(code__in=langs):
                if obj.new_lang == 'contact':
                    notify_new_language(obj, language, request.user)
                    messages.success(
                        request,
                        _(
                            "A request for a new translation has been "
                            "sent to the project's maintainers."
                        )
                    )
                elif obj.new_lang == 'add':
                    obj.add_new_language(language, request)
            return redirect(obj)
        else:
            messages.error(
                request,
                _('Please fix errors in the form.')
            )
    else:
        form = form_class(obj)

    return render(
        request,
        'new-language.html',
        {
            'object': obj,
            'project': obj.project,
            'form': form,
        }
    )


@never_cache
def healthz(request):
    """Simple health check endpoint"""
    return HttpResponse('ok')


@never_cache
def show_component_list(request, name):
    obj = get_object_or_404(ComponentList, slug=name)

    return render(
        request,
        'component-list.html',
        {
            'object': obj,
        }
    )
