# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from django.shortcuts import render_to_response, redirect
from django.utils.translation import ugettext as _
from django.template import RequestContext, loader
from django.http import HttpResponseNotFound, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.utils.safestring import mark_safe

from trans.models import (
    Project, SubProject, Translation, Check,
    Dictionary, Change, Unit
)
from trans.requirements import get_versions, get_optional_versions
from lang.models import Language
from trans.forms import (
    UploadForm, SimpleUploadForm, ExtraUploadForm, SearchForm,
    AutoForm, ReviewForm, NewLanguageForm,
)
from accounts.models import Profile, notify_new_language
from trans.views.helper import (
    get_project, get_subproject, get_translation,
    try_set_language,
)
import weblate

import datetime
from urllib import urlencode


def home(request):
    '''
    Home page of Weblate showing list of projects, stats
    and user links if logged in.
    '''

    if 'show_set_password' in request.session:
        messages.warning(
            request,
            _(
                'You have activated your account, now you should set '
                'the password to be able to login next time.'
            )
        )
        return redirect('password')

    projects = Project.objects.all_acl(request.user)
    acl_projects = projects
    if projects.count() == 1:
        projects = SubProject.objects.filter(
            project=projects[0]
        ).select_related()

    # Warn about not filled in username (usually caused by migration of
    # users from older system
    if not request.user.is_anonymous() and request.user.get_full_name() == '':
        messages.warning(
            request,
            _('Please set your full name in your profile.')
        )

    # Load user translations if user is authenticated
    usertranslations = None
    if request.user.is_authenticated():
        profile = request.user.get_profile()

        usertranslations = Translation.objects.filter(
            language__in=profile.languages.all()
        ).order_by(
            'subproject__project__name', 'subproject__name'
        ).select_related()

    # Some stats
    top_translations = Profile.objects.order_by('-translated')[:10]
    top_suggestions = Profile.objects.order_by('-suggested')[:10]
    last_changes = Change.objects.prefetch().filter(
        Q(translation__subproject__project__in=acl_projects) |
        Q(dictionary__project__in=acl_projects)
    ).order_by('-timestamp')[:10]

    return render_to_response('index.html', RequestContext(request, {
        'projects': projects,
        'top_translations': top_translations.select_related('user'),
        'top_suggestions': top_suggestions.select_related('user'),
        'last_changes': last_changes,
        'last_changes_rss': reverse('rss'),
        'last_changes_url': '',
        'usertranslations': usertranslations,
        'search_form': SearchForm(),
    }))


