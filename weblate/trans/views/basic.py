#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.html import escape
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from weblate.formats.models import EXPORTERS
from weblate.lang.models import Language
from weblate.trans.forms import (
    AnnouncementForm,
    AutoForm,
    BulkEditForm,
    ComponentDeleteForm,
    ComponentMoveForm,
    ComponentRenameForm,
    DownloadForm,
    NewUnitForm,
    ProjectDeleteForm,
    ProjectRenameForm,
    ReplaceForm,
    ReportsForm,
    SearchForm,
    TranslationDeleteForm,
    get_new_language_form,
    get_upload_form,
)
from weblate.trans.models import Change, ComponentList, Translation, Unit
from weblate.trans.models.component import prefetch_tasks
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.models.translation import GhostTranslation
from weblate.trans.util import render, sort_unicode
from weblate.utils import messages
from weblate.utils.stats import GhostProjectLanguageStats, prefetch_stats
from weblate.utils.views import (
    get_component,
    get_paginator,
    get_project,
    get_translation,
    try_set_language,
)


def optional_form(form, perm_user, perm, perm_obj, **kwargs):
    if not perm_user.has_perm(perm, perm_obj):
        return None
    return form(**kwargs)


@never_cache
def list_projects(request):
    """List all projects."""
    return render(
        request,
        "projects.html",
        {
            "allow_index": True,
            "projects": prefetch_project_flags(
                prefetch_stats(request.user.allowed_projects)
            ),
            "title": _("Projects"),
        },
    )


def add_ghost_translations(component, user, translations, generator):
    """Adds ghost translations for user languages to the list."""
    if component.can_add_new_language(user):
        existing = {translation.language.code for translation in translations}
        for language in user.profile.languages.all():
            if language.code in existing:
                continue
            translations.append(generator(component, language))


def show_engage(request, project, lang=None):
    # Get project object, skipping ACL
    obj = get_project(request, project, skip_acl=True)

    # Handle language parameter
    if lang is not None:
        language = get_object_or_404(Language, code=lang)
    else:
        language = None
    full_stats = obj.stats
    if language:
        try_set_language(lang)
        stats_obj = full_stats.get_single_language_stats(language)
    else:
        stats_obj = full_stats

    return render(
        request,
        "engage.html",
        {
            "allow_index": True,
            "object": obj,
            "project": obj,
            "full_stats": full_stats,
            "languages": stats_obj.languages,
            "total": obj.stats.source_strings,
            "percent": stats_obj.translated_percent,
            "language": language,
            "project_link": mark_safe(
                '<a href="{}">{}</a>'.format(
                    escape(obj.get_absolute_url()), escape(obj.name)
                )
            ),
            "title": _("Get involved in {0}!").format(obj),
        },
    )


@never_cache
def show_project(request, project):
    obj = get_project(request, project)
    obj.stats.ensure_basic()
    user = request.user

    last_changes = Change.objects.prefetch().order().filter(project=obj)[:10]
    last_announcements = (
        Change.objects.prefetch()
        .order()
        .filter(project=obj, action=Change.ACTION_ANNOUNCEMENT)[:10]
    )

    language_stats = obj.stats.get_language_stats()
    # Show ghost translations for user languages
    component = None
    for component in obj.component_set.filter_access(user).all():
        if component.can_add_new_language(user):
            break
    if component:
        add_ghost_translations(
            component, user, language_stats, GhostProjectLanguageStats
        )

    language_stats = sort_unicode(
        language_stats,
        lambda x: "{}-{}".format(
            user.profile.get_language_order(x.language), x.language
        ),
    )

    # Paginate components of project.
    all_components = obj.component_set.filter_access(user).prefetch().order()
    components = prefetch_tasks(prefetch_stats(get_paginator(request, all_components)))

    return render(
        request,
        "project.html",
        {
            "allow_index": True,
            "object": obj,
            "project": obj,
            "last_changes": last_changes,
            "last_announcements": last_announcements,
            "reports_form": ReportsForm(),
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
                auto_id="id_bulk_%s",
            ),
            "components": components,
            "licenses": obj.component_set.exclude(license="").order_by("license"),
        },
    )


