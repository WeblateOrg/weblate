# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import shutil
import stat
from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import TextChoices
from django.utils.translation import gettext, gettext_lazy, ngettext
from translation_finder.finder import EXCLUDES

if TYPE_CHECKING:
    from pathlib import Path

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


def remove_readonly(func, path, excinfo) -> None:
    """Clear the readonly bit and reattempt the removal."""
    if isinstance(excinfo[1], FileNotFoundError):
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
    # TODO: switch to onexc with Python >= 3.12
    shutil.rmtree(path, ignore_errors=ignore_errors, onerror=remove_readonly)


def should_skip(location):
    """Check for skipping location in manage commands."""
    location = os.path.abspath(location)
    return not location.startswith(WEBLATE_DIR) or location.startswith(
        (
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
    )


def is_excluded(path):
    """Whether path should be excluded from zip extraction."""
    return any(exclude in f"/{path}/" for exclude in PATH_EXCLUDES) or ".." in path
