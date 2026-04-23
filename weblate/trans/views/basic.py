# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections import Counter
from contextlib import suppress
from typing import TYPE_CHECKING, NotRequired, Protocol, TypedDict, Unpack, overload

from django.conf import settings
from django.contrib.auth.decorators import login_not_required, login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext, ngettext
from django.views.decorators.cache import never_cache
from django.views.generic import RedirectView

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
    ComponentLinkAddForm,
    ComponentLinkCategoryForm,
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
    get_new_project_or_category_language_form,
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
    ComponentLink,
    prefetch_tasks,
    translation_prefetch_tasks,
)
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.models.translation import GhostTranslation
from weblate.trans.util import render, sort_unicode, translation_percent
from weblate.utils import messages
from weblate.utils.decorators import engage_login_not_required
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
    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.trans.models.component import ComponentQuerySet


class LanguageChangeKwargs(TypedDict):
    user: User
    component: Component
    details: dict[str, str]
    translation: NotRequired[Translation]


class _ComponentChangeSet(Protocol):
    def create(
        self, *, action: ActionEvents, **kwargs: Unpack[LanguageChangeKwargs]
    ) -> Change: ...


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

    show_review_columns = projects.filter(
        Q(source_review=True) | Q(translation_review=True)
    ).exists()

    return render(
        request,
        "projects.html",
        {
            "allow_index": True,
            "projects": prefetch_project_flags(
                get_paginator(
                    request,
                    projects,
                    stats=True,
                    sort_by=request.GET.get("sort_by"),
                )
            ),
            "title": gettext("Projects"),
            "query_string": query_string,
            "show_review_columns": show_review_columns,
        },
    )


@overload
def add_ghost_translations(
    obj: Category,
    user: User,
    translations: list,
    generator: type[GhostCategoryLanguageStats],
    **kwargs,
) -> None: ...
@overload
def add_ghost_translations(
    obj: Project,
    user: User,
    translations: list,
    generator: type[GhostProjectLanguageStats | GhostTranslation],
    **kwargs,
) -> None: ...
def add_ghost_translations(
    obj,
    user,
    translations,
    generator,
    **kwargs,
):
    """Add ghost translations for user languages to the list."""
    project = obj if isinstance(obj, Project) else obj.project
    existing_language_ids = {translation.language.id for translation in translations}
    user_languages = list(user.profile.all_languages)
    missing_languages = [
        language
        for language in user_languages
        if language.id not in existing_language_ids
    ]
    if not missing_languages:
        return

    allowed_language_ids = Language.objects.get_allowed_add_language_ids(
        project, (language.id for language in missing_languages)
    )

    for language in missing_languages:
        # Skip languages not allowed for adding
        if language.id not in allowed_language_ids:
            continue

        # Generate ghost object
        translations.append(generator(obj, language, **kwargs))


@engage_login_not_required
def show_engage(request: AuthenticatedHttpRequest, path):
    # Legacy URL
    if len(path) == 2:
        return redirect("engage", permanent=True, path=[path[0], "-", path[1]])
    # Get project object, skipping ACL
    obj = parse_path(None, path, (ProjectLanguage, Project))

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


def show_project_language(
    request: AuthenticatedHttpRequest, obj: ProjectLanguage
) -> HttpResponse:
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
        get_paginator(
            request,
            obj.translation_set,
            stats=True,
            sort_by=request.GET.get("sort_by"),
        )
    )
    extra_translations = []

    # Add ghost translations
    if user.is_authenticated and translations.paginator.num_pages == 1:
        existing = {translation.component.id for translation in obj.translation_set}
        missing = project_object.get_child_components_filter(
            lambda qs: (
                qs.exclude(id__in=existing)
                .prefetch()
                .prefetch_related("source_language")
            )
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
            "autoform": optional_form(
                AutoForm,
                user,
                "translation.auto",
                obj,
                obj=obj.project,
                user=user,
            ),
            "bulk_state_form": optional_form(
                BulkEditForm,
                user,
                "unit.bulk_edit",
                obj,
                user=user,
                obj=obj,
                project=obj.project,
            ),
        },
    )


