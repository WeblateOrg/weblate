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

import datetime

from django.shortcuts import redirect
from django.utils import translation
from django.utils.translation import ugettext as _
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse
from django.utils.safestring import mark_safe
from django.utils import timezone
import django.views.defaults

from six import string_types
from six.moves.urllib.parse import urlencode

from weblate.trans import messages
from weblate.trans.models import (
    Project, SubProject, Translation, Check, ComponentList,
    Dictionary, Change, Unit,
)
from weblate.requirements import get_versions, get_optional_versions
from weblate.lang.models import Language
from weblate.trans.forms import (
    get_upload_form, SearchForm, SiteSearchForm,
    AutoForm, ReviewForm, get_new_language_form,
    UserManageForm, ReportsForm,
)
from weblate.trans.permissions import (
    can_automatic_translation, can_add_translation,
)
from weblate.accounts.models import Profile, notify_new_language
from weblate.trans.views.helper import (
    get_project, get_subproject, get_translation,
    try_set_language,
)
from weblate.trans.util import render, sort_objects
import weblate


def get_suggestions(request, user, project_ids):
    """Returns suggested translations for user"""

    # Grab all untranslated translations
    base = Translation.objects.prefetch().filter(
        subproject__project_id__in=project_ids,
    ).exclude(
        total=F('translated'),
    ).order_by(
        '-translated'
    )
    all_matching = base.none()

    if user.is_authenticated() and user.profile.languages.exists():
        # Find other translations for user language
        all_matching = base.filter(
            language__in=user.profile.languages.all(),
        ).exclude(
            subproject__project__in=user.profile.subscriptions.all()
        )

    else:
        # Filter based on session language
        session_lang = translation.get_language()
        if session_lang and session_lang != 'en':
            all_matching = base.filter(
                language__code=session_lang
            )

        # Fall back to all
        if not all_matching:
            all_matching = base.exclude(
                language__code='en'
            )

    return all_matching[:10]


def home(request):
    """
    Home page of Weblate showing list of projects, stats
    and user links if logged in.
    """

    if 'show_set_password' in request.session:
        messages.warning(
            request,
            _(
                'You have activated your account, now you should set '
                'the password to be able to login next time.'
            )
        )
        return redirect('password')

    project_ids = Project.objects.get_acl_ids(request.user)

    suggestions = get_suggestions(
        request, request.user, project_ids
    )

    # Warn about not filled in username (usually caused by migration of
    # users from older system
    if not request.user.is_anonymous() and request.user.first_name == '':
        messages.warning(
            request,
            _('Please set your full name in your profile.')
        )

    # Some stats
    last_changes = Change.objects.last_changes(request.user)

    # Dashboard project/subproject view
    componentlists = ComponentList.objects.all()
    # dashboard_choices is dict with labels of choices as a keys
    dashboard_choices = dict(Profile.DASHBOARD_CHOICES)
    usersubscriptions = None
    userlanguages = None
    active_tab_id = Profile.DASHBOARD_SUGGESTIONS
    active_tab_slug = Profile.DASHBOARD_SLUGS.get(active_tab_id)

    if request.user.is_authenticated():
        active_tab_id = request.user.profile.dashboard_view
        active_tab_slug = Profile.DASHBOARD_SLUGS.get(active_tab_id)
        if active_tab_id == Profile.DASHBOARD_COMPONENT_LIST:
            clist = request.user.profile.dashboard_component_list
            active_tab_slug = clist.tab_slug()
            dashboard_choices[active_tab_id] = clist.name

        # Ensure ACL filtering applies (user could have been removed
        # from the project meanwhile)
        subscribed_projects = request.user.profile.subscriptions.filter(
            id__in=project_ids
        )

        last_changes = last_changes.filter(
            subproject__project__in=subscribed_projects
        )

        components_by_language = Translation.objects.prefetch().filter(
            language__in=request.user.profile.languages.all(),
        ).order_by(
            'subproject__project__name', 'subproject__name'
        )

        usersubscriptions = components_by_language.filter(
            subproject__project__in=subscribed_projects
        )
        userlanguages = components_by_language.filter(
            subproject__project_id__in=project_ids
        )

        for componentlist in componentlists:
            componentlist.translations = components_by_language.filter(
                subproject__in=componentlist.components.all()
            )

    return render(
        request,
        'index.html',
        {
            'suggestions': suggestions,
            'last_changes': last_changes[:10],
            'last_changes_url': '',
            'search_form': SiteSearchForm(),
            'usersubscriptions': usersubscriptions,
            'userlanguages': userlanguages,
            'componentlists': componentlists,
            'active_tab_slug': active_tab_slug,
            'active_tab_label': dashboard_choices.get(active_tab_id)
        }
    )


