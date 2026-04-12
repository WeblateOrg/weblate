# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import TextChoices
from django.db.models.fields.files import FieldFile
from django.utils.translation import gettext, gettext_lazy, ngettext
from translation_finder.finder import EXCLUDES

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.core.files.base import File

WEBLATE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(WEBLATE_DIR)
DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_TEST_DIR = os.path.join(BASE_DIR, "data-test")
BUILD_DIR = os.path.join(BASE_DIR, "build")
VENV_DIR = os.path.join(BASE_DIR, ".venv")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
CLIENT_DIR = os.path.join(BASE_DIR, "client")
EXAMPLES_DIR = os.path.join(BASE_DIR, "weblate", "examples")

PATH_EXCLUDES = [f"/{exclude}/" for exclude in EXCLUDES]
REPO_TEMP_DIRNAME = "weblate-tmp"


class FileUploadMethod(TextChoices):
    TRANSLATE = "translate", gettext_lazy("Add as translation")
    APPROVE = "approve", gettext_lazy("Add as approved translation")
    SUGGEST = "suggest", gettext_lazy("Add as suggestion")
    FUZZY = "fuzzy", gettext_lazy("Add as translation needing edit")
    REPLACE = "replace", gettext_lazy("Replace existing translation file")
    SOURCE = "source", gettext_lazy("Update source strings")
    ADD = "add", gettext_lazy("Add new strings")


def get_upload_message(not_found: int, skipped: int, accepted: int, total: int) -> str:
    if total == 0:
        return gettext("No strings were imported from the uploaded file.")
    return ngettext(
        "Processed {0} string from the uploaded files "
        "(skipped: {1}, not found: {2}, updated: {3}).",
        "Processed {0} strings from the uploaded files "
        "(skipped: {1}, not found: {2}, updated: {3}).",
        total,
    ).format(total, skipped, not_found, accepted)


def remove_readonly(func: Callable, path: str, error: BaseException) -> None:
    """Clear the readonly bit and reattempt the removal."""
    if isinstance(error, FileNotFoundError):
        return
    if os.path.isdir(path):
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    else:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    if func in {os.open, os.lstat, os.rmdir}:
        # Could not remove a directory
        remove_tree(path)
    else:
        func(path)


def remove_tree(path: str | Path, ignore_errors: bool = False) -> None:
    shutil.rmtree(path, ignore_errors=ignore_errors, onexc=remove_readonly)


def should_skip(location):
    """Check for skipping location in manage commands."""
    excluded_directories = (
        VENV_DIR,
        settings.DATA_DIR,
        DEFAULT_DATA_DIR,
        BUILD_DIR,
        DEFAULT_TEST_DIR,
        DOCS_DIR,
        SCRIPTS_DIR,
        CLIENT_DIR,
        EXAMPLES_DIR,
    )
    return not is_path_within_directory(location, WEBLATE_DIR) or any(
        is_path_within_directory(location, excluded_directory)
        for excluded_directory in excluded_directories
    )


def is_excluded(path: str) -> bool:
    """Whether path should be excluded from zip extraction."""
    return any(exclude in f"/{path}/" for exclude in PATH_EXCLUDES) or ".." in path


def is_path_within_directory(path: str, directory: str) -> bool:
    """Check whether resolved path is contained within resolved directory."""
    try:
        resolved_directory = Path(directory).resolve(strict=False)
    except OSError:
        return False
    return is_path_within_resolved_directory(path, resolved_directory)


def is_path_within_resolved_directory(
    path: str | Path, resolved_directory: Path
) -> bool:
    """Check whether resolved path is contained within a resolved directory."""
    try:
        resolved_path = Path(path).resolve(strict=False)
    except OSError:
        return False
    return resolved_path.is_relative_to(resolved_directory)


def cleanup_error_message(text: str) -> str:
    """Remove absolute paths from the text."""
    return text.replace(settings.CACHE_DIR or "NONEXISTING_CACHE", "...").replace(
        settings.DATA_DIR, "..."
    )


def get_repo_temp_dir(path: str | Path, temp_dir: str | Path | None = None) -> Path:
    """Return the provided temporary directory or fall back beside the path."""
    try:
        resolved = Path(path).resolve(strict=False)
    except OSError:
        resolved = Path(path)
    result = resolved if resolved.is_dir() else resolved.parent
    if temp_dir is not None:
        result = Path(temp_dir)
    result.mkdir(parents=True, exist_ok=True)
    return result


def _validate_file_size(size: int | None, max_size: int | None) -> None:
    if max_size is not None and size is not None and size > max_size:
        raise ValidationError(gettext("Uploaded file is too big."))


def _read_content(filelike: FieldFile | File, max_size: int | None) -> bytes:
    _validate_file_size(getattr(filelike, "size", None), max_size)
    if max_size is None:
        return filelike.read()

    content = filelike.read(max_size + 1)
    if len(content) > max_size:
        raise ValidationError(gettext("Uploaded file is too big."))
    return content


def read_file_bytes(filelike: FieldFile | File, max_size: int | None = None) -> bytes:
    """Read file content without breaking Django's upload/save lifecycle."""
    if isinstance(filelike, FieldFile) and getattr(filelike, "_committed", True):
        filelike.open("rb")
        try:
            return _read_content(filelike, max_size)
        finally:
            filelike.close()

    filelike.seek(0)
    try:
        return _read_content(filelike, max_size)
    finally:
        filelike.seek(0)
