# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext, ngettext
from django.views.decorators.cache import never_cache
from django.views.generic import RedirectView

from weblate.auth.models import AuthenticatedHttpRequest
from weblate.formats.models import EXPORTERS
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.exceptions import FileParseError
from weblate.trans.forms import (
    AddCategoryForm,
    AnnouncementForm,
    AutoForm,
    BulkEditForm,
    CategoryDeleteForm,
    CategoryLanguageDeleteForm,
    CategoryRenameForm,
    ComponentDeleteForm,
    ComponentRenameForm,
    DownloadForm,
    ProjectDeleteForm,
    ProjectFilterForm,
    ProjectLanguageDeleteForm,
    ProjectRenameForm,
    ReplaceForm,
    ReportsForm,
    SearchForm,
    TranslationDeleteForm,
    get_new_component_language_form,
    get_new_project_language_form,
    get_new_unit_form,
    get_upload_form,
)
from weblate.trans.models import (
    Category,
    Change,
    Component,
    ComponentList,
    Project,
    Translation,
)
from weblate.trans.models.component import (
    ComponentQuerySet,
    prefetch_tasks,
    translation_prefetch_tasks,
)
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.models.translation import GhostTranslation
from weblate.trans.util import render, sort_unicode, translation_percent
from weblate.utils import messages
from weblate.utils.ratelimit import reset_rate_limit, session_ratelimit_post
from weblate.utils.stats import (
    CategoryLanguage,
    GhostCategoryLanguageStats,
    GhostProjectLanguageStats,
    ProjectLanguage,
    get_non_glossary_stats,
    prefetch_stats,
)
from weblate.utils.views import (
    get_paginator,
    optional_form,
    parse_path,
    show_form_errors,
    try_set_language,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from weblate.auth.models import AuthenticatedHttpRequest, User


@never_cache
def list_projects(request: AuthenticatedHttpRequest):
    """List all projects."""
    query_string = ""
    projects = request.user.allowed_projects
    form = ProjectFilterForm(request.GET)
    if form.is_valid():
        query = {}
        if form.cleaned_data["owned"]:
            user = form.cleaned_data["owned"]
            query["owned"] = user.username
            projects = (user.owned_projects & projects.distinct()).order()
        elif form.cleaned_data["watched"]:
            user = form.cleaned_data["watched"]
            query["watched"] = user.username
            projects = (user.watched_projects & projects).order()
        query_string = urlencode(query)
    else:
        show_form_errors(request, form)

    return render(
        request,
        "projects.html",
        {
            "allow_index": True,
            "projects": prefetch_project_flags(
                get_paginator(request, projects, stats=True)
            ),
            "title": gettext("Projects"),
            "query_string": query_string,
        },
    )


def add_ghost_translations(
    obj: Project | Category,
    user: User,
    components: ComponentQuerySet,
    translations: list,
    generator: Callable,
    **kwargs,
) -> None:
    """Add ghost translations for user languages to the list."""
    components_count = components.count()

    languages = (
        components.values("translation__language")
        .annotate(count=Count("translation__id"))
        .values_list("translation__language", "count")
    )

    language_counter: dict[int, int] = defaultdict(int)
    for language_id, count in languages:
        language_counter[language_id] += count

    languages_in_all_components = {
        language_id
        for language_id, count in language_counter.items()
        if count >= components_count
    }
    for language in user.profile.all_languages:
        if language.id in languages_in_all_components:
            continue
        translations.append(generator(obj, language, **kwargs))


def show_engage(request: AuthenticatedHttpRequest, path):
    # Legacy URL
    if len(path) == 2:
        return redirect("engage", permanent=True, path=[path[0], "-", path[1]])
    # Get project object, skipping ACL
    obj = parse_path(request, path, (ProjectLanguage, Project), skip_acl=True)

    translate_object = None
    if isinstance(obj, ProjectLanguage):
        language = obj.language
        try_set_language(language.code)
        translate_object = obj
        project = obj.project
    else:
        project = obj
        language = None
        guessed_language = (
            Language.objects.filter(translation__component__project=obj)
            .exclude(component__project=obj)
            .distinct()
            .get_request_language(request)
        )
        if guessed_language:
            translate_object = ProjectLanguage(
                project=project, language=guessed_language
            )

    stats = get_non_glossary_stats(obj.stats)

    return render(
        request,
        "engage.html",
        {
            "allow_index": True,
            "object": obj,
            "path_object": obj,
            "project": project,
            "strings_count": stats["source_strings"],
            "languages_count": project.stats.languages,
            "percent": translation_percent(stats["translated"], stats["all"]),
            "language": language,
            "translate_object": translate_object,
            "project_link": format_html(
                '<a href="{}">{}</a>', project.get_absolute_url(), project.name
            ),
            "title": gettext("Get involved in {0}!").format(project),
        },
    )


@never_cache
def show(request: AuthenticatedHttpRequest, path):
    obj = parse_path(
        request,
        path,
        (
            Translation,
            Component,
            Project,
            ProjectLanguage,
            Category,
            CategoryLanguage,
        ),
    )
    if isinstance(obj, Project):
        return show_project(request, obj)
    if isinstance(obj, Component):
        return show_component(request, obj)
    if isinstance(obj, ProjectLanguage):
        return show_project_language(request, obj)
    if isinstance(obj, Category):
        return show_category(request, obj)
    if isinstance(obj, CategoryLanguage):
        return show_category_language(request, obj)
    if isinstance(obj, Translation):
        return show_translation(request, obj)
    msg = f"Not supported show: {obj}"
    raise TypeError(msg)


def show_project_language(request: AuthenticatedHttpRequest, obj: ProjectLanguage):
    language_object = obj.language
    project_object = obj.project
    user = request.user

    last_changes = Change.objects.last_changes(
        user, project=project_object, language=language_object
    ).recent()

    last_announcements = (
        Change.objects.last_changes(
            user, project=project_object, language=language_object
        )
        .filter_announcements()
        .recent()
    )

    translations = translation_prefetch_tasks(
        get_paginator(request, obj.translation_set, stats=True)
    )
    extra_translations = []

    # Add ghost translations
    if user.is_authenticated and translations.paginator.num_pages == 1:
        existing = {translation.component.slug for translation in obj.translation_set}
        missing = project_object.get_child_components_filter(
            lambda qs: qs.exclude(slug__in=existing)
            .prefetch()
            .prefetch_related("source_language")
        )
        for item in missing:
            item.project = project_object
        extra_translations = [
            GhostTranslation(project_object, language_object, component)
            for component in missing
            if component.can_add_new_language(user, fast=True)
        ]

    return render(
        request,
        "language-project.html",
        {
            "allow_index": True,
            "language": language_object,
            "project": project_object,
            "object": obj,
            "path_object": obj,
            "last_changes": last_changes,
            "last_announcements": last_announcements,
            "translations": translations,
            "translation_objects": [*extra_translations, *translations],
            "categories": prefetch_stats(
                CategoryLanguage(category, obj.language)
                for category in obj.project.category_set.filter(category=None).all()
            ),
            "title": f"{project_object} - {language_object}",
            "search_form": SearchForm(
                request=request,
                language=language_object,
                initial=SearchForm.get_initial(request),
                obj=obj,
            ),
            "announcement_form": optional_form(
                AnnouncementForm, user, "announcement.add", project_object
            ),
            "language_stats": project_object.stats.get_single_language_stats(
                language_object
            ),
            "delete_form": optional_form(
                ProjectLanguageDeleteForm, user, "translation.delete", obj, obj=obj
            ),
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj, obj=obj),
            "bulk_state_form": optional_form(
                BulkEditForm,
                user,
                "translation.auto",
                obj,
                user=user,
                obj=obj,
                project=obj.project,
            ),
        },
    )