def show_category_language(
    request: AuthenticatedHttpRequest, obj: CategoryLanguage
) -> HttpResponse:
    language_object = obj.language
    category_object = obj.category
    user = request.user

    last_changes = (
        Change.objects.last_changes(user, language=language_object)
        .for_category(category_object)
        .recent()
    )

    translations = get_paginator(
        request,
        obj.translation_set,
        stats=True,
        sort_by=request.GET.get("sort_by"),
    )
    extra_translations = []

    # Add ghost translations
    if user.is_authenticated and translations.paginator.num_pages == 1:
        existing = {translation.component.id for translation in obj.translation_set}
        missing = category_object.component_set.exclude(id__in=existing)
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
                "unit.bulk_edit",
                obj,
                user=user,
                obj=obj,
                project=obj.category.project,
            ),
        },
    )


def show_project(request: AuthenticatedHttpRequest, obj: Project) -> HttpResponse:
    def filter_no_category(qs: ComponentQuerySet) -> ComponentQuerySet:
        if settings.HIDE_SHARED_GLOSSARY_COMPONENTS:
            qs = qs.exclude(Q(is_glossary=True) & ~Q(project=obj))
        # Show at project root:
        # - Owned components without a category (project=obj ensures we
        #   don't match shared components whose source category is None)
        # - Shared components whose link to this project has no category
        #   (scoped to this project to avoid matching links to other projects
        #   if a component is shared to multiple projects)
        return qs.filter(
            Q(project=obj, category=None)
            | Q(
                componentlink__project=obj,
                componentlink__category__isnull=True,
            )
        )

    user = request.user

    all_changes = obj.change_set.filter_components(request.user).prefetch()
    last_changes = all_changes.recent()
    last_announcements = all_changes.filter_announcements().recent()

    all_components = obj.get_child_components_access(user, filter_no_category)
    all_components = get_paginator(
        request,
        all_components,
        stats=True,
        sort_by=request.GET.get("sort_by"),
    )
    for component in all_components:
        component.is_shared = None if component.project == obj else component.project

    language_stats = obj.stats.get_language_stats()
    can_add_language_components = obj.components_user_can_add_new_language(user)
    user_can_add_translation = can_add_language_components.exists()
    if user_can_add_translation:
        add_ghost_translations(
            obj,
            user,
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
                request=request,
                initial=SearchForm.get_initial(request),
                obj=obj,
            ),
            "announcement_form": optional_form(
                AnnouncementForm, user, "announcement.add", obj
            ),
            "add_form": AddCategoryForm(request, obj) if obj.can_add_category else None,
            "delete_form": optional_form(
                ProjectDeleteForm, user, "project.edit", obj, obj=obj
            ),
            "managed_teams": obj.defined_groups.filter(admins=request.user),
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
                "unit.bulk_edit",
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


def show_category(request: AuthenticatedHttpRequest, obj: Category) -> HttpResponse:
    user = request.user

    all_changes = (
        Change.objects.for_category(obj).filter_components(request.user).prefetch()
    )

    last_changes = all_changes.recent()
    last_announcements = all_changes.filter_announcements().recent()

    all_components = obj.get_child_components_access(user)
    all_components = get_paginator(
        request,
        all_components,
        stats=True,
        sort_by=request.GET.get("sort_by"),
    )
    for component in all_components:
        component.is_shared = (
            None if component.project == obj.project else component.project
        )

    language_stats = obj.stats.get_language_stats()
    can_add_language_components = obj.components_user_can_add_new_language(user)
    user_can_add_translation = can_add_language_components.exists()
    if user_can_add_translation:
        add_ghost_translations(
            obj,
            user,
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
                request=request,
                initial=SearchForm.get_initial(request),
                obj=obj,
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
            "autoform": optional_form(
                AutoForm,
                user,
                "translation.auto",
                obj,
                obj=obj.project,
                user=user,
            ),
            "bulk_state_form": optional_form(
                BulkEditForm,
                user,
                "unit.bulk_edit",
                obj,
                user=user,
                obj=obj,
                project=obj.project,
            ),
            "components": components,
            "categories": prefetch_stats(obj.category_set.all()),
            "user_can_add_translation": user_can_add_translation,
        },
    )


def show_component(request: AuthenticatedHttpRequest, obj: Component) -> HttpResponse:
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
                "unit.bulk_edit",
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
            "autoform": optional_form(
                AutoForm,
                user,
                "translation.auto",
                obj,
                obj=obj,
                user=user,
            ),
            "search_form": SearchForm(
                request=request,
                initial=SearchForm.get_initial(request),
                obj=obj,
            ),
            "alerts": obj.all_active_alerts
            if "alerts" not in request.GET
            else obj.alert_set.all(),
            "user_can_add_translation": user_can_add_translation,
            "component_links_formset": _get_component_links_formset(obj, user),
            "component_link_add_form": _get_component_link_add_form(request, obj, user),
        },
    )


