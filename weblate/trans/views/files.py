# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext, ngettext
from django.views.decorators.http import require_POST

from weblate.trans.exceptions import FailedCommitError, PluralFormsMismatchError
from weblate.trans.forms import DownloadForm, get_upload_form
from weblate.trans.models import Component, ComponentList, Project, Translation
from weblate.utils import messages
from weblate.utils.data import data_dir
from weblate.utils.errors import report_error
from weblate.utils.stats import ProjectLanguage
from weblate.utils.views import (
    download_translation_file,
    parse_path,
    show_form_errors,
    zip_download,
)


def download_multi(translations, commit_objs, fmt=None, name="translations"):
    filenames = set()
    components = set()

    for obj in commit_objs:
        try:
            obj.commit_pending("download", None)
        except Exception:
            if isinstance(obj, Project):
                report_error(cause="Download commit", project=obj)
            else:
                report_error(cause="Download commit", project=obj.project)

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
    if not request.user.has_perm("translation.download", obj):
        raise PermissionDenied
    components = obj.components.filter_access(request.user)
    return download_multi(
        Translation.objects.filter(component__in=components),
        components,
        request.GET.get("format"),
        name=obj.slug,
    )


def download(request, path):
    """Handling of translation uploads."""
    obj = parse_path(request, path, (Translation, Component, Project, ProjectLanguage))
    if not request.user.has_perm("translation.download", obj):
        raise PermissionDenied

    if isinstance(obj, Translation):
        kwargs = {}

        if "format" in request.GET or "q" in request.GET:
            form = DownloadForm(obj, request.GET)
            if not form.is_valid():
                show_form_errors(request, form)
                return redirect(obj)

            kwargs["query_string"] = form.cleaned_data.get("q", "")
            kwargs["fmt"] = form.cleaned_data["format"]

        return download_translation_file(request, obj, **kwargs)
    if isinstance(obj, ProjectLanguage):
        components = obj.project.component_set.filter_access(request.user)
        return download_multi(
            Translation.objects.filter(component__in=components, language=obj.language),
            [obj.project],
            request.GET.get("format"),
            name=f"{obj.project.slug}-{obj.language.code}",
        )
    if isinstance(obj, Project):
        components = obj.component_set.filter_access(request.user)
        return download_multi(
            Translation.objects.filter(component__in=components),
            [obj],
            request.GET.get("format"),
            name=obj.slug,
        )
    if isinstance(obj, Component):
        return download_multi(
            obj.translation_set.all(),
            [obj],
            request.GET.get("format"),
            name=obj.full_slug.replace("/", "-"),
        )
    raise TypeError(f"Unsupported download: {obj}")


@require_POST
def upload(request, path):
    """Handling of translation uploads."""
    obj = parse_path(request, path, (Translation,))

    if not request.user.has_perm("upload.perform", obj):
        raise PermissionDenied

    # Check method and lock
    if obj.component.locked:
        messages.error(request, gettext("Access denied."))
        return redirect(obj)

    # Get correct form handler based on permissions
    form = get_upload_form(request.user, obj, request.POST, request.FILES)

    # Check form validity
    if not form.is_valid():
        messages.error(request, gettext("Please fix errors in the form."))
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
        not_found, skipped, accepted, total = obj.handle_upload(
            request,
            request.FILES["file"],
            conflicts,
            author_name,
            author_email,
            method=form.cleaned_data["method"],
            fuzzy=form.cleaned_data["fuzzy"],
        )
        if total == 0:
            message = gettext("No strings were imported from the uploaded file.")
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
    except PluralFormsMismatchError:
        messages.error(
            request,
            gettext(
                "Plural forms in the uploaded file do not match current translation."
            ),
        )
    except FailedCommitError as error:
        messages.error(request, str(error))  # noqa: G200
        report_error(cause="Upload error", project=obj.component.project)
    except Exception as error:
        messages.error(
            request,
            gettext("File upload has failed: %s")
            % str(error).replace(obj.component.full_path, ""),
        )
        report_error(cause="Upload error", project=obj.component.project)

    return redirect(obj)
