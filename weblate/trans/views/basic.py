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

from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.utils import translation
from django.views.decorators.cache import never_cache
from django.utils.encoding import force_text
from django.utils.html import escape
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext as _
from django.utils.translation.trans_real import parse_accept_lang_header
import django.views.defaults

from weblate.checks.models import Check
from weblate.utils import messages
from weblate.utils.stats import prefetch_stats
from weblate.trans.models import (
    Project, Translation, ComponentList, Change, Unit, IndexUpdate,
)
from weblate.utils.requirements import get_versions, get_optional_versions
from weblate.lang.models import Language
from weblate.trans.forms import (
    get_upload_form, SearchForm, SiteSearchForm,
    AutoForm, ReviewForm, get_new_language_form,
    ReportsForm, ReplaceForm, NewUnitForm, MassStateForm, DownloadForm,
)
from weblate.accounts.models import Profile
from weblate.accounts.notifications import notify_new_language
from weblate.trans.views.helper import (
    get_project, get_component, get_translation,
    try_set_language,
)
from weblate.trans.util import render, sort_objects, sort_unicode
from weblate.vcs.gpg import get_gpg_public_key, get_gpg_sign_key


def get_untranslated(base, limit=None):
    """Filter untranslated."""
    result = []
    for item in prefetch_stats(base):
        if item.stats.translated != item.stats.all:
            result.append(item)
            if limit and len(result) >= limit:
                return result
    return result


def get_suggestions(request, user, base):
    """Return suggested translations for user"""
    if user.is_authenticated and user.profile.languages.exists():
        # Remove user subscriptions
        result = get_untranslated(
            base.exclude(
                component__project__in=user.profile.subscriptions.all()
            ),
            10
        )
        if result:
            return result
    return get_untranslated(base.order_by('?'), 10)


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


def get_user_translations(request, user):
    """Get list of translations in user languages

    Works also for anonymous users based on current UI language.
    """
    result = Translation.objects.prefetch().filter(
        component__project__in=user.allowed_projects
    ).order_by(
        'component__priority',
        'component__project__name',
        'component__name'
    )

    if user.is_authenticated and user.profile.languages.exists():
        result = result.filter(
            language__in=user.profile.languages.all(),
        )
    else:
        # Filter based on session language
        tmp = result.filter(
            language=guess_user_language(request, result)
        )
        if tmp:
            return tmp

    return result


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

    user_translations = get_user_translations(request, user)

    suggestions = get_suggestions(request, user, user_translations)

    # Warn about not filled in username (usually caused by migration of
    # users from older system
    if user.is_authenticated and user.full_name == '':
        messages.warning(
            request,
            mark_safe('<a href="{0}">{1}</a>'.format(
                reverse('profile') + '#account',
                escape(_('Please set your full name in your profile.'))
            ))
        )

    usersubscriptions = None

    componentlists = list(ComponentList.objects.filter(show_dashboard=True))
    for componentlist in componentlists:
        componentlist.translations = prefetch_stats(
            user_translations.filter(
                component__in=componentlist.components.all()
            )
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
        subscribed_projects = user.allowed_projects.filter(
            profile=user.profile
        )

        usersubscriptions = user_translations.filter(
            component__project__in=subscribed_projects
        )

        if user.profile.hide_completed:
            usersubscriptions = get_untranslated(usersubscriptions)
            user_translations = get_untranslated(user_translations)
            for componentlist in componentlists:
                componentlist.translations = get_untranslated(
                    componentlist.translations
                )
        usersubscriptions = prefetch_stats(usersubscriptions)

    return render(
        request,
        'index.html',
        {
            'allow_index': True,
            'suggestions': suggestions,
            'search_form': SiteSearchForm(),
            'usersubscriptions': usersubscriptions,
            'userlanguages': prefetch_stats(user_translations),
            'componentlists': componentlists,
            'all_componentlists': prefetch_stats(ComponentList.objects.all()),
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
    percent = stats_obj.translated_percent

    languages = obj.get_language_count()

    context = {
        'allow_index': True,
        'object': obj,
        'project': obj,
        'languages': languages,
        'total': obj.stats.source_strings,
        'percent': percent,
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

    last_changes = Change.objects.for_project(obj)[:10]

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
            'components': prefetch_stats(obj.component_set.select_related()),
        }
    )


@never_cache
def show_component(request, project, component):
    obj = get_component(request, project, component)

    last_changes = Change.objects.for_component(obj)[:10]

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
    last_changes = Change.objects.for_translation(obj)[:10]

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
            'last_changes_url': urlencode(obj.get_kwargs()),
            'show_only_component': True,
            'pending_fulltext': obj.unit_set.filter(
                id__in=IndexUpdate.objects.filter(
                    to_delete=False
                ).values('unitid')
            ).exists(),
            'other_translations': prefetch_stats(
                Translation.objects.prefetch().filter(
                    component__project=obj.component.project,
                    language=obj.language,
                ).exclude(
                    pk=obj.pk
                )
            ),
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
            'gpg_key_id': get_gpg_sign_key(),
            'gpg_key': get_gpg_public_key(),
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
    for project in prefetch_stats(Project.objects.all()):
        total_strings.append(project.stats.source_strings)
        total_words.append(project.stats.source_words)

    context['total_translations'] = totals['translated__sum']
    context['total_suggestions'] = totals['suggested__sum']
    context['total_users'] = totals['id__count']
    context['total_strings'] = sum(total_strings)
    context['total_units'] = Unit.objects.count()
    context['total_words'] = sum(total_words)
    context['total_languages'] = Language.objects.filter(
        translation__pk__gt=0
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
