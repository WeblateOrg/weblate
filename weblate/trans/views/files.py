#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import os

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from weblate.lang.models import Language
from weblate.trans.exceptions import PluralFormsMismatch
from weblate.trans.forms import DownloadForm, get_upload_form
from weblate.trans.models import ComponentList, Translation
from weblate.utils import messages
from weblate.utils.data import data_dir
from weblate.utils.errors import report_error
from weblate.utils.views import (
    download_translation_file,
    get_component,
    get_project,
    get_translation,
    show_form_errors,
    zip_download,
)


def download_multi(translations, fmt=None, name="translations"):
    filenames = set()
    components = set()

    for translation in translations:
        # Add translation files
        if translation.filename:
            filenames.add(translation.get_filename())
        # Add templates for all components
        if translation.component_id in components:
            continue
        components.add(translation.component_id)
        for filename in (
            translation.component.template,
            translation.component.new_base,
            translation.component.intermediate,
        ):
            if filename:
                fullname = os.path.join(translation.component.full_path, filename)
                if os.path.exists(fullname):
                    filenames.add(fullname)

    return zip_download(data_dir("vcs"), sorted(filenames), name)


def download_component_list(request, name):
    obj = get_object_or_404(ComponentList, slug__iexact=name)
    components = obj.components.filter_access(request.user)
    for component in components:
        component.commit_pending("download", None)
    return download_multi(
        Translation.objects.filter(component__in=components),
        request.GET.get("format"),
        name=obj.slug,
    )


def download_component(request, project, component):
    obj = get_component(request, project, component)
    obj.commit_pending("download", None)
    return download_multi(
        obj.translation_set.all(),
        request.GET.get("format"),
        name=obj.full_slug.replace("/", "-"),
    )


def download_project(request, project):
    obj = get_project(request, project)
    obj.commit_pending("download", None)
    components = obj.component_set.filter_access(request.user)
    return download_multi(
        Translation.objects.filter(component__in=components),
        request.GET.get("format"),
        name=obj.slug,
    )


def download_lang_project(request, lang, project):
    obj = get_project(request, project)
    obj.commit_pending("download", None)
    langobj = get_object_or_404(Language, code=lang)
    components = obj.component_set.filter_access(request.user)
    return download_multi(
        Translation.objects.filter(component__in=components, language=langobj),
        request.GET.get("format"),
        name=f"{obj.slug}-{langobj.code}",
    )


def download_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    kwargs = {}

    if "format" in request.GET or "q" in request.GET:
        form = DownloadForm(request.GET)
        if not form.is_valid():
            show_form_errors(request, form)
            return redirect(obj)

        kwargs["units"] = (
            obj.unit_set.search(
                form.cleaned_data.get("q", ""), project=obj.component.project
            )
            .distinct()
            .order_by("position")
            .prefetch_full()
        )
        kwargs["fmt"] = form.cleaned_data["format"]

    return download_translation_file(request, obj, **kwargs)


@require_POST
def upload_translation(request, project, component, lang):
    """Handling of translation uploads."""
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("upload.perform", obj):
        raise PermissionDenied()

    # Check method and lock
    if obj.component.locked:
        messages.error(request, _("Access denied."))
        return redirect(obj)

    # Get correct form handler based on permissions
    form = get_upload_form(request.user, obj, request.POST, request.FILES)

    # Check form validity
    if not form.is_valid():
        messages.error(request, _("Please fix errors in the form."))
        show_form_errors(request, form)
        return redirect(obj)

    # Create author name
    author_name = None
    author_email = None
    if request.user.has_perm("upload.authorship", obj):
        author_name = form.cleaned_data["author_name"]
        author_email = form.cleaned_data["author_email"]

    # Check for overwriting
    conflicts = ""
    if request.user.has_perm("upload.overwrite", obj):
        conflicts = form.cleaned_data["conflicts"]

    # Do actual import
    try:
        not_found, skipped, accepted, total = obj.merge_upload(
            request,
            request.FILES["file"],
            conflicts,
            author_name,
            author_email,
            method=form.cleaned_data["method"],
            fuzzy=form.cleaned_data["fuzzy"],
        )
        if total == 0:
            message = _("No strings were imported from the uploaded file.")
        else:
            message = ngettext(
                "Processed {0} string from the uploaded files "
                "(skipped: {1}, not found: {2}, updated: {3}).",
                "Processed {0} strings from the uploaded files "
                "(skipped: {1}, not found: {2}, updated: {3}).",
                total,
            ).format(total, skipped, not_found, accepted)
        if accepted == 0:
            messages.warning(request, message)
        else:
            messages.success(request, message)
    except PluralFormsMismatch:
        messages.error(
            request,
            _("Plural forms in the uploaded file do not match current translation."),
        )
    except Exception as error:
        messages.error(
            request,
            _("File upload has failed: %s")
            % str(error).replace(obj.component.full_path, ""),
        )
        report_error(cause="Upload error")

    return redirect(obj)