def search(request):
    '''
    Performs sitewide search on units.
    '''
    search_form = SearchForm(request.GET)
    context = {
        'search_form': search_form,
    }

    if search_form.is_valid():
        units = Unit.objects.search(
            search_form.cleaned_data['search'],
            search_form.cleaned_data['q'],
            search_form.cleaned_data['src'],
            search_form.cleaned_data['ctx'],
            search_form.cleaned_data['tgt'],
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

        context['units'] = units
        context['title'] = _('Search for %s') % (
            search_form.cleaned_data['q']
        )
        context['query_string'] = search_form.urlencode()
        context['search_query'] = search_form.cleaned_data['q']
    else:
        messages.error(request, _('Invalid search query!'))

    return render_to_response(
        'search.html',
        RequestContext(request, context)
    )


def show_engage(request, project, lang=None):
    # Get project object
    obj = get_project(request, project)

    # Handle language parameter
    language = None
    if lang is not None:
        language = try_set_language(lang)

    context = {
        'object': obj,
        'project': obj.name,
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

    return render_to_response('engage.html', RequestContext(request, context))


def show_project(request, project):
    obj = get_project(request, project)

    dicts = Dictionary.objects.filter(
        project=obj
    ).values_list(
        'language', flat=True
    ).distinct()

    last_changes = Change.objects.prefetch().filter(
        Q(translation__subproject__project=obj) |
        Q(dictionary__project=obj)
    ).order_by('-timestamp')[:10]

    return render_to_response('project.html', RequestContext(request, {
        'object': obj,
        'dicts': Language.objects.filter(id__in=dicts),
        'last_changes': last_changes,
        'last_changes_rss': reverse(
            'rss-project',
            kwargs={'project': obj.slug}
        ),
        'last_changes_url': urlencode(
            {'project': obj.slug}
        ),
    }))


def show_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    last_changes = Change.objects.prefetch().filter(
        translation__subproject=obj
    ).order_by('-timestamp')[:10]

    new_lang_form = NewLanguageForm()

    return render_to_response('subproject.html', RequestContext(request, {
        'object': obj,
        'last_changes': last_changes,
        'last_changes_rss': reverse(
            'rss-subproject',
            kwargs={'subproject': obj.slug, 'project': obj.project.slug}
        ),
        'last_changes_url': urlencode(
            {'subproject': obj.slug, 'project': obj.project.slug}
        ),
        'new_lang_form': new_lang_form,
    }))


def review_source(request, project, subproject):
    '''
    Listing of source strings to review.
    '''
    obj = get_subproject(request, project, subproject)

    # Grab first translation in subproject
    # (this assumes all have same source strings)
    try:
        source = obj.translation_set.all()[0]
    except Translation.DoesNotExist:
        raise Http404('No translation exists in this subproject.')

    # Grab search type and page number
    rqtype = request.GET.get('type', 'all')
    limit = request.GET.get('limit', 50)
    page = request.GET.get('page', 1)
    ignored = 'ignored' in request.GET

    # Fiter units
    sources = source.unit_set.filter_type(rqtype, source, ignored)

    paginator = Paginator(sources, limit)

    try:
        sources = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        sources = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        sources = paginator.page(paginator.num_pages)

    return render_to_response('source-review.html', RequestContext(request, {
        'object': obj,
        'source': source,
        'sources': sources,
        'rqtype': rqtype,
        'title': _('Review source strings in %s') % obj.__unicode__(),
    }))


def show_source(request, project, subproject):
    '''
    Show source strings summary and checks.
    '''
    obj = get_subproject(request, project, subproject)

    # Grab first translation in subproject
    # (this assumes all have same source strings)
    try:
        source = obj.translation_set.all()[0]
    except Translation.DoesNotExist:
        raise Http404('No translation exists in this subproject.')

    return render_to_response('source.html', RequestContext(request, {
        'object': obj,
        'source': source,
        'title': _('Source strings in %s') % obj.__unicode__(),
    }))


def show_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)
    last_changes = Change.objects.prefetch().filter(
        translation=obj
    ).order_by('-timestamp')[:10]

    # Check locks
    obj.is_locked(request)

    # How much is user allowed to configure upload?
    if request.user.has_perm('trans.author_translation'):
        form = ExtraUploadForm()
    elif request.user.has_perm('trans.overwrite_translation'):
        form = UploadForm()
    else:
        form = SimpleUploadForm()

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

    return render_to_response('translation.html', RequestContext(request, {
        'object': obj,
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
    }))


def not_found(request):
    '''
    Error handler showing list of available projects.
    '''
    template = loader.get_template('404.html')
    return HttpResponseNotFound(
        template.render(RequestContext(request, {
            'request_path': request.path,
            'title': _('Page Not Found'),
            'projects': Project.objects.all_acl(request.user),
        }))
    )


def about(request):
    '''
    Shows about page with version information.
    '''
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
        except Translation.DoesNotExist:
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

    return render_to_response('about.html', RequestContext(request, context))


def data_root(request):
    return render_to_response('data-root.html', RequestContext(request, {
        'hooks_docs': weblate.get_doc_url('api', 'hooks'),
        'api_docs': weblate.get_doc_url('api', 'exports'),
        'rss_docs': weblate.get_doc_url('api', 'rss'),
        'projects': Project.objects.all_acl(request.user),
    }))


def data_project(request, project):
    obj = get_project(request, project)
    return render_to_response('data.html', RequestContext(request, {
        'object': obj,
        'hooks_docs': weblate.get_doc_url('api', 'hooks'),
        'api_docs': weblate.get_doc_url('api', 'exports'),
        'rss_docs': weblate.get_doc_url('api', 'rss'),
    }))


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
        elif obj.project.new_lang == 'contact':
            notify_new_language(obj, language, request.user)
            messages.info(
                request,
                _(
                    "A request for a new translation has been "
                    "sent to the project's maintainers."
                )
            )
        elif obj.project.new_lang == 'add':
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
