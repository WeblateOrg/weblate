# -*- coding: utf-8 -*-
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
from django.utils.encoding import force_str
from django.utils.html import escape
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from weblate.auth.models import Group
from weblate.formats.exporters import list_exporters
from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.trans.forms import (
    AutoForm,
    BulkEditForm,
    ComponentMoveForm,
    ComponentRenameForm,
    DeleteForm,
    DownloadForm,
    NewNamespacedLanguageForm,
    NewUnitForm,
    ProjectRenameForm,
    ReplaceForm,
    ReportsForm,
    SearchForm,
    WhiteboardForm,
    get_new_language_form,
    get_upload_form,
)
from weblate.trans.models import Change, ComponentList, Translation, Unit
from weblate.trans.util import render, sort_objects, sort_unicode
from weblate.utils import messages
from weblate.utils.stats import prefetch_stats
from weblate.utils.views import (
    get_component,
    get_paginator,
    get_project,
    get_translation,
    try_set_language,
)
from weblate.vendasta.constants import ACCESS_NAMESPACE, NAMESPACE_SEPARATOR


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
            "projects": prefetch_stats(request.user.allowed_projects),
            "title": _("Projects"),
        },
    )


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
    user = request.user

    last_changes = Change.objects.prefetch().order().filter(project=obj)[:10]

    language_stats = sort_unicode(
        obj.stats.get_language_stats(), lambda x: force_str(x.language)
    )

    # Paginate components of project.
    all_components = obj.component_set.prefetch().order()
    components = prefetch_stats(get_paginator(request, all_components))

    return render(
        request,
        "project.html",
        {
            "allow_index": True,
            "object": obj,
            "project": obj,
            "last_changes": last_changes,
            "reports_form": ReportsForm(),
            "last_changes_url": urlencode({"project": obj.slug}),
            "language_stats": language_stats,
            "search_form": SearchForm(request.user),
            "whiteboard_form": optional_form(WhiteboardForm, user, "project.edit", obj),
            "delete_form": optional_form(
                DeleteForm, user, "project.edit", obj, obj=obj
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
    user = request.user
    user_can_access_namespace = bool(
        user.groups.filter(roles__name=ACCESS_NAMESPACE).count()
    )

    last_changes = Change.objects.prefetch().order().filter(component=obj)[:10]

    return render(
        request,
        "component.html",
        {
            "allow_index": True,
            "object": obj,
            "project": obj.project,
            "translations": sort_objects(
                prefetch_stats(obj.translation_set.prefetch())
            ),
            "reports_form": ReportsForm(),
            "last_changes": last_changes,
            "last_changes_url": urlencode(
                {"component": obj.slug, "project": obj.project.slug}
            ),
            "language_count": Language.objects.filter(translation__component=obj)
            .distinct()
            .count(),
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
            "whiteboard_form": optional_form(
                WhiteboardForm, user, "component.edit", obj
            ),
            "delete_form": optional_form(
                DeleteForm, user, "component.edit", obj, obj=obj
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
            "user_can_add_namespaced_translation": user_can_access_namespace,
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
            "whiteboard_form": optional_form(
                WhiteboardForm, user, "component.edit", obj
            ),
            "delete_form": optional_form(
                DeleteForm, user, "translation.delete", obj, obj=obj
            ),
            "last_changes": last_changes,
            "last_changes_url": urlencode(obj.get_reverse_url_kwargs()),
            "other_translations": prefetch_stats(
                Translation.objects.prefetch()
                .filter(component__project=obj.component.project, language=obj.language)
                .exclude(pk=obj.pk)
            ),
            "exporters": list_exporters(obj),
        },
    )


@never_cache
def data_project(request, project):
    obj = get_project(request, project)
    return render(
        request,
        "data.html",
        {"object": obj, "components": obj.component_set.order(), "project": obj},
    )


@never_cache
@login_required
def new_language(request, project, component):
    LOGGER.info("################# Hit the New Language handler")
    namespace = ""
    namespace_query = request.user.groups.filter(roles__name=ACCESS_NAMESPACE).order_by(
        "name"
    )
    if namespace_query.count():
        namespace = namespace_query[0]

    obj = get_component(request, project, component, skip_acl=bool(namespace))

    form_class = get_new_language_form(request, obj)
    can_add = obj.can_add_new_language(request)

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

    context = {
        "object": obj,
        "project": obj.project,
        "form": form,
        "can_add": can_add,
        "namespace": namespace,
        "namespaced_form": NewNamespacedLanguageForm(obj, namespace=namespace),
    }
    return render(request, "new-language.html", context)


@never_cache
@login_required
def new_namespaced_language(request, project, component):
    obj = get_component(request, project, component)

    namespace = ""
    namespace_query = request.user.groups.filter(roles__name=ACCESS_NAMESPACE).order_by(
        "name"
    )
    if namespace_query.count():
        namespace = namespace_query[0]

    if namespace and request.method == "POST":
        form = NewNamespacedLanguageForm(obj, request.POST)

        if form.is_valid():
            langs = form.cleaned_data["lang"]
            kwargs = {
                "user": request.user,
                "author": request.user,
                "component": obj,
                "details": {},
            }
            for language in Language.objects.filter(code__in=langs):
                namespaced_language = Language.objects.create(
                    code=language.code + NAMESPACE_SEPARATOR + namespace,
                    name="{} ({})".format(language.name, namespace),
                    direction=language.direction,
                )

                namespace_group = Group.objects.get(name=namespace)
                namespace_group.languages.add(namespaced_language)

                kwargs["details"]["language"] = namespaced_language.code
                translation = obj.add_new_language(namespaced_language, request)
                if translation:
                    kwargs["translation"] = translation
                    if len(langs) == 1:
                        obj = translation
                    Change.objects.create(action=Change.ACTION_ADDED_LANGUAGE, **kwargs)
            return redirect(obj)

    messages.error(request, _("Please fix errors in the form."))
    return redirect(obj)


@never_cache
def healthz(request):
    """Simple health check endpoint."""
    return HttpResponse("ok")


@never_cache
def show_component_list(request, name):
    obj = get_object_or_404(ComponentList, slug=name)

    return render(
        request,
        "component-list.html",
        {
            "object": obj,
            "components": obj.components.filter(
                project_id__in=request.user.allowed_project_ids
            ),
        },
    )
