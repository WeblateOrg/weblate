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
from django.shortcuts import redirect
from django.utils import translation
from django.views.decorators.cache import never_cache
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext as _
from django.utils.translation.trans_real import parse_accept_lang_header

from weblate.utils import messages
from weblate.utils.stats import prefetch_stats
from weblate.utils.views import get_paginator
from weblate.trans.models import Translation, ComponentList
from weblate.lang.models import Language
from weblate.trans.forms import SiteSearchForm
from weblate.accounts.models import Profile
from weblate.trans.util import render


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
    """Home page handler serving different views based on user."""

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

    if not request.user.is_authenticated:
        return dashboard_anonymous(request)

    if 'show_set_password' in request.session:
        messages.warning(
            request,
            _(
                'You have activated your account, now you should set '
                'the password to be able to login next time.'
            )
        )
        return redirect('password')

    # Warn about not filled in username (usually caused by migration of
    # users from older system
    if not request.user.full_name or not request.user.email:
        messages.warning(
            request,
            mark_safe('<a href="{0}">{1}</a>'.format(
                reverse('profile') + '#account',
                escape(
                    _('Please set your full name and email in your profile.')
                )
            ))
        )

    return dashboard_user(request)


def dashboard_user(request):
    """Home page of Weblate showing list of projects, stats
    and user links if logged in.
    """

    user = request.user

    user_translations = get_user_translations(request, user)

    suggestions = get_suggestions(request, user, user_translations)

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
        'dashboard/user.html',
        {
            'allow_index': True,
            'suggestions': suggestions,
            'search_form': SiteSearchForm(),
            'usersubscriptions': get_paginator(request, usersubscriptions),
            'userlanguages': prefetch_stats(
                get_paginator(request, user_translations)
            ),
            'componentlists': componentlists,
            'all_componentlists': prefetch_stats(ComponentList.objects.all()),
            'active_tab_slug': active_tab_slug,
        }
    )


def dashboard_anonymous(request):
    """Home page of Weblate showing list of projects for anonymous user."""

    all_projects = prefetch_stats(request.user.allowed_projects)
    top_projects = sorted(
        all_projects,
        key=lambda prj: -prj.stats.recent_changes
    )

    return render(
        request,
        'dashboard/anonymous.html',
        {
            'top_projects': top_projects[:20],
            'all_projects': len(all_projects),
        }
    )