def list_projects(request):
    """Lists all projects"""

    return render(
        request,
        'projects.html',
        {
            'projects': Project.objects.all_acl(request.user),
            'title': _('Projects'),
        }
    )


def search(request):
    """
    Performs site-wide search on units.
    """
    search_form = SiteSearchForm(request.GET)
    context = {
        'search_form': search_form,
    }

    if search_form.is_valid():
        # Filter results by ACL
        acl_projects = Project.objects.get_acl_ids(request.user)

        units = Unit.objects.search(
            None,
            search_form.cleaned_data,
        ).filter(
            translation__subproject__project_id__in=acl_projects
        ).select_related(
            'translation',
        )

        limit = request.GET.get('limit', 50)
        page = request.GET.get('page', 1)

        paginator = Paginator(units, limit)

        try:
            units = paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page.
            units = paginator.page(1)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of
            # results.
            units = paginator.page(paginator.num_pages)

        context['page_obj'] = units
        context['title'] = _('Search for %s') % (
            search_form.cleaned_data['q']
        )
        context['query_string'] = search_form.urlencode()
        context['search_query'] = search_form.cleaned_data['q']
    else:
        messages.error(request, _('Invalid search query!'))

    return render(
        request,
        'search.html',
        context
    )


def show_engage(request, project, lang=None):
    # Get project object, skipping ACL
    obj = get_project(request, project, skip_acl=True)

    # Handle language parameter
    language = None
    if lang is not None:
        try_set_language(lang)
        language = Language.objects.try_get(code=lang)

    context = {
        'object': obj,
        'project': obj,
        'languages': obj.get_language_count(),
        'total': obj.get_total(),
        'percent': obj.get_translated_percent(language),
        'url': obj.get_absolute_url(),
        'language': language,
    }

    # Render text
    if language is None:
        status_text = _(
            '<a href="%(url)s">Translation project for %(project)s</a> '
            'currently contains %(total)s strings for translation and is '
            '<a href="%(url)s">being translated into %(languages)s languages'
            '</a>. Overall, these translations are %(percent)s%% complete.'
        )
    else:
        # Translators: line of text in engagement widget, please use your
        # language name instead of English
        status_text = _(
            '<a href="%(url)s">Translation project for %(project)s</a> into '
            'English currently contains %(total)s strings for translation and '
            'is %(percent)s%% complete.'
        )
        if 'English' in status_text:
            status_text = status_text.replace('English', language.name)

    context['status_text'] = mark_safe(status_text % context)

    return render(
        request,
        'engage.html',
        context
    )


def show_project(request, project):
    obj = get_project(request, project)

    dict_langs = Dictionary.objects.filter(
        project=obj
    ).values_list(
        'language', flat=True
    ).distinct()

    dicts = []
    for language in Language.objects.filter(id__in=dict_langs):
        dicts.append(
            {
                'language': language,
                'count': Dictionary.objects.filter(
                    language=language,
                    project=obj
                ).count(),
            }
        )

    last_changes = Change.objects.prefetch().filter(
        Q(translation__subproject__project=obj) |
        Q(dictionary__project=obj)
    )[:10]

    return render(
        request,
        'project.html',
        {
            'object': obj,
            'project': obj,
            'dicts': dicts,
            'last_changes': last_changes,
            'last_changes_url': urlencode(
                {'project': obj.slug}
            ),
            'add_user_form': UserManageForm(),
        }
    )


def show_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    last_changes = Change.objects.prefetch().filter(
        translation__subproject=obj
    )[:10]

    new_lang_form = get_new_language_form(request, obj)(obj)

    return render(
        request,
        'subproject.html',
        {
            'object': obj,
            'project': obj.project,
            'translations': sort_objects(obj.translation_set.enabled()),
            'show_language': 1,
            'reports_form': ReportsForm(),
            'last_changes': last_changes,
            'last_changes_url': urlencode(
                {'subproject': obj.slug, 'project': obj.project.slug}
            ),
            'new_lang_form': new_lang_form,
        }
    )