@never_cache
def show_component(request, project, component):
    obj = get_component(request, project, component)
    obj.stats.ensure_basic()
    user = request.user

    last_changes = Change.objects.prefetch().order().filter(component=obj)[:10]

    translations = prefetch_stats(list(obj.translation_set.prefetch()))

    # Show ghost translations for user languages
    add_ghost_translations(obj, user, translations, GhostTranslation)

    translations = sort_unicode(
        translations,
        lambda x: "{}-{}".format(
            user.profile.get_language_order(x.language), x.language
        ),
    )

    return render(
        request,
        "component.html",
        {
            "allow_index": True,
            "object": obj,
            "project": obj.project,
            "translations": translations,
            "reports_form": ReportsForm(),
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
                auto_id="id_bulk_%s",
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
            "alerts": obj.all_alerts,
        },
    )


@never_cache
def show_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    obj.stats.ensure_all()
    last_changes = Change.objects.prefetch().order().filter(translation=obj)[:10]
    user = request.user

    # Get form
    form = get_upload_form(user, obj)

    search_form = SearchForm(request.user)

    # Translations to same language from other components in this project
    other_translations = prefetch_stats(
        list(
            Translation.objects.prefetch()
            .filter(component__project=obj.component.project, language=obj.language)
            .exclude(pk=obj.pk)
        )
    )

    # Include ghost translations for other components, this
    # adds quick way to create translations in other components
    existing = {translation.component.slug for translation in other_translations}
    existing.add(obj.component.slug)
    for test_component in obj.component.project.component_set.filter_access(
        user
    ).exclude(slug__in=existing):
        if test_component.can_add_new_language(user):
            other_translations.append(GhostTranslation(test_component, obj.language))

    # Limit the number of other components displayed to 10, preferring untranslated ones
    other_translations = sorted(
        other_translations,
        key=lambda t : t.stats.translated_percent
    )[:10]

    return render(
        request,
        "translation.html",
        {
            "allow_index": True,
            "object": obj,
            "project": obj.component.project,
            "form": form,
            "download_form": DownloadForm(auto_id="id_dl_%s"),
            "autoform": optional_form(
                AutoForm, user, "translation.auto", obj, obj=obj.component
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
                project=obj.component.project,
                auto_id="id_bulk_%s",
            ),
            "new_unit_form": NewUnitForm(
                user, initial={"value": Unit(translation=obj, id_hash=-1)}
            ),
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
    obj = get_project(request, project)
    return render(
        request,
        "data.html",
        {
            "object": obj,
            "components": obj.component_set.filter_access(request.user).order(),
            "project": obj,
        },
    )


@never_cache
@login_required
def new_language(request, project, component):
    obj = get_component(request, project, component)

    form_class = get_new_language_form(request, obj)
    can_add = obj.can_add_new_language(request.user)

    if request.method == "POST":
        form = form_class(obj, request.POST)

        if form.is_valid():
            langs = form.cleaned_data["lang"]
            kwargs = {
                "user": request.user,
                "author": request.user,
                "component": obj,
                "details": {},
            }
            for language in Language.objects.filter(code__in=langs):
                kwargs["details"]["language"] = language.code
                if can_add:
                    translation = obj.add_new_language(language, request)
                    if translation:
                        kwargs["translation"] = translation
                        if len(langs) == 1:
                            obj = translation
                        Change.objects.create(
                            action=Change.ACTION_ADDED_LANGUAGE, **kwargs
                        )
                elif obj.new_lang == "contact":
                    Change.objects.create(
                        action=Change.ACTION_REQUESTED_LANGUAGE, **kwargs
                    )
                    messages.success(
                        request,
                        _(
                            "A request for a new translation has been "
                            "sent to the project's maintainers."
                        ),
                    )
            return redirect(obj)
        messages.error(request, _("Please fix errors in the form."))
    else:
        form = form_class(obj)

    return render(
        request,
        "new-language.html",
        {"object": obj, "project": obj.project, "form": form, "can_add": can_add},
    )


@never_cache
def healthz(request):
    """Simple health check endpoint."""
    return HttpResponse("ok")


@never_cache
def show_component_list(request, name):
    obj = get_object_or_404(ComponentList, slug__iexact=name)

    return render(
        request,
        "component-list.html",
        {"object": obj, "components": obj.components.filter_access(request.user)},
    )