def show_category_language(request: AuthenticatedHttpRequest, obj):
    language_object = obj.language
    category_object = obj.category
    user = request.user

    last_changes = (
        Change.objects.last_changes(user, language=language_object)
        .for_category(category_object)
        .recent()
    )

    translations = get_paginator(request, obj.translation_set, stats=True)
    extra_translations = []

    # Add ghost translations
    if user.is_authenticated and translations.paginator.num_pages == 1:
        existing = {translation.component.slug for translation in obj.translation_set}
        missing = category_object.component_set.exclude(slug__in=existing)
        extra_translations = [
            GhostTranslation(obj.project, language_object, component)
            for component in missing
            if component.can_add_new_language(user, fast=True)
        ]

    return render(
        request,
        "category-language.html",
        {
            "allow_index": True,
            "language": language_object,
            "category": category_object,
            "object": obj,
            "path_object": obj,
            "last_changes": last_changes,
            "translations": translations,
            "translation_objects": [*extra_translations, *translations],
            "categories": prefetch_stats(
                CategoryLanguage(category, obj.language)
                for category in obj.category.category_set.all()
            ),
            "title": f"{category_object} - {language_object}",
            "search_form": SearchForm(
                request=request,
                language=language_object,
                initial=SearchForm.get_initial(request),
                obj=obj,
            ),
            "language_stats": category_object.stats.get_single_language_stats(
                language_object
            ),
            "delete_form": optional_form(
                CategoryLanguageDeleteForm, user, "translation.delete", obj, obj=obj
            ),
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj, obj=obj),
            "bulk_state_form": optional_form(
                BulkEditForm,
                user,
                "translation.auto",
                obj,
                user=user,
                obj=obj,
                project=obj.category.project,
            ),
        },
    )