def _get_component_link_add_form(request, obj, user):
    """Build the form for adding a new component link."""
    if not user.has_perm("component.edit", obj):
        return None
    return ComponentLinkAddForm(request=request, component=obj, prefix="link_add")


def _get_component_links_formset(obj, user):
    """Build a list of ComponentLinkCategoryForm instances for the component."""
    if not user.has_perm("component.edit", obj):
        return None

    links = ComponentLink.objects.filter(component=obj).select_related(
        "project", "category"
    )
    if not links:
        return None
    forms = []
    for link in links:
        form = ComponentLinkCategoryForm(
            initial={"link_id": link.pk, "category": link.category},
            project=link.project,
        )
        form.project_name = link.project.name
        forms.append(form)
    return forms


def show_translation(
    request: AuthenticatedHttpRequest, obj: Translation
) -> HttpResponse:
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
        .filter(
            Q(component__project=project) | Q(component__links=project),
            language=obj.language,
        )
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
        existing = {translation.component.id for translation in other_translations}
        existing.add(component.id)

        # Figure out missing components
        available_components = [
            c for c in project.child_components if not c.is_glossary
        ]

        all_components = {c.id for c in available_components}
        missing = all_components - existing
        if 0 < len(missing) < 5:
            for test_component in available_components:
                if test_component.id in existing:
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
                "unit.bulk_edit",
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
def data_project(request: AuthenticatedHttpRequest, project: str) -> HttpResponse:
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
    obj = parse_path(request, path, (Component, Project, Category))
    if isinstance(obj, Component):
        return new_component_language(request, obj)
    if isinstance(obj, Project):
        return new_project_or_category_language(request, obj)
    if isinstance(obj, Category):
        return new_project_or_category_language(request, obj)
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


def new_project_or_category_language(
    request: AuthenticatedHttpRequest, obj: Category | Project
) -> HttpResponse:
    user = request.user
    eligible_components = obj.components_user_can_add_new_language(user)
    if not eligible_components.exists():
        messages.error(
            request,
            gettext("Language addition is not supported by any of the components."),
        )
        return redirect(obj)

    form_class = get_new_project_or_category_language_form(request, obj)

    if request.method == "POST":
        form = form_class(user, obj, request.POST)
        if form.is_valid():
            languages = Language.objects.filter(code__in=form.cleaned_data["lang"])
            language_map = {lang.code: lang for lang in languages}
            lang_counters: dict[str, Counter[str]] = {
                lang_code: Counter() for lang_code in language_map
            }

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
        "new-project-or-category-language.html",
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
) -> tuple[Component | Translation | str, Counter[str]]:
    added_codes: set[str] = set()
    result: Component | Translation | str = component
    change_set: _ComponentChangeSet = component.change_set
    kwargs: LanguageChangeKwargs = {
        "user": user,
        "component": component,
        "details": {},
    }
    lang_counts: Counter[str] = Counter()
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
                    added_codes.add(translation.language_code)
                    kwargs["translation"] = translation
                    if len(languages) == 1:
                        result = translation
                    change_set.create(action=ActionEvents.ADDED_LANGUAGE, **kwargs)
                    lang_counts[f"added_{lang_code}"] += 1
                    continue

            elif component.new_lang == "contact":
                if component.translation_set.filter(language_code=lang_code).exists():
                    continue
                change_set.create(action=ActionEvents.REQUESTED_LANGUAGE, **kwargs)
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

        with suppress(FileParseError):
            # force_scan needed, see add_new_language
            if added_codes and not component.create_translations(
                request=request,
                force_scan=True,
                langs=sorted(added_codes),
            ):
                if show_messages:
                    messages.success(
                        request,
                        gettext(
                            "All languages have been added, updates of translations are in progress."
                        ),
                    )
                result = f"{reverse('show_progress', kwargs={'path': result.get_url_path()})}?info=1"

    if user.has_perm("component.edit", component):
        reset_rate_limit("language", request)

    return result, lang_counts


@never_cache
@login_not_required
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
            sort_by=request.GET.get("sort_by"),
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

    # pylint: disable=arguments-differ
    def get_redirect_url(self, project: str | None, lang: str):
        return super().get_redirect_url(path=[project or "-", "-", lang])