def show_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)
    last_changes = Change.objects.prefetch().filter(
        translation=obj
    )[:10]

    # Check locks
    obj.is_locked(request.user)

    # Get form
    form = get_upload_form(request.user, obj.subproject.project)()

    # Is user allowed to do automatic translation?
    if can_automatic_translation(request.user, obj.subproject.project):
        autoform = AutoForm(obj, request.user)
    else:
        autoform = None

    # Search form for everybody
    search_form = SearchForm()

    # Review form for logged in users
    if request.user.is_anonymous():
        review_form = None
    else:
        review_form = ReviewForm(
            initial={
                'date': timezone.now().date() - datetime.timedelta(days=31)
            }
        )

    return render(
        request,
        'translation.html',
        {
            'object': obj,
            'project': obj.subproject.project,
            'form': form,
            'autoform': autoform,
            'search_form': search_form,
            'review_form': review_form,
            'last_changes': last_changes,
            'last_changes_url': urlencode(obj.get_kwargs()),
            'show_only_component': True,
            'other_translations': Translation.objects.filter(
                subproject__project=obj.subproject.project,
                language=obj.language,
            ).exclude(
                pk=obj.pk
            ),
        }
    )


def not_found(request):
    """
    Error handler showing list of available projects.
    """
    return render(
        request,
        '404.html',
        {
            'request_path': request.path,
            'title': _('Page Not Found'),
        },
        status=404
    )


def denied(request):
    """
    Error handler showing list of available projects.
    """
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
    """
    Error handler for server errors.
    """
    try:
        return render(
            request,
            '500.html',
            {
                'request_path': request.path,
                'title': _('Internal Server Error'),
            },
            status=500,
        )
    except Exception:
        return django.views.defaults.server_error(request)


def about(request):
    """
    Shows about page with version information.
    """
    context = {}
    context['title'] = _('About Weblate')
    context['versions'] = get_versions() + get_optional_versions()

    return render(
        request,
        'about.html',
        context
    )


def stats(request):
    """Various stats about Weblate"""

    context = {}

    context['title'] = _('Weblate statistics')

    totals = Profile.objects.aggregate(
        Sum('translated'), Sum('suggested'), Count('id')
    )
    total_strings = []
    total_words = []
    for project in SubProject.objects.iterator():
        try:
            translation_obj = project.translation_set.all()[0]
            total_strings.append(translation_obj.total)
            total_words.append(translation_obj.total_words)
        except IndexError:
            pass

    context['total_translations'] = totals['translated__sum']
    context['total_suggestions'] = totals['suggested__sum']
    context['total_users'] = totals['id__count']
    context['total_strings'] = sum(total_strings)
    context['total_words'] = sum(total_words)
    context['total_languages'] = Language.objects.filter(
        translation__total__gt=0
    ).distinct().count()
    context['total_checks'] = Check.objects.count()
    context['ignored_checks'] = Check.objects.filter(ignore=True).count()

    top_translations = Profile.objects.order_by('-translated')[:10]
    top_suggestions = Profile.objects.order_by('-suggested')[:10]

    context['top_translations'] = top_translations.select_related('user')
    context['top_suggestions'] = top_suggestions.select_related('user')

    return render(
        request,
        'stats.html',
        context
    )


def data_root(request):
    return render(
        request,
        'data-root.html',
        {
            'hooks_docs': weblate.get_doc_url('api', 'hooks'),
            'api_docs': weblate.get_doc_url('api'),
            'rss_docs': weblate.get_doc_url('api', 'rss'),
        }
    )


def data_project(request, project):
    obj = get_project(request, project)
    return render(
        request,
        'data.html',
        {
            'object': obj,
            'project': obj,
            'hooks_docs': weblate.get_doc_url('api', 'hooks'),
            'api_docs': weblate.get_doc_url('api'),
            'rss_docs': weblate.get_doc_url('api', 'rss'),
        }
    )


@login_required
def new_language(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    if not can_add_translation(request.user, obj.project):
        raise PermissionDenied()

    form = get_new_language_form(request, obj)(obj, request.POST)

    if form.is_valid():
        langs = form.cleaned_data['lang']
        if isinstance(langs, string_types):
            langs = [langs]
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
    else:
        messages.error(
            request,
            _('Invalid language chosen!')
        )

    return redirect(obj)


def healthz(request):
    """Simple health check endpoint"""
    return HttpResponse('ok')
