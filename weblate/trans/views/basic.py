# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import translation
from django.views.decorators.cache import never_cache
from django.utils.encoding import force_text
from django.utils.html import escape
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext as _
from django.utils.translation.trans_real import parse_accept_lang_header
import django.views.defaults

from weblate.utils import messages
from weblate.trans.models import (
    Project, Translation, Check, ComponentList, Change, Unit,
)
from weblate.requirements import get_versions, get_optional_versions
from weblate.lang.models import Language
from weblate.trans.forms import (
    get_upload_form, SearchForm, SiteSearchForm,
    AutoForm, ReviewForm, get_new_language_form,
    ReportsForm, ReplaceForm,
)
from weblate.permissions.helpers import (
    can_automatic_translation, can_translate,
)
from weblate.accounts.models import Profile
from weblate.accounts.notifications import notify_new_language
from weblate.trans.stats import get_per_language_stats
from weblate.trans.views.helper import (
    get_project, get_subproject, get_translation,
    try_set_language,
)
from weblate.trans.util import (
    render, sort_objects, sort_unicode, translation_percent,
)
import weblate


def get_suggestions(request, user, base):
    """Return suggested translations for user"""

    # Grab all untranslated translations
    result = base.exclude(
        total=F('translated'),
    ).order_by(
        '-translated'
    )

    if user.is_authenticated and user.profile.languages.exists():
        # Remove user subscriptions
        result = result.exclude(
            subproject__project__in=user.profile.subscriptions.all()
        )

    result = result[:10]

    if result:
        return result
    return base.order_by('?')[:10]


def guess_user_language(request, translations):
    """Guess user language for translations.

    It tries following:

    - Use session language.
    - Parse Accept-Language header.
    - Fallback to random language.
    """
    # Session language
    session_lang = translation.get_language()
    if session_lang and session_lang != 'en':
        try:
            return Language.objects.get(code=session_lang)
        except Language.DoesNotExist:
            pass

    # Accept-Language HTTP header, for most browser it consists of browser
    # language with higher rank and OS language with lower rank so it still
    # might be usable guess
    accept = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    for accept_lang, dummy in parse_accept_lang_header(accept):
        if accept_lang == 'en':
            continue
        try:
            return Language.objects.get(code=accept_lang)
        except Language.DoesNotExist:
            continue

    # Random language from existing translations, we do not want to list all
    # languages by default
    try:
        return translations.order_by('?')[0].language
    except IndexError:
        # There are not existing translations, so return any Language objects
        return Language.objects.all()[0]


def get_user_translations(request, user, project_ids):
    """Get list of translations in user languages

    Works also for anonymous users based on current UI language.
    """
    result = Translation.objects.prefetch().filter(
        subproject__project_id__in=project_ids
    )
    if user.is_authenticated and user.profile.languages.exists():
        result = result.filter(
            language__in=user.profile.languages.all(),
        )
    else:
        # Filter based on session language
        result = result.filter(
            language=guess_user_language(request, result)
        )
    return result.order_by(
        'subproject__priority',
        'subproject__project__name',
        'subproject__name'
    )


