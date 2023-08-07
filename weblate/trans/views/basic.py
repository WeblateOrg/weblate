# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache

from weblate.formats.models import EXPORTERS
from weblate.lang.models import Language
from weblate.trans.exceptions import FileParseError
from weblate.trans.forms import (
    AnnouncementForm,
    AutoForm,
    BulkEditForm,
    ComponentDeleteForm,
    ComponentMoveForm,
    ComponentRenameForm,
    DownloadForm,
    ProjectDeleteForm,
    ProjectFilterForm,
    ProjectRenameForm,
    ReplaceForm,
    ReportsForm,
    SearchForm,
    TranslationDeleteForm,
    get_new_language_form,
    get_new_unit_form,
    get_upload_form,
)
from weblate.trans.models import Change, Component, ComponentList, Project, Translation
from weblate.trans.models.component import prefetch_tasks
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.models.translation import GhostTranslation
from weblate.trans.util import render, sort_unicode
from weblate.utils import messages
from weblate.utils.ratelimit import reset_rate_limit, session_ratelimit_post
from weblate.utils.stats import (
    GhostProjectLanguageStats,
    ProjectLanguage,
    prefetch_stats,
)
from weblate.utils.views import (
    get_paginator,
    optional_form,
    parse_path,
    show_form_errors,
    try_set_language,
)


@never_cache
def list_projects(request):
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
                get_paginator(request, prefetch_stats(projects))
            ),
            "title": gettext("Projects"),
            "query_string": query_string,
        },
    )


def add_ghost_translations(component, user, translations, generator, **kwargs):
    """Adds ghost translations for user languages to the list."""
    if component.can_add_new_language(user, fast=True):
        existing = {translation.language.code for translation in translations}
        for language in user.profile.all_languages:
            if language.code in existing:
                continue
            translations.append(generator(component, language, **kwargs))


def show_engage(request, path):
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
    full_stats = obj.stats
    if language:
        stats_obj = full_stats.get_single_language_stats(language)
    else:
        stats_obj = full_stats

    return render(
        request,
        "engage.html",
        {
            "allow_index": True,
            "object": obj,
            "project": project,
            "full_stats": obj.stats,
            "languages": stats_obj.languages,
            "total": obj.stats.source_strings,
            "percent": stats_obj.translated_percent,
            "language": language,
            "translate_object": translate_object,
            "project_link": format_html(
                '<a href="{}">{}</a>', project.get_absolute_url(), project.name
            ),
            "title": gettext("Get involved in {0}!").format(project),
        },
    )


@never_cache
def show(request, path):
    obj = parse_path(request, path, (Translation, Component, Project))
    if isinstance(obj, Project):
        return show_project(request, obj)
    if isinstance(obj, Component):
        return show_component(request, obj)
    return show_translation(request, obj)


def show_project(request, obj):
    obj.stats.ensure_basic()
    user = request.user

    last_changes = obj.change_set.prefetch().order()[:10].preload()
    last_announcements = (
        obj.change_set.prefetch()
        .order()
        .filter(action=Change.ACTION_ANNOUNCEMENT)[:10]
        .preload()
    )

    all_components = prefetch_stats(obj.get_child_components_access(user).prefetch())
    all_components = get_paginator(request, all_components)
    for component in all_components:
        component.is_shared = None if component.project == obj else component.project

    language_stats = obj.stats.get_language_stats()
    # Show ghost translations for user languages
    component = None
    for component in all_components:
        if component.can_add_new_language(user, fast=True):
            break
    if component:
        add_ghost_translations(
            component,
            user,
            language_stats,
            GhostProjectLanguageStats,
            is_shared=component.is_shared,
        )

    language_stats = sort_unicode(
        language_stats,
        lambda x: f"{user.profile.get_translation_order(x)}-{x.language}",
    )

    components = prefetch_tasks(all_components)

    return render(
        request,
        "project.html",
        {
            "allow_index": True,
            "object": obj,
            "project": obj,
            "last_changes": last_changes,
            "last_announcements": last_announcements,
            "reports_form": ReportsForm({"project": obj}),
            "last_changes_url": urlencode({"project": obj.slug}),
            "language_stats": [stat.obj or stat for stat in language_stats],
            "search_form": SearchForm(request.user),
            "announcement_form": optional_form(
                AnnouncementForm, user, "project.edit", obj
            ),
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
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj),
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
            "licenses": sorted(
                (component for component in all_components if component.license),
                key=lambda component: component.license,
            ),
        },
    )


def show_component(request, obj):
    obj.stats.ensure_basic()
    user = request.user

    last_changes = obj.change_set.prefetch().order()[:10].preload("component")

    translations = prefetch_stats(list(obj.translation_set.prefetch()))

    # Show ghost translations for user languages
    add_ghost_translations(obj, user, translations, GhostTranslation)

    translations = sort_unicode(
        translations,
        lambda x: f"{user.profile.get_translation_order(x)}-{x.language}",
    )

    return render(
        request,
        "component.html",
        {
            "allow_index": True,
            "object": obj,
            "project": obj.project,
            "component": obj,
            "translations": translations,
            "reports_form": ReportsForm({"component": obj}),
            "last_changes": last_changes,
            "last_changes_url": urlencode(
                {"component": obj.slug, "project": obj.project.slug}
            ),
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj),
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
                AnnouncementForm, user, "component.edit", obj
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
            "move_form": optional_form(
                ComponentMoveForm,
                user,
                "component.edit",
                obj,
                request=request,
                instance=obj,
            ),
            "search_form": SearchForm(request.user),
            "alerts": obj.all_active_alerts
            if "alerts" not in request.GET
            else obj.alert_set.all(),
        },
    )