def show_project(request: AuthenticatedHttpRequest, obj):
    user = request.user

    all_changes = obj.change_set.filter_components(request.user).prefetch()
    last_changes = all_changes.recent()
    last_announcements = all_changes.filter_announcements().recent()

    all_components = obj.get_child_components_access(
        user, lambda qs: qs.filter(category=None)
    )
    all_components = get_paginator(request, all_components, stats=True)
    for component in all_components:
        component.is_shared = None if component.project == obj else component.project

    language_stats = obj.stats.get_language_stats()
    can_add_language_components = obj.components_user_can_add_new_language(user)
    user_can_add_translation = can_add_language_components.exists()
    if user_can_add_translation:
        add_ghost_translations(
            obj,
            user,
            can_add_language_components,
            language_stats,
            GhostProjectLanguageStats,
        )

    language_stats = sort_unicode(
        language_stats, user.profile.get_translation_orderer(request)
    )

    components = prefetch_tasks(all_components)

    return render(
        request,
        "project.html",
        {
            "allow_index": True,
            "object": obj,
            "path_object": obj,
            "project": obj,
            "last_changes": last_changes,
            "last_announcements": last_announcements,
            "reports_form": ReportsForm({"project": obj}),
            "language_stats": [stat.obj or stat for stat in language_stats],
            "search_form": SearchForm(
                request=request, initial=SearchForm.get_initial(request), obj=obj
            ),
            "announcement_form": optional_form(
                AnnouncementForm, user, "announcement.add", obj
            ),
            "add_form": AddCategoryForm(request, obj) if obj.can_add_category else None,
            "delete_form": optional_form(
                ProjectDeleteForm, user, "project.edit", obj, obj=obj
            ),
            "rename_form": optional_form(
                ProjectRenameForm,
                user,
                "project.edit",
                obj,
                request=request,
                instance=obj,
            ),
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj, obj=obj),
            "bulk_state_form": optional_form(
                BulkEditForm,
                user,
                "translation.auto",
                obj,
                user=user,
                obj=obj,
                project=obj,
            ),
            "components": components,
            "categories": prefetch_stats(obj.category_set.filter(category=None)),
            "user_can_add_translation": user_can_add_translation,
        },
    )


