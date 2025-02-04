# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import translation
from django.utils.html import format_html
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache

from weblate.accounts.models import Profile
from weblate.lang.models import Language
from weblate.metrics.models import Metric
from weblate.trans.forms import ReportsForm, SearchForm
from weblate.trans.models import Component, ComponentList, Project, Translation
from weblate.trans.models.component import translation_prefetch_tasks
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.models.translation import GhostTranslation, TranslationQuerySet
from weblate.trans.util import render
from weblate.utils import messages
from weblate.utils.stats import prefetch_stats
from weblate.utils.views import get_paginator

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest, User


def get_untranslated(base, limit: int | None = None):
    """Filter untranslated."""
    result = []
    for item in base:
        if item.stats.translated != item.stats.all:
            result.append(item)
            if limit and len(result) >= limit:
                return result
    return result


def get_suggestions(
    user: User,
    user_has_languages: bool,
    base: TranslationQuerySet,
    filtered: bool = False,
):
    """Return suggested translations for user."""
    if not filtered:
        non_alerts = base.annotate(alert_count=Count("component__alert__pk")).filter(
            alert_count=0
        )
        result = get_suggestions(user, user_has_languages, non_alerts, True)
        if result:
            return result
    if user_has_languages:
        # Remove user subscriptions
        result = get_untranslated(
            prefetch_stats(
                base.exclude(component__project__in=user.profile.watched.all())
            ),
            10,
        )
        if result:
            return result
    return get_untranslated(prefetch_stats(base), 10)


def guess_user_language(
    request: AuthenticatedHttpRequest, translations: TranslationQuerySet
) -> Language | None:
    """
    Guess user language for translations.

    It tries following:

    - Use session language.
    - Parse Accept-Language header.
    - Fallback to random language.
    """
    # Session language
    session_lang = translation.get_language()
    if session_lang and session_lang != "en":
        try:
            return Language.objects.get(code=session_lang)
        except Language.DoesNotExist:
            pass

    # Try getting from Accept-Language
    if request.accepted_language:
        return request.accepted_language

    # Random language from existing translations, we do not want to list all
    # languages by default
    try:
        return translations.order_by("?")[0].language
    except IndexError:
        # There are no existing translations
        return None


def get_user_translations(
    request: AuthenticatedHttpRequest, user: User, user_has_languages: bool
):
    """
    Get list of translations in user languages.

    Works also for anonymous users based on current UI language.
    """
    result = Translation.objects.prefetch().filter_access(user).order()

    if user_has_languages:
        result = result.filter(language__in=user.profile.all_languages)
    else:
        # Filter based on session language
        tmp = result.filter(language=guess_user_language(request, result))
        if tmp:
            return tmp

    return result


def redirect_single_project(user: User):
    target: Component | Project
    if isinstance(settings.SINGLE_PROJECT, str):
        target = project = Project.objects.get(slug=settings.SINGLE_PROJECT)
    elif Component.objects.filter(is_glossary=False).count() == 1:
        target = component = Component.objects.filter(is_glossary=False).get()
        project = component.project
    elif Project.objects.count() == 1:
        target = project = Project.objects.get()
    else:
        msg = "SINGLE_PROJECT enabled, but no project found"
        raise ImproperlyConfigured(msg)

    if not user.is_authenticated and not user.can_access_project(project):
        return redirect(f"{settings.LOGIN_URL}?next={target.get_absolute_url()}")
    return redirect(target)


@never_cache
def home(request: AuthenticatedHttpRequest):
    """Home page handler serving different views based on user."""
    user = request.user

    # This is used on Hosted Weblate to handle removed translation projects.
    # The redirect itself is done in the http server.
    if "removed" in request.GET:
        messages.warning(
            request,
            gettext(
                "The project you were looking for has been removed, "
                "however you are welcome to contribute to other ones."
            ),
        )

    if "show_set_password" in request.session:
        messages.warning(
            request,
            gettext(
                "You have activated your account, now you should set "
                "the password to be able to sign in next time."
            ),
        )
        return redirect("password")

    # Warn about not filled in username, this is usually caused by migration of
    # users from older system
    if user.is_authenticated and (not user.full_name or not user.email):
        messages.warning(
            request,
            format_html(
                '<a href="{}">{}</a>',
                reverse("profile") + "#account",
                gettext("Please set your full name and e-mail in your profile."),
            ),
        )

    # Redirect to single project or component
    if settings.SINGLE_PROJECT:
        return redirect_single_project(user)

    if not user.is_authenticated:
        return dashboard_anonymous(request)

    return dashboard_user(request)


