# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.shortcuts import render, redirect
from django.utils.translation import ugettext as _
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
import django.views.defaults

from weblate.trans.models import (
    Project, SubProject, Translation, Check,
    Dictionary, Change, Unit, WhiteboardMessage
)
from weblate.requirements import get_versions, get_optional_versions
from weblate.lang.models import Language
from weblate.trans.util import redirect_param
from weblate.trans.forms import (
    get_upload_form, SearchForm,
    AutoForm, ReviewForm, NewLanguageForm,
    AddUserForm,
)
from weblate.accounts.models import Profile, notify_new_language
from weblate.trans.views.helper import (
    get_project, get_subproject, get_translation,
    try_set_language,
)
import weblate

import datetime
from urllib import urlencode


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

    wb_messages = WhiteboardMessage.objects.all()

    projects = Project.objects.all_acl(request.user)
    if projects.count() == 1:
        projects = SubProject.objects.filter(
            project=projects[0]
        ).select_related()

    # Warn about not filled in username (usually caused by migration of
    # users from older system
    if not request.user.is_anonymous() and request.user.first_name == '':
        messages.warning(
            request,
            _('Please set your full name in your profile.')
        )

    # Some stats
    top_translations = Profile.objects.order_by('-translated')[:10]
    top_suggestions = Profile.objects.order_by('-suggested')[:10]
    last_changes = Change.objects.last_changes(request.user)[:10]

    return render(
        request,
        'index.html',
        {
            'projects': projects,
            'top_translations': top_translations.select_related('user'),
            'top_suggestions': top_suggestions.select_related('user'),
            'last_changes': last_changes,
            'last_changes_rss': reverse('rss'),
            'last_changes_url': '',
            'search_form': SearchForm(),
            'whiteboard_messages': wb_messages,
        }
    )


def search(request):
    """
    Performs site-wide search on units.
    """
    search_form = SearchForm(request.GET)
    context = {
        'search_form': search_form,
    }

    if search_form.is_valid():
        units = Unit.objects.search(
            None,
            search_form.cleaned_data,
        ).select_related(
            'translation',
        )

        # Filter results by ACL
        acl_projects, filtered = Project.objects.get_acl_status(request.user)
        if filtered:
            units = units.filter(
                translation__subproject__project__in=acl_projects
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
        language = try_set_language(lang)

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
            'last_changes_rss': reverse(
                'rss-project',
                kwargs={'project': obj.slug}
            ),
            'last_changes_url': urlencode(
                {'project': obj.slug}
            ),
            'add_user_form': AddUserForm(),
        }
    )


def show_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    last_changes = Change.objects.prefetch().filter(
        translation__subproject=obj
    )[:10]

    new_lang_form = NewLanguageForm()

    return render(
        request,
        'subproject.html',
        {
            'object': obj,
            'project': obj.project,
            'translations': obj.translation_set.enabled(),
            'show_language': 1,
            'last_changes': last_changes,
            'last_changes_rss': reverse(
                'rss-subproject',
                kwargs={'subproject': obj.slug, 'project': obj.project.slug}
            ),
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
    obj.is_locked(request)

    # Get form
    form = get_upload_form(request)()

    # Is user allowed to do automatic translation?
    if request.user.has_perm('trans.automatic_translation'):
        autoform = AutoForm(obj)
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
                'date': datetime.date.today() - datetime.timedelta(days=31)
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
            'last_changes_rss': reverse(
                'rss-translation',
                kwargs=obj.get_kwargs(),
            ),
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
            status=500
        )
    except Exception:
        return django.views.defaults.server_error(request)


def about(request):
    """
    Shows about page with version information.
    """
    context = {}
    totals = Profile.objects.aggregate(
        Sum('translated'), Sum('suggested'), Count('id')
    )
    total_strings = 0
    total_words = 0
    for project in SubProject.objects.iterator():
        try:
            translation = project.translation_set.all()[0]
            total_strings += translation.total
            total_words += translation.total_words
        except (IndexError, Translation.DoesNotExist):
            pass
    context['title'] = _('About Weblate')
    context['total_translations'] = totals['translated__sum']
    context['total_suggestions'] = totals['suggested__sum']
    context['total_users'] = totals['id__count']
    context['total_strings'] = total_strings
    context['total_words'] = total_words
    context['total_languages'] = Language.objects.filter(
        translation__total__gt=0
    ).distinct().count()
    context['total_checks'] = Check.objects.count()
    context['ignored_checks'] = Check.objects.filter(ignore=True).count()
    context['versions'] = get_versions() + get_optional_versions()

    return render(
        request,
        'about.html',
        context
    )


def data_root(request):
    return render(
        request,
        'data-root.html',
        {
            'hooks_docs': weblate.get_doc_url('api', 'hooks'),
            'api_docs': weblate.get_doc_url('api', 'exports'),
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
            'api_docs': weblate.get_doc_url('api', 'exports'),
            'rss_docs': weblate.get_doc_url('api', 'rss'),
        }
    )


@login_required
def new_language(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    form = NewLanguageForm(request.POST)

    if form.is_valid():
        language = Language.objects.get(code=form.cleaned_data['lang'])
        same_lang = obj.translation_set.filter(language=language)
        if same_lang.exists():
            messages.error(
                request,
                _('Chosen translation already exists in this project!')
            )
        elif obj.new_lang == 'contact':
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
            _('Failed to process new translation request!')
        )

    return redirect(
        'subproject',
        subproject=obj.slug,
        project=obj.project.slug
    )


@require_POST
@permission_required('trans.manage_acl')
def add_user(request, project):
    obj = get_project(request, project)

    form = AddUserForm(request.POST)

    if not obj.enable_acl:
        messages.error(request, _('ACL not enabled for this project!'))
    elif form.is_valid():
        try:
            user = User.objects.get(
                Q(username=form.cleaned_data['name']) |
                Q(email=form.cleaned_data['name'])
            )
            obj.add_user(user)
            messages.success(
                request, _('User has been added to this project.')
            )
        except User.DoesNotExist:
            messages.error(request, _('No matching user found!'))
        except User.MultipleObjectsReturned:
            messages.error(request, _('More users matched!'))
    else:
        messages.error(request, _('Invalid user specified!'))

    return redirect_param(
        'project',
        '#acl',
        project=obj.slug,
    )


@require_POST
@permission_required('trans.manage_acl')
def delete_user(request, project):
    obj = get_project(request, project)

    form = AddUserForm(request.POST)

    if form.is_valid():
        try:
            user = User.objects.get(
                username=form.cleaned_data['name']
            )
            obj.remove_user(user)
            messages.success(
                request, _('User has been removed from this project.')
            )
        except User.DoesNotExist:
            messages.error(request, _('No matching user found!'))
        except User.MultipleObjectsReturned:
            messages.error(request, _('More users matched!'))
    else:
        messages.error(request, _('Invalid user specified!'))

    return redirect_param(
        'project',
        '#acl',
        project=obj.slug,
    )