def show_category(request: AuthenticatedHttpRequest, obj):
    user = request.user

    all_changes = (
        Change.objects.for_category(obj).filter_components(request.user).prefetch()
    )

    last_changes = all_changes.recent()
    last_announcements = all_changes.filter_announcements().recent()

    all_components = obj.get_child_components_access(user)
    all_components = get_paginator(request, all_components, stats=True)

    language_stats = obj.stats.get_language_stats()
    can_add_language_components = obj.project.components_user_can_add_new_language(user)
    user_can_add_translation = can_add_language_components.exists()
    if user_can_add_translation:
        add_ghost_translations(
            obj,
            user,
            can_add_language_components,
            language_stats,
            GhostCategoryLanguageStats,
        )

    orderer = user.profile.get_translation_orderer(request)
    language_stats = sort_unicode(
        language_stats,
        lambda x: f"{orderer(x)}-{x.language}",
    )

    components = prefetch_tasks(all_components)

    return render(
        request,
        "category.html",
        {
            "allow_index": True,
            "object": obj,
            "path_object": obj,
            "project": obj,
            "add_form": AddCategoryForm(request, obj) if obj.can_add_category else None,
            "last_changes": last_changes,
            "last_announcements": last_announcements,
            "reports_form": ReportsForm({"category": obj}),
            "language_stats": [stat.obj or stat for stat in language_stats],
            "search_form": SearchForm(
                request=request, initial=SearchForm.get_initial(request), obj=obj
            ),
            "announcement_form": optional_form(
                AnnouncementForm, user, "announcement.add", obj.project
            ),
            "delete_form": optional_form(
                CategoryDeleteForm, user, "project.edit", obj, obj=obj
            ),
            "rename_form": optional_form(
                CategoryRenameForm,
                user,
                "project.edit",
                obj,
                request=request,
                instance=obj,
            ),
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj, obj=obj),
            "bulk_state_form": optional_form(
                BulkEditForm,
                user,
                "translation.auto",
                obj,
                user=user,
                obj=obj,
                project=obj.project,
            ),
            "components": components,
            "categories": prefetch_stats(obj.category_set.all()),
        },
    )


def show_component(request: AuthenticatedHttpRequest, obj: Component):
    user = request.user

    obj.project.project_languages.preload_workflow_settings()

    last_changes = obj.change_set.prefetch().recent(skip_preload="component")

    translations = prefetch_stats(list(obj.translation_set.prefetch_meta()))

    can_add_language_components = obj.project.components_user_can_add_new_language(user)
    user_can_add_translation = can_add_language_components.exists()
    if user_can_add_translation:
        add_ghost_translations(
            obj.project,
            user,
            can_add_language_components,
            translations,
            GhostTranslation,
            component=obj,
        )

    translations = sort_unicode(
        translations, user.profile.get_translation_orderer(request)
    )

    return render(
        request,
        "component.html",
        {
            "allow_index": True,
            "object": obj,
            "path_object": obj,
            "project": obj.project,
            "component": obj,
            "translations": translations,
            "reports_form": ReportsForm({"component": obj}),
            "last_changes": last_changes,
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj, obj=obj),
            "bulk_state_form": optional_form(
                BulkEditForm,
                user,
                "translation.auto",
                obj,
                user=user,
                obj=obj,
                project=obj.project,
            ),
            "announcement_form": optional_form(
                AnnouncementForm, user, "announcement.add", obj
            ),
            "delete_form": optional_form(
                ComponentDeleteForm, user, "component.edit", obj, obj=obj
            ),
            "rename_form": optional_form(
                ComponentRenameForm,
                user,
                "component.edit",
                obj,
                request=request,
                instance=obj,
            ),
            "search_form": SearchForm(
                request=request, initial=SearchForm.get_initial(request), obj=obj
            ),
            "alerts": obj.all_active_alerts
            if "alerts" not in request.GET
            else obj.alert_set.all(),
        },
    )


