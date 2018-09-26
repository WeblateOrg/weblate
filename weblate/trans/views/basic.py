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

from __future__ import unicode_literals

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.cache import never_cache
from django.utils.encoding import force_text
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
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
    ReportsForm, ReplaceForm, NewUnitForm, MassStateForm, DownloadForm,
)
from weblate.accounts.notifications import notify_new_language
from weblate.utils.views import (
    get_project, get_component, get_translation,
    try_set_language,
)
from weblate.trans.util import render, sort_objects, sort_unicode


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

    context = {
        'allow_index': True,
        'object': obj,
        'project': obj,
        'languages': stats_obj.languages,
        'total': obj.stats.source_strings,
        'percent': stats_obj.translated_percent,
        'url': obj.get_absolute_url(),
        'lang_url': obj.get_absolute_url() + '#languages',
        'language': language,
        'title': _('Get involved in {0}!').format(obj),
    }

    # Render text
    if language is None:
        status_text = _(
            '<a href="%(url)s">Translation project for %(project)s</a> '
            'currently contains %(total)s strings for translation and is '
            '<a href="%(lang_url)s">being translated into %(languages)s '
            'languages</a>. Overall, these translations are %(percent)s%% '
            'complete.'
        )
    else:
        # Translators: line of text in engagement page, please use your
        # language name instead of English
        status_text = _('<a href="%(url)s">Translation project for '
                        '%(project)s</a> into English currently contains '
                        '%(total)s strings for translation and is '
                        '%(percent)s%% complete.')
        if 'English' in status_text:
            status_text = status_text.replace('English', language.name)

    context['status_text'] = mark_safe(status_text % context)

    return render(
        request,
        'engage.html',
        context
    )


@never_cache
def show_project(request, project):
    obj = get_project(request, project)

    dict_langs = Language.objects.filter(
        dictionary__project=obj
    ).annotate(Count('dictionary'))

    last_changes = Change.objects.prefetch().filter(project=obj)[:10]

    language_stats = sort_unicode(
        obj.stats.get_language_stats(), lambda x: force_text(x.language.name)
    )

    # Is user allowed to do automatic translation?
    if request.user.has_perm('translation.auto', obj):
        mass_state_form = MassStateForm(request.user, obj)
    else:
        mass_state_form = None

    if request.user.has_perm('unit.edit', obj):
        replace_form = ReplaceForm()
    else:
        replace_form = None

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
            'replace_form': replace_form,
            'mass_state_form': mass_state_form,
            'components': components,
            'licenses': ', '.join(
                sorted(set([x.license for x in all_components if x.license]))
            ),
        }
    )


@never_cache
def show_component(request, project, component):
    obj = get_component(request, project, component)

    last_changes = Change.objects.prefetch().filter(component=obj)[:10]

    # Is user allowed to do automatic translation?
    if request.user.has_perm('translation.auto', obj):
        mass_state_form = MassStateForm(request.user, obj)
    else:
        mass_state_form = None

    if request.user.has_perm('unit.edit', obj):
        replace_form = ReplaceForm()
    else:
        replace_form = None

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
            'replace_form': replace_form,
            'mass_state_form': mass_state_form,
            'search_form': SearchForm(),
        }
    )


@never_cache
def show_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    obj.stats.ensure_all()
    last_changes = Change.objects.prefetch().filter(translation=obj)[:10]

    # Get form
    form = get_upload_form(request.user, obj)

    # Is user allowed to do automatic translation?
    if request.user.has_perm('translation.auto', obj):
        mass_state_form = MassStateForm(request.user, obj)
    else:
        mass_state_form = None

    # Is user allowed to do automatic translation?
    if request.user.has_perm('translation.auto', obj):
        autoform = AutoForm(obj, request.user)
    else:
        autoform = None

    # Search form for everybody
    search_form = SearchForm()

    # Review form for logged in users
    if request.user.is_anonymous:
        review_form = None
    else:
        review_form = ReviewForm(
            initial={'exclude_user': request.user.username}
        )

    if request.user.has_perm('unit.edit', obj):
        replace_form = ReplaceForm()
    else:
        replace_form = None

    return render(
        request,
        'translation.html',
        {
            'allow_index': True,
            'object': obj,
            'project': obj.component.project,
            'form': form,
            'download_form': DownloadForm(),
            'autoform': autoform,
            'search_form': search_form,
            'review_form': review_form,
            'replace_form': replace_form,
            'mass_state_form': mass_state_form,
            'new_unit_form': NewUnitForm(
                request.user,
                initial={
                    'value': Unit(translation=obj, id_hash=-1),
                },
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
