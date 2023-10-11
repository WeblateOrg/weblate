# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.generic import RedirectView

from weblate.formats.models import EXPORTERS
from weblate.lang.models import Language
from weblate.trans.exceptions import FileParseError
from weblate.trans.forms import (
    AddCategoryForm,
    AnnouncementForm,
    AutoForm,
    BulkEditForm,
    CategoryDeleteForm,
    CategoryLanguageDeleteForm,
    CategoryMoveForm,
    CategoryRenameForm,
    ComponentDeleteForm,
    ComponentMoveForm,
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
    get_new_language_form,
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
from weblate.trans.models.component import prefetch_tasks, translation_prefetch_tasks
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.models.translation import GhostTranslation
from weblate.trans.util import render, sort_unicode, translation_percent
from weblate.utils import messages
from weblate.utils.ratelimit import reset_rate_limit, session_ratelimit_post
from weblate.utils.stats import (
    CategoryLanguage,
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
            code = component.format_new_language_code(language)
            if re.match(component.language_regex, code) is None:
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
        stats_obj = obj.stats

        all_count = strings_count = stats_obj.all
        translated_count = stats_obj.translated

        # Remove glossary from counts
        glossaries = prefetch_stats(
            Translation.objects.filter(
                language=language, component__in=project.glossaries
            ).prefetch()
        )
        for glossary in prefetch_stats(glossaries):
            all_count -= glossary.stats.all
            translated_count -= glossary.stats.translated
            strings_count -= glossary.stats.all

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
        stats_obj = obj.stats

        all_count = stats_obj.all
        strings_count = stats_obj.source_strings
        translated_count = stats_obj.translated

        # Remove glossary from counts
        for glossary in prefetch_stats(project.glossaries):
            all_count -= glossary.stats.all
            translated_count -= glossary.stats.translated
            strings_count -= glossary.stats.source_strings

    return render(
        request,
        "engage.html",
        {
            "allow_index": True,
            "object": obj,
            "path_object": obj,
            "project": project,
            "strings_count": strings_count,
            "languages_count": project.stats.languages,
            "percent": translation_percent(translated_count, all_count),
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
    raise TypeError(f"Not supported show: {obj}")


def show_project_language(request, obj):
    language_object = obj.language
    project_object = obj.project
    user = request.user

    last_changes = Change.objects.last_changes(
        user, project=project_object, language=language_object
    )[:10].preload()

    translations = list(obj.translation_set)

    # Add ghost translations
    if user.is_authenticated:
        existing = {translation.component.slug for translation in translations}
        missing = project_object.get_child_components_filter(
            lambda qs: qs.exclude(slug__in=existing)
        )
        translations.extend(
            GhostTranslation(component, language_object)
            for component in missing
            if component.can_add_new_language(user, fast=True)
        )

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
            "translations": translations,
            "title": f"{project_object} - {language_object}",
            "search_form": SearchForm(user, language=language_object),
            "licenses": project_object.component_set.exclude(license="").order_by(
                "license"
            ),
            "language_stats": project_object.stats.get_single_language_stats(
                language_object
            ),
            "delete_form": optional_form(
                ProjectLanguageDeleteForm, user, "translation.delete", obj, obj=obj
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
        },
    )


def show_category_language(request, obj):
    language_object = obj.language
    category_object = obj.category
    user = request.user

    last_changes = (
        Change.objects.last_changes(user, language=language_object)
        .for_category(category_object)[:10]
        .preload()
    )

    translations = list(obj.translation_set)

    # Add ghost translations
    if user.is_authenticated:
        existing = {translation.component.slug for translation in translations}
        missing = category_object.component_set.exclude(slug__in=existing)
        translations.extend(
            GhostTranslation(component, language_object)
            for component in missing
            if component.can_add_new_language(user, fast=True)
        )

    return render(
        request,
        "category-project.html",
        {
            "allow_index": True,
            "language": language_object,
            "category": category_object,
            "object": obj,
            "path_object": obj,
            "last_changes": last_changes,
            "translations": translations,
            "title": f"{category_object} - {language_object}",
            "search_form": SearchForm(user, language=language_object),
            "licenses": obj.category.get_child_components_access(user)
            .exclude(license="")
            .order_by("license"),
            "language_stats": category_object.stats.get_single_language_stats(
                language_object
            ),
            "delete_form": optional_form(
                CategoryLanguageDeleteForm, user, "translation.delete", obj, obj=obj
            ),
            "replace_form": optional_form(ReplaceForm, user, "unit.edit", obj),
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


def show_project(request, obj):
    obj.stats.ensure_basic()
    user = request.user

    all_changes = obj.change_set.prefetch().order()
    last_changes = all_changes[:10].preload()
    last_announcements = all_changes.filter_announcements()[:10].preload()

    all_components = obj.get_child_components_access(
        user, lambda qs: qs.filter(category=None)
    )
    all_components = get_paginator(request, prefetch_stats(all_components))
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

    language_stats = sort_unicode(language_stats, user.profile.get_translation_order)

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
            "search_form": SearchForm(request.user),
            "announcement_form": optional_form(
                AnnouncementForm, user, "project.edit", obj
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
            "categories": obj.category_set.filter(category=None),
            "licenses": sorted(
                (component for component in all_components if component.license),
                key=lambda component: component.license,
            ),
        },
    )


def show_category(request, obj):
    obj.stats.ensure_basic()
    user = request.user

    all_changes = Change.objects.for_category(obj).prefetch().order()
    last_changes = all_changes[:10].preload()
    last_announcements = all_changes.filter_announcements()[:10].preload()

    all_components = obj.get_child_components_access(user)
    all_components = get_paginator(request, prefetch_stats(all_components))

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
        )

    language_stats = sort_unicode(
        language_stats,
        lambda x: f"{user.profile.get_translation_order(x)}-{x.language}",
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
            "language_stats": [stat.obj or stat for stat in language_stats],
            "search_form": SearchForm(user),
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
            "move_form": optional_form(
                CategoryMoveForm,
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
                project=obj.project,
            ),
            "components": components,
            "categories": obj.category_set.all(),
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

    translations = sort_unicode(translations, user.profile.get_translation_order)

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
    # Show up to 10 of them, needs to be list to append ghost ones later
    other_translations = translation_prefetch_tasks(
        prefetch_stats(
            list(
                Translation.objects.prefetch()
                .filter(component__project=project, language=obj.language)
                .exclude(pk=obj.pk)[:10]
            )
        )
    )

    # Include ghost translations for other components, this
    # adds quick way to create translations in other components
    if len(other_translations) < 10:
        existing = {translation.component.slug for translation in other_translations}
        existing.add(component.slug)
        for test_component in project.child_components:
            if test_component.slug in existing:
                continue
            if test_component.can_add_new_language(user, fast=True):
                other_translations.append(
                    GhostTranslation(test_component, obj.language)
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
            "components": obj.get_child_components_access(request.user),
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
            "path_object": obj,
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
    components = prefetch_tasks(
        prefetch_stats(obj.components.filter_access(request.user).prefetch())
    )

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
