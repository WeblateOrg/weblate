# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from functools import wraps
from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import SimpleLazyObject
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from weblate.auth.bots import InternalBot
from weblate.formats.base import is_identity_safe_exporter
from weblate.formats.models import EXPORTERS
from weblate.trans.exceptions import (
    FailedCommitError,
    FileParseError,
    PluralFormsMismatchError,
)
from weblate.trans.forms import DownloadForm, get_upload_form
from weblate.trans.models import (
    Category,
    Component,
    ComponentList,
    Project,
    Translation,
)
from weblate.trans.util import get_upload_error_message
from weblate.utils import messages
from weblate.utils.data import data_dir
from weblate.utils.errors import report_error
from weblate.utils.files import get_upload_message
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.utils.views import (
    download_translation_file,
    parse_path,
    repository_lock_timeout_response,
    show_form_errors,
    write_zip_files,
    zip_download,
    zip_download_archive,
)
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from zipfile import ZipFile

    from django.db.models import Model, QuerySet
    from django.http import HttpResponseBase

    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.trans.models.translation import TranslationQuerySet


def handle_repository_lock_timeout[**P](
    view: Callable[P, HttpResponseBase],
) -> Callable[P, HttpResponseBase]:
    """Convert repository lock timeouts only at the browser view boundary."""

    @wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> HttpResponseBase:
        try:
            return view(*args, **kwargs)
        except WeblateLockTimeoutError as error:
            return repository_lock_timeout_response(error)

    return wrapper


def get_download_components(
    translations: QuerySet[Translation],
) -> QuerySet[Component]:
    """Return components represented by a translation queryset."""
    return Component.objects.filter(
        pk__in=translations.order_by().values("component_id")
    ).select_related("project")


def prepare_download_scope(
    user: User,
    translations: TranslationQuerySet,
    empty_permission_obj: Model | ProjectLanguage | CategoryLanguage | None = None,
    *,
    fmt: str | None = None,
) -> tuple[TranslationQuerySet, QuerySet[Component]]:
    """Apply download permission and validate an aggregate download scope."""
    downloadable = translations.filter_permission_scope(user, "translation.download")
    from weblate.auth.scope import get_permission_scope_query  # ruff: ignore[import-outside-top-level]

    exporter = EXPORTERS.get(fmt[4:]) if fmt and fmt.startswith("zip:") else None
    if not is_identity_safe_exporter(exporter):
        downloadable = downloadable.filter(
            get_permission_scope_query(
                user,
                "contribution.view_author",
                component_path="component",
                language_path="language_id",
            )
        )
    if not downloadable.exists() and (
        translations.exists()
        or empty_permission_obj is None
        or not user.has_perm("translation.download", empty_permission_obj)
    ):
        raise PermissionDenied
    return downloadable, get_download_components(downloadable)


def get_workspace_download_components(
    user: User, workspace: Workspace
) -> list[Component]:
    """Return workspace components represented by downloadable translations."""
    translations = Translation.objects.filter(component__project__workspace=workspace)
    return list(
        get_download_components(
            translations.filter_permission_scope(user, "translation.download")
        )
    )


def can_download_workspace(user: User, workspace: Workspace) -> bool:
    """Return whether the user can download any workspace translation."""
    return (
        Translation.objects.filter(component__project__workspace=workspace)
        .filter_permission_scope(user, "translation.download")
        .exists()
    )


def _group_download_translations(
    translations: Iterable[Translation],
) -> dict[int, tuple[Component, list[Translation]]]:
    repository_groups: dict[int, tuple[Component, list[Translation]]] = {}
    for translation in translations:
        repo_component = translation.component.effective_repo_component
        if repo_component.pk is None:
            msg = "Can not download files from an unsaved component"
            raise ValueError(msg)
        group = repository_groups.setdefault(repo_component.pk, (repo_component, []))
        group[1].append(translation)
    return repository_groups


def _write_repository_download_files(
    zipfile: ZipFile,
    repo_component: Component,
    translations: Iterable[Translation],
) -> None:
    with repo_component.repository.lock:
        filenames: set[str] = set()
        components: set[int] = set()
        component_roots: set[str] = set()
        for translation in translations:
            component_roots.add(translation.component.full_path)
            if translation.filename:
                filename = translation.get_filename()
                if filename:
                    filenames.add(filename)
            if translation.component_id in components:
                continue
            components.add(translation.component_id)
            for getter in (
                translation.component.get_template_filename,
                translation.component.get_new_base_filename,
                translation.component.get_intermediate_filename,
            ):
                try:
                    fullname = getter()
                except ValidationError:
                    continue
                if fullname and os.path.exists(fullname):
                    filenames.add(fullname)

        write_zip_files(
            zipfile,
            data_dir("vcs"),
            sorted(filenames),
            allowed_roots=sorted(component_roots),
            refresh_lock=repo_component.repository.lock.reacquire,
        )