def fetch_componentlists(user: User, user_translations):
    componentlists = list(
        ComponentList.objects.filter(
            show_dashboard=True,
            components__project__in=user.allowed_projects,
        )
        .distinct()
        .order()
    )
    for componentlist in componentlists:
        components = componentlist.components.filter_access(user)
        # Force fetching the query now
        list(components)

        translations = translation_prefetch_tasks(
            prefetch_stats(list(user_translations.filter(component__in=components)))
        )

        # Show ghost translations for user languages
        existing = {
            (translation.component.slug, translation.language.code)
            for translation in translations
        }
        languages = user.profile.all_languages
        for component in components:
            for language in languages:
                if (
                    component.slug,
                    language.code,
                ) in existing or not component.can_add_new_language(user, fast=True):
                    continue
                translations.append(GhostTranslation(component, language))

        componentlist.translations = translations

    # Filter out component lists with translations
    # This will remove the ones where user doesn't have access to anything
    return [c for c in componentlists if c.translations]


def dashboard_user(request: AuthenticatedHttpRequest):
    """Home page of Weblate for authenticated user."""
    user = request.user

    user_has_languages = user.is_authenticated and user.profile.all_languages

    user_translations = get_user_translations(request, user, user_has_languages)

    suggestions = get_suggestions(user, user_has_languages, user_translations)

    usersubscriptions = None

    componentlists = fetch_componentlists(request.user, user_translations)

    active_tab_id = user.profile.dashboard_view
    active_tab_slug = Profile.DASHBOARD_SLUGS.get(active_tab_id)
    if (
        active_tab_id == Profile.DASHBOARD_COMPONENT_LIST
        and user.profile.dashboard_component_list
    ):
        active_tab_slug = user.profile.dashboard_component_list.tab_slug()

    if user.is_authenticated:
        usersubscriptions = user_translations.filter_access(user).filter(
            component__project__in=user.watched_projects
        )

        if user.profile.hide_completed:
            usersubscriptions = get_untranslated(prefetch_stats(usersubscriptions))
            for componentlist in componentlists:
                componentlist.translations = get_untranslated(
                    prefetch_stats(componentlist.translations)
                )

        usersubscriptions = get_paginator(request, usersubscriptions, stats=True)
        usersubscriptions = translation_prefetch_tasks(usersubscriptions)
        owned = user.owned_projects.order()
    else:
        owned = Project.objects.none()

    return render(
        request,
        "dashboard/user.html",
        {
            "allow_index": True,
            "suggestions": suggestions,
            "search_form": SearchForm(request.user),
            "usersubscriptions": usersubscriptions,
            "componentlists": componentlists,
            "all_componentlists": prefetch_stats(
                ComponentList.objects.filter(
                    components__project__in=request.user.allowed_projects
                )
                .distinct()
                .order()
            ),
            "active_tab_slug": active_tab_slug,
            "reports_form": ReportsForm({}),
            "all_owned_projects": owned,
            "owned_projects": prefetch_project_flags(prefetch_stats(owned[:10])),
        },
    )


def dashboard_anonymous(request: AuthenticatedHttpRequest):
    """Home page of Weblate showing list of projects for anonymous user."""
    top_project_ids_cache = cache.get("dashboard-anonymous-projects")
    if top_project_ids_cache is not None:
        # hiredis-py 3 makes list from set
        top_project_ids = set(top_project_ids_cache)
    else:
        top_projects = sorted(
            prefetch_stats(request.user.allowed_projects),
            key=lambda prj: -prj.stats.monthly_changes,
        )[:20]
        top_project_ids = {p.id for p in top_projects}
        cache.set("dashboard-anonymous-projects", top_project_ids, 3600)
    top_projects = request.user.allowed_projects.filter(id__in=top_project_ids)

    return render(
        request,
        "dashboard/anonymous.html",
        {
            "top_projects": prefetch_stats(prefetch_project_flags(top_projects)),
            "all_projects": Metric.objects.get_current_metric(
                None, Metric.SCOPE_GLOBAL, 0
            )["public_projects"],
        },
    )