def show_translation(request, obj):
    component = obj.component
    project = component.project
    obj.stats.ensure_all()
    last_changes = obj.change_set.prefetch().order()[:10].preload("translation")
    user = request.user

    # Get form
    form = get_upload_form(user, obj)

    search_form = SearchForm(request.user, language=obj.language)

    # Translations to same language from other components in this project
    other_translations = prefetch_stats(
        list(
            Translation.objects.prefetch()
            .filter(component__project=project, language=obj.language)
            .exclude(pk=obj.pk)
        )
    )

    # Include ghost translations for other components, this
    # adds quick way to create translations in other components
    existing = {translation.component.slug for translation in other_translations}
    existing.add(component.slug)
    for test_component in project.child_components:
        if test_component.slug in existing:
            continue
        if test_component.can_add_new_language(user, fast=True):
            other_translations.append(GhostTranslation(test_component, obj.language))

    # Limit the number of other components displayed to 10, preferring untranslated ones
    other_translations = sorted(
        other_translations, key=lambda t: t.stats.translated_percent
    )[:10]

    return render(
        request,
        "translation.html",
        {
            "allow_index": True,
            "object": obj,
            "project": project,
            "component": obj.component,
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
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj),
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
            "announcement_form": optional_form(
                AnnouncementForm, user, "component.edit", obj
            ),
            "delete_form": optional_form(
                TranslationDeleteForm, user, "translation.delete", obj, obj=obj
            ),
            "last_changes": last_changes,
            "last_changes_url": urlencode(obj.get_reverse_url_kwargs()),
            "other_translations": other_translations,
            "exporters": EXPORTERS.list_exporters(obj),
        },
    )


@never_cache
def data_project(request, project):
    obj = parse_path(request, [project], (Project,))
    return render(
        request,
        "data.html",
        {
            "object": obj,
            "components": obj.get_child_components_access(request.user)
            .prefetch()
            .order(),
            "project": obj,
        },
    )


@never_cache
@login_required
@session_ratelimit_post("language", logout_user=False)
@transaction.atomic
def new_language(request, path):
    obj = parse_path(request, path, (Component,))
    user = request.user

    form_class = get_new_language_form(request, obj)
    can_add = obj.can_add_new_language(user)
    added = False

    if request.method == "POST":
        form = form_class(obj, request.POST)

        if form.is_valid():
            result = obj
            langs = form.cleaned_data["lang"]
            kwargs = {
                "user": user,
                "author": user,
                "component": obj,
                "details": {},
            }
            with obj.repository.lock:
                for language in Language.objects.filter(code__in=langs):
                    kwargs["details"]["language"] = language.code
                    if can_add:
                        translation = obj.add_new_language(
                            language, request, create_translations=False
                        )
                        if translation:
                            added = True
                            kwargs["translation"] = translation
                            if len(langs) == 1:
                                result = translation
                            Change.objects.create(
                                action=Change.ACTION_ADDED_LANGUAGE, **kwargs
                            )
                    elif obj.new_lang == "contact":
                        Change.objects.create(
                            action=Change.ACTION_REQUESTED_LANGUAGE, **kwargs
                        )
                        messages.success(
                            request,
                            gettext(
                                "A request for a new translation has been "
                                "sent to the project's maintainers."
                            ),
                        )
                try:
                    if added and not obj.create_translations(request=request):
                        messages.warning(
                            request,
                            gettext(
                                "The translation will be updated in the background."
                            ),
                        )
                except FileParseError:
                    pass
            if user.has_perm("component.edit", obj):
                reset_rate_limit("language", request)
            return redirect(result)
        messages.error(request, gettext("Please fix errors in the form."))
    else:
        form = form_class(obj)

    return render(
        request,
        "new-language.html",
        {
            "object": obj,
            "project": obj.project,
            "component": obj,
            "form": form,
            "can_add": can_add,
        },
    )


@never_cache
def healthz(request):
    """Simple health check endpoint."""
    return HttpResponse("ok")


@never_cache
def show_component_list(request, name):
    obj = get_object_or_404(ComponentList, slug__iexact=name)
    components = obj.components.filter_access(request.user)

    return render(
        request,
        "component-list.html",
        {
            "object": obj,
            "components": components,
            "licenses": sorted(
                (component for component in components if component.license),
                key=lambda component: component.license,
            ),
        },
    )


@never_cache
def guide(request, path):
    obj = parse_path(request, path, (Component,))

    return render(
        request,
        "guide.html",
        {
            "object": obj,
            "project": obj.project,
            "component": obj,
            "guidelines": obj.guidelines,
        },
    )