def show_translation(request: AuthenticatedHttpRequest, obj):
    component = obj.component
    project = component.project
    last_changes = obj.change_set.prefetch().recent(skip_preload="translation")
    user = request.user

    # Get form
    form = get_upload_form(user, obj)

    search_form = SearchForm(
        request=request,
        language=obj.language,
        initial=SearchForm.get_initial(request),
        obj=obj,
    )

    # Translations to same language from other components in this project
    # Show up to 10 of them, needs to be list to append ghost ones later
    other_translations = list(
        Translation.objects.prefetch()
        .filter(component__project=project, language=obj.language)
        .exclude(component__is_glossary=True)
        .order_by("component__name")
        .exclude(pk=obj.pk)[:10]
    )
    if len(other_translations) == 10:
        # Discard too long list as the selection is purely random and thus most
        # likely useless
        other_translations = []
    else:
        # Prefetch stats and tasks for component listing
        other_translations = translation_prefetch_tasks(
            prefetch_stats(other_translations)
        )
        # Include ghost translations for other components, this
        # adds quick way to create translations in other components
        existing = {translation.component.slug for translation in other_translations}
        existing.add(component.slug)

        # Figure out missing components
        all_components = {c.slug for c in project.child_components}
        missing = all_components - existing
        if len(missing) < 5:
            for test_component in project.child_components:
                if test_component.slug in existing:
                    continue
                if test_component.can_add_new_language(user, fast=True):
                    other_translations.append(
                        GhostTranslation(project, obj.language, test_component)
                    )

    return render(
        request,
        "translation.html",
        {
            "allow_index": True,
            "path_object": obj,
            "object": obj,
            "project": project,
            "component": obj.component,
            "supports_plural": component.file_format_cls.supports_plural,
            "form": form,
            "download_form": DownloadForm(obj, auto_id="id_dl_%s"),
            "autoform": optional_form(
                AutoForm,
                user,
                "translation.auto",
                obj,
                obj=component,
                user=user,
            ),
            "search_form": search_form,
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj, obj=obj),
            "bulk_state_form": optional_form(
                BulkEditForm,
                user,
                "translation.auto",
                obj,
                user=user,
                obj=obj,
                project=project,
            ),
            "new_unit_form": get_new_unit_form(obj, user),
            "new_unit_plural_form": get_new_unit_form(obj, user, is_source_plural=True),
            "announcement_form": optional_form(
                AnnouncementForm, user, "announcement.add", component
            ),
            "delete_form": optional_form(
                TranslationDeleteForm, user, "translation.delete", obj, obj=obj
            ),
            "last_changes": last_changes,
            "other_translations": other_translations,
            "exporters": EXPORTERS.list_exporters(obj),
        },
    )


@never_cache
def data_project(request: AuthenticatedHttpRequest, project) -> HttpResponse:
    obj = parse_path(request, [project], (Project,))
    return render(
        request,
        "data.html",
        {
            "object": obj,
            "components": obj.get_child_components_access(request.user),
            "project": obj,
        },
    )


@never_cache
@login_required
@transaction.atomic
@session_ratelimit_post("language", logout_user=False)
def new_language(request: AuthenticatedHttpRequest, path) -> HttpResponse:
    obj = parse_path(request, path, (Component, Project))
    if isinstance(obj, Component):
        return new_component_language(request, obj)
    if isinstance(obj, Project):
        return new_project_language(request, obj)
    msg = f"Not supported new language: {obj}"
    raise TypeError(msg)


def new_component_language(
    request: AuthenticatedHttpRequest, obj: Component
) -> HttpResponse:
    user = request.user

    form_class = get_new_component_language_form(request, obj)

    if request.method == "POST":
        form = form_class(user, obj, request.POST)
        if form.is_valid():
            languages = Language.objects.filter(code__in=form.cleaned_data["lang"])
            result, _ = add_languages_to_component(
                request,
                user,
                languages,
                obj,
                show_messages=True,
            )
            return redirect(result)
        messages.error(request, gettext("Please fix errors in the form."))
    else:
        form = form_class(user, obj)

    return render(
        request,
        "new-language.html",
        {
            "object": obj,
            "path_object": obj,
            "project": obj.project,
            "component": obj,
            "form": form,
            "can_add": obj.can_add_new_language(user),
        },
    )


def new_project_language(
    request: AuthenticatedHttpRequest, obj: Project
) -> HttpResponse:
    user = request.user
    eligible_components = obj.components_user_can_add_new_language(user)
    if not eligible_components.exists():
        messages.error(
            request,
            gettext("Language addition is not supported by any of the components."),
        )
        return redirect(obj)

    form_class = get_new_project_language_form(request, obj)

    if request.method == "POST":
        form = form_class(user, obj, request.POST)
        if form.is_valid():
            languages = Language.objects.filter(code__in=form.cleaned_data["lang"])
            language_map = {lang.code: lang for lang in languages}
            lang_counters = {lang_code: Counter() for lang_code in language_map}

            for component in eligible_components:
                _, component_counts = add_languages_to_component(
                    request,
                    user,
                    languages,
                    component,
                    show_messages=False,
                )

                for lang_code in language_map:
                    for action in ["added", "requested", "errors"]:
                        key = f"{action}_{lang_code}"
                        lang_counters[lang_code][action] += component_counts[key]

            for lang_code, lang in language_map.items():
                counter = lang_counters[lang_code]

                if counter["added"] > 0:
                    messages.success(
                        request,
                        ngettext(
                            "Language %(language)s added to %(count)d component.",
                            "Language %(language)s added to %(count)d components.",
                            counter["added"],
                        )
                        % {
                            "language": lang.name,
                            "count": counter["added"],
                        },
                    )

                if counter["requested"] > 0:
                    messages.success(
                        request,
                        ngettext(
                            "Language %(language)s requested for %(count)d component.",
                            "Language %(language)s requested for %(count)d components.",
                            counter["requested"],
                        )
                        % {
                            "language": lang.name,
                            "count": counter["requested"],
                        },
                    )

                if counter["errors"] > 0:
                    messages.warning(
                        request,
                        ngettext(
                            "Language %(language)s could not be added to %(count)d component. Please check the component's configuration.",
                            "Language %(language)s could not be added to %(count)d components. Please check the components' configuration.",
                            counter["errors"],
                        )
                        % {
                            "language": lang.name,
                            "count": counter["errors"],
                        },
                    )

            return redirect(obj)
        messages.error(request, gettext("Please fix errors in the form."))
    else:
        form = form_class(user, obj)

    return render(
        request,
        "new-project-language.html",
        {
            "object": obj,
            "path_object": obj,
            "project": obj,
            "form": form,
        },
    )