@never_cache
def home(request):
    """Home page of Weblate showing list of projects, stats
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

    # This is used on Hosted Weblate to handle removed translation projects.
    # The redirect itself is done in the http server.
    if 'removed' in request.GET:
        messages.warning(
            request,
            _(
                'The project you were looking for has been removed, '
                'however you are welcome to contribute to other ones.'
            )
        )

    user = request.user

    project_ids = Project.objects.get_acl_ids(user)

    user_translations = get_user_translations(request, user, project_ids)

    suggestions = get_suggestions(request, user, user_translations)

    # Warn about not filled in username (usually caused by migration of
    # users from older system
    if user.is_authenticated and user.first_name == '':
        messages.warning(
            request,
            mark_safe('<a href="{0}">{1}</a>'.format(
                reverse('profile') + '#account',
                escape(_('Please set your full name in your profile.'))
            ))
        )

    usersubscriptions = None

    componentlists = list(ComponentList.objects.all())
    for componentlist in componentlists:
        componentlist.translations = user_translations.filter(
            subproject__in=componentlist.components.all()
        )
    # Filter out component lists with translations
    # This will remove the ones where user doesn't have access to anything
    componentlists = [c for c in componentlists if c.translations]

    active_tab_id = user.profile.dashboard_view
    active_tab_slug = Profile.DASHBOARD_SLUGS.get(active_tab_id)
    if active_tab_id == Profile.DASHBOARD_COMPONENT_LIST:
        active_tab_slug = user.profile.dashboard_component_list.tab_slug()

    if user.is_authenticated:
        # Ensure ACL filtering applies (user could have been removed
        # from the project meanwhile)
        subscribed_projects = user.profile.subscriptions.filter(
            id__in=project_ids
        )

        usersubscriptions = user_translations.filter(
            subproject__project__in=subscribed_projects
        )

        if user.profile.hide_completed:
            usersubscriptions = usersubscriptions.exclude(
                total=F('translated')
            )
            user_translations = user_translations.exclude(
                total=F('translated')
            )

    return render(
        request,
        'index.html',
        {
            'allow_index': True,
            'suggestions': suggestions,
            'search_form': SiteSearchForm(),
            'usersubscriptions': usersubscriptions,
            'userlanguages': user_translations,
            'componentlists': componentlists,
            'active_tab_slug': active_tab_slug,
        }
    )


@never_cache
def list_projects(request):
    """List all projects"""

    return render(
        request,
        'projects.html',
        {
            'allow_index': True,
            'projects': Project.objects.all_acl(request.user),
            'title': _('Projects'),
        }
    )


def show_engage(request, project, lang=None):
    # Get project object, skipping ACL
    obj = get_project(request, project, skip_acl=True)

    # Handle language parameter
    language = None
    if lang is not None:
        try_set_language(lang)
        language = Language.objects.try_get(code=lang)

    languages = obj.get_language_count()

    context = {
        'allow_index': True,
        'object': obj,
        'project': obj,
        'languages': languages,
        'total': obj.get_total(),
        'percent': obj.get_translated_percent(language),
        'url': obj.get_absolute_url(),
        'language': language,
        'title': _('Get involved in {0}!').format(obj),
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

    last_changes = Change.objects.for_project(obj)[:10]

    language_stats = sort_unicode(
        get_per_language_stats(obj), lambda tup: force_text(tup[0])
    )

    language_stats = [
        (
            tup[0],
            translation_percent(tup[1], tup[2]),
            translation_percent(tup[3], tup[4])
        )
        for tup in language_stats
    ]

    if can_translate(request.user, project=obj):
        replace_form = ReplaceForm()
    else:
        replace_form = None

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
            'unit_count': Unit.objects.filter(
                translation__subproject__project=obj
            ).count(),
            'words_count': obj.get_total_words(),
            'language_count': Language.objects.filter(
                translation__subproject__project=obj
            ).distinct().count(),
            'strings_count': obj.get_total(),
            'source_words_count': obj.get_source_words(),
            'search_form': SearchForm(),
            'replace_form': replace_form,
        }
    )


@never_cache
def show_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    last_changes = Change.objects.for_component(obj)[:10]

    try:
        sample = obj.translation_set.all()[0]
        source_words = sample.total_words
        total_strings = sample.total
    except IndexError:
        source_words = 0
        total_strings = 0

    if can_translate(request.user, project=obj.project):
        replace_form = ReplaceForm()
    else:
        replace_form = None

    return render(
        request,
        'subproject.html',
        {
            'allow_index': True,
            'object': obj,
            'project': obj.project,
            'translations': sort_objects(obj.translation_set.enabled()),
            'show_language': 1,
            'reports_form': ReportsForm(),
            'last_changes': last_changes,
            'last_changes_url': urlencode(
                {'subproject': obj.slug, 'project': obj.project.slug}
            ),
            'unit_count': Unit.objects.filter(
                translation__subproject=obj
            ).count(),
            'words_count': obj.get_total_words(),
            'language_count': Language.objects.filter(
                translation__subproject=obj
            ).distinct().count(),
            'strings_count': total_strings,
            'source_words_count': source_words,
            'replace_form': replace_form,
            'search_form': SearchForm(),
        }
    )


@never_cache
def show_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)
    last_changes = Change.objects.for_translation(obj)[:10]

    # Check locks
    obj.is_locked(request.user)

    # Get form
    form = get_upload_form(request.user, obj)

    # Is user allowed to do automatic translation?
    if can_automatic_translation(request.user, obj.subproject.project):
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

    replace_form = None
    if can_translate(request.user, obj):
        replace_form = ReplaceForm()

    return render(
        request,
        'translation.html',
        {
            'allow_index': True,
            'object': obj,
            'project': obj.subproject.project,
            'form': form,
            'autoform': autoform,
            'search_form': search_form,
            'review_form': review_form,
            'replace_form': replace_form,
            'last_changes': last_changes,
            'last_changes_url': urlencode(obj.get_kwargs()),
            'show_only_component': True,
            'other_translations': Translation.objects.prefetch().filter(
                subproject__project=obj.subproject.project,
                language=obj.language,
            ).exclude(
                pk=obj.pk
            ),
        }
    )


def not_found(request):
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


def denied(request):
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
    """Show about page with version information."""
    return render(
        request,
        'about.html',
        {
            'title': _('About Weblate'),
            'versions': get_versions() + get_optional_versions(),
            'allow_index': True,
        }
    )


def stats(request):
    """View with Various stats about Weblate."""

    context = {}

    context['title'] = _('Weblate statistics')

    totals = Profile.objects.aggregate(
        Sum('translated'), Sum('suggested'), Count('id')
    )
    total_strings = []
    total_words = []
    for project in Project.objects.iterator():
        total_strings.append(project.get_total())
        total_words.append(project.get_source_words())

    context['total_translations'] = totals['translated__sum']
    context['total_suggestions'] = totals['suggested__sum']
    context['total_users'] = totals['id__count']
    context['total_strings'] = sum(total_strings)
    context['total_units'] = Unit.objects.count()
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


@never_cache
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


@never_cache
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


@never_cache
@login_required
def new_language(request, project, subproject):
    obj = get_subproject(request, project, subproject)

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