def download_multi(
    request: AuthenticatedHttpRequest,
    translations,
    commit_objs,
    fmt=None,
    name="translations",
):
    extra: dict[str, str | bytes] = {}
    # Resolve the commit bot only when needed, once for the whole download.
    commit_user = SimpleLazyObject(InternalBot.COMMIT.get_user)

    for obj in commit_objs:
        try:
            obj.commit_pending("download", commit_user)
        except Exception:
            if isinstance(obj, Project):
                report_error("Download commit", project=obj)
            else:
                report_error("Download commit", project=obj.project)

    if fmt and fmt.startswith("zip:"):
        exporter_format = fmt[4:]
        try:
            exporter_cls = EXPORTERS[exporter_format]
        except KeyError as exc:
            msg = f"Conversion to {exporter_format} is not supported"
            raise Http404(msg) from exc

        for translation in translations:
            if not exporter_cls.supports(translation):
                filename = (
                    f"{'-'.join(translation.get_url_path())}.{exporter_cls.extension}"
                )
                extra[f"{filename}.skipped"] = (
                    "File format is not compatible with this translation"
                )
            else:
                exporter = exporter_cls(translation=translation)
                filename = exporter.get_filename()
                units = translation.unit_set.prefetch_full().order_by("position")
                exporter.add_units(units)
                extra[filename] = exporter.serialize()
        return zip_download(data_dir("vcs"), [], name, extra=extra)

    repository_groups = _group_download_translations(translations)

    with zip_download_archive(name) as (response, zipfile):
        for _pk, (repo_component, group_translations) in sorted(
            repository_groups.items()
        ):
            _write_repository_download_files(
                zipfile, repo_component, group_translations
            )

    return response


@handle_repository_lock_timeout
def download_component_list(request: AuthenticatedHttpRequest, name):
    obj = get_object_or_404(
        ComponentList.objects.filter_access(request.user), slug__iexact=name
    )
    translations, components = prepare_download_scope(
        request.user,
        Translation.objects.filter(component__in=obj.components.all()),
        obj,
        fmt=request.GET.get("format"),
    )
    return download_multi(
        request,
        translations,
        components,
        request.GET.get("format"),
        name=obj.slug,
    )


@handle_repository_lock_timeout
def download(request: AuthenticatedHttpRequest, path):
    """Download translation."""
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
            Workspace,
        ),
    )
    if isinstance(obj, Workspace):
        translations, components = prepare_download_scope(
            request.user,
            Translation.objects.filter(component__project__workspace=obj),
            fmt=request.GET.get("format"),
        )
        return download_multi(
            request,
            translations.prefetch(),
            components,
            request.GET.get("format"),
            name=f"workspace-{obj.pk}",
        )

    if isinstance(obj, Translation):
        if not request.user.has_perm("translation.download", obj):
            raise PermissionDenied
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
        translations, components = prepare_download_scope(
            request.user,
            Translation.objects.filter(
                component__project=obj.project, language=obj.language
            ),
            obj,
            fmt=request.GET.get("format"),
        )
        return download_multi(
            request,
            translations.prefetch(),
            components,
            request.GET.get("format"),
            name=f"{obj.project.slug}-{obj.language.code}",
        )
    if isinstance(obj, Project):
        translations, components = prepare_download_scope(
            request.user,
            Translation.objects.filter(component__project=obj),
            obj,
            fmt=request.GET.get("format"),
        )
        return download_multi(
            request,
            translations.prefetch(),
            components,
            request.GET.get("format"),
            name=obj.slug,
        )
    if isinstance(obj, CategoryLanguage):
        translations, components = prepare_download_scope(
            request.user,
            Translation.objects.filter(
                component_id__in=obj.category.all_component_ids,
                language=obj.language,
            ),
            obj,
            fmt=request.GET.get("format"),
        )
        return download_multi(
            request,
            translations.prefetch(),
            components,
            request.GET.get("format"),
            name=f"{obj.category.slug}-{obj.language.code}",
        )
    if isinstance(obj, Category):
        translations, components = prepare_download_scope(
            request.user,
            Translation.objects.filter(component_id__in=obj.all_component_ids),
            obj,
            fmt=request.GET.get("format"),
        )
        return download_multi(
            request,
            translations.prefetch(),
            components,
            request.GET.get("format"),
            name=obj.slug,
        )
    if isinstance(obj, Component):
        translations, components = prepare_download_scope(
            request.user,
            obj.translation_set.all(),
            obj,
            fmt=request.GET.get("format"),
        )
        return download_multi(
            request,
            translations.prefetch_meta(),
            components,
            request.GET.get("format"),
            name=obj.full_slug.replace("/", "-"),
        )
    msg = f"Unsupported download: {obj}"
    raise TypeError(msg)


@require_POST
def upload(request: AuthenticatedHttpRequest, path):
    """Handle translation upload."""
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
            ignore_language=form.cleaned_data["ignore_language"],
        )
    except PluralFormsMismatchError:
        messages.error(
            request,
            gettext(
                "Plural forms in the uploaded file do not match current translation."
            ),
        )
    except FileParseError as error:
        messages.error(
            request,
            get_upload_error_message(
                error,
                repo_urls=(obj.component.repo, obj.component.push),
                extra_paths=(obj.component.full_path,),
            ),
        )
    except FailedCommitError as error:
        messages.error(
            request,
            get_upload_error_message(
                error,
                repo_urls=(obj.component.repo, obj.component.push),
                extra_paths=(obj.component.full_path,),
            ),
        )
        report_error("Upload error", project=obj.component.project)
    except DatabaseError as error:
        messages.error(
            request,
            get_upload_error_message(
                error,
                repo_urls=(obj.component.repo, obj.component.push),
                extra_paths=(obj.component.full_path,),
            ),
        )
        report_error("Upload error", project=obj.component.project)
    except Exception as error:
        messages.error(
            request,
            get_upload_error_message(
                error,
                repo_urls=(obj.component.repo, obj.component.push),
                extra_paths=(obj.component.full_path,),
            ),
        )
        report_error("Upload error", project=obj.component.project)
    else:
        message = get_upload_message(not_found, skipped, accepted, total)
        if accepted == 0:
            messages.warning(request, message)
        else:
            messages.success(request, message)

    return redirect(obj)