def add_languages_to_component(
    request: AuthenticatedHttpRequest,
    user: User,
    languages: list[Language],
    component: Component,
    show_messages: bool,
) -> tuple[Any, Counter]:
    added = False
    result = component
    kwargs = {
        "user": user,
        "component": component,
        "details": {},
    }
    lang_counts = Counter()
    with component.repository.lock:
        component.commit_pending("add language", None)
        for language in languages:
            lang_code = language.code
            kwargs["details"]["language"] = lang_code

            if component.can_add_new_language(user):
                translation = component.add_new_language(
                    language,
                    request,
                    create_translations=False,
                    show_messages=show_messages,
                )
                if translation:
                    added = True
                    kwargs["translation"] = translation
                    if len(languages) == 1:
                        result = translation
                    component.change_set.create(
                        action=ActionEvents.ADDED_LANGUAGE, **kwargs
                    )
                    lang_counts[f"added_{lang_code}"] += 1
                    continue

            elif component.new_lang == "contact":
                if component.translation_set.filter(language_code=lang_code).exists():
                    continue
                component.change_set.create(
                    action=ActionEvents.REQUESTED_LANGUAGE, **kwargs
                )
                if show_messages:
                    messages.success(
                        request,
                        gettext(
                            "A request for a new translation has been "
                            "sent to the project's maintainers."
                        ),
                    )
                lang_counts[f"requested_{lang_code}"] += 1
                continue

            lang_counts[f"errors_{lang_code}"] += 1

        try:
            # force_scan needed, see add_new_language
            if added and not component.create_translations(
                request=request, force_scan=True
            ):
                if show_messages:
                    messages.success(
                        request,
                        gettext(
                            "All languages have been added, updates of translations are in progress."
                        ),
                    )
                result = "{}?info=1".format(
                    reverse(
                        "show_progress",
                        kwargs={"path": result.get_url_path()},
                    )
                )
        except FileParseError:
            pass

    if user.has_perm("component.edit", component):
        reset_rate_limit("language", request)

    return result, lang_counts


@never_cache
def healthz(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Make simple health check endpoint."""
    return HttpResponse("ok")


@never_cache
def show_component_list(request: AuthenticatedHttpRequest, name) -> HttpResponse:
    obj = get_object_or_404(ComponentList, slug__iexact=name)
    components = prefetch_tasks(
        get_paginator(
            request,
            obj.components.filter_access(request.user).order().prefetch(),
            stats=True,
        )
    )

    return render(
        request,
        "component-list.html",
        {
            "object": obj,
            "components": components,
        },
    )


@never_cache
def guide(request: AuthenticatedHttpRequest, path):
    obj = parse_path(request, path, (Component,))

    return render(
        request,
        "guide.html",
        {
            "object": obj,
            "path_object": obj,
            "project": obj.project,
            "component": obj,
            "guidelines": obj.guidelines,
        },
    )


class ProjectLanguageRedirectView(RedirectView):
    permanent = True
    query_string = True
    pattern_name = "show"

    def get_redirect_url(self, project: str | None, lang: str):
        return super().get_redirect_url(path=[project or "-", "-", lang])
