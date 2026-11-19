# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import shutil
import stat
from bisect import bisect_left
from contextlib import suppress
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from glob import has_magic
from pathlib import Path, PurePosixPath, PureWindowsPath
from time import monotonic
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import TextChoices
from django.db.models.fields.files import FieldFile
from django.utils.translation import gettext, gettext_lazy, ngettext
from translation_finder.finder import EXCLUDES

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

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

PATH_EXCLUDES = [f"/{exclude.casefold()}/" for exclude in EXCLUDES]
MANAGED_VCS_METADATA_DIRS = frozenset((".git", ".hg"))
ARCHIVE_VCS_METADATA_NAMES = frozenset(
    (
        ".git",
        ".hg",
        ".svn",
        ".bzr",
        "_darcs",
        "_mtn",
        ".pijul",
        ".pc",
        "_fossil_",
        ".fslckout",
        "bitkeeper",
    )
)
REPO_TEMP_DIRNAME = "weblate-tmp"


class PathMatchLimitError(Exception):
    """Repository path matching exceeded its work or time budget."""


@dataclass
class PathMatchBudget:
    """Shared budget for enumeration and subsequent match processing."""

    max_work: int = 100_000
    deadline: float = field(default_factory=lambda: monotonic() + 5)
    work: int = 0

    def check(self, work: int = 0) -> None:
        self.work += work
        if self.work > self.max_work:
            msg = "File mask traversal work limit exceeded"
            raise PathMatchLimitError(msg)
        if monotonic() >= self.deadline:
            msg = "File mask scan deadline exceeded"
            raise PathMatchLimitError(msg)


def bounded_glob(root: str, pattern: str, *, budget: PathMatchBudget) -> list[str]:
    """Match a repository-relative mask without unbounded glob enumeration."""
    budget.check()
    root_path = Path(root)
    try:
        base = root_path.resolve(strict=True)
        root_stat = base.stat()
    except (OSError, RuntimeError):
        budget.check()
        return []
    parts = pattern.split("/")
    # Directory identities are branch-local: independent aliases remain valid.
    directories = [(root_path, 0, frozenset({(root_stat.st_dev, root_stat.st_ino)}))]
    matches: list[str] = []

    def visit(path: Path, index: int, ancestors: frozenset[tuple[int, int]]) -> None:
        budget.check(1)
        try:
            resolved = path.resolve(strict=True)
            info = path.stat()
        except (OSError, RuntimeError):
            # Ignore inaccessible, disappearing, dangling, and looping links.
            return
        finally:
            budget.check()
        if not resolved.is_relative_to(base):
            return
        if is_managed_vcs_metadata_path(str(path.relative_to(root_path))) or (
            is_managed_vcs_metadata_path(str(resolved.relative_to(base)))
        ):
            return
        if index == len(parts) - 1:
            matches.append(str(path))
            return
        identity = (info.st_dev, info.st_ino)
        if stat.S_ISDIR(info.st_mode) and identity not in ancestors:
            directories.append((path, index + 1, ancestors | {identity}))

    while directories:
        directory, index, ancestors = directories.pop()
        budget.check(1)
        segment = parts[index]
        if not has_magic(segment):
            visit(directory / segment, index, ancestors)
            continue
        with suppress(OSError), os.scandir(directory) as entries:
            for entry in entries:
                budget.check(1)
                if entry.name.startswith(".") and not segment.startswith("."):
                    continue
                if fnmatchcase(entry.name, segment):
                    visit(directory / entry.name, index, ancestors)
    budget.check()
    return matches


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


def remove_tree(path: str | Path, ignore_errors: bool = False) -> None:
    retried: set[str] = set()

    def remove_readonly(func: Callable, path: str, error: BaseException) -> None:
        """Clear the readonly bit and retry each path at most once."""
        if isinstance(error, FileNotFoundError):
            return
        key = os.fspath(path)
        if not isinstance(error, PermissionError) or key in retried:
            raise error
        retried.add(key)
        if os.path.isdir(path):
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        else:
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        if func in {os.open, os.lstat}:
            # Restart traversal after restoring directory access. Share the
            # retry budget so persistent permission errors cannot recurse.
            shutil.rmtree(path, onexc=remove_readonly)
        else:
            func(path)

    shutil.rmtree(path, ignore_errors=ignore_errors, onexc=remove_readonly)


def should_skip(location: str | os.PathLike[str]) -> bool:
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
    normalized = normalize_archive_path(path)
    return any(
        exclude in f"/{normalized}/" for exclude in PATH_EXCLUDES
    ) or is_unsafe_path(path)


def _normalize_metadata_path_component(component: str) -> str:
    if component in {".", ".."}:
        return component
    return component.casefold().rstrip(". ")


def normalize_archive_path(path: str) -> str:
    """Normalize an archive path for metadata comparisons."""
    normalized = PurePosixPath(path.replace("\\", "/"))
    return PurePosixPath(
        *(_normalize_metadata_path_component(part) for part in normalized.parts)
    ).as_posix()


def get_archive_vcs_metadata_members(paths: Iterable[str]) -> frozenset[str]:
    """Return known VCS metadata members from a working-tree archive."""
    entries: set[str] = set()
    metadata_roots: set[str] = set()
    bitkeeper_parents: set[str] = set()

    for path in paths:
        normalized = normalize_archive_path(path)
        entries.add(normalized)
        parts = PurePosixPath(normalized).parts
        for index, part in enumerate(parts):
            # The first metadata root contains the remainder of this entry. Keeping
            # only that root also bounds retained data independently of path depth.
            if part in ARCHIVE_VCS_METADATA_NAMES:
                metadata_roots.add("/".join(parts[: index + 1]))
                if part == "bitkeeper":
                    bitkeeper_parents.add("/".join(parts[:index]))
                break
            if part == "cvs" and index + 1 < len(parts):
                if parts[index + 1] in {"entries", "root"}:
                    metadata_roots.add("/".join(parts[: index + 1]))
                    break
            elif part == "cvsroot" and index + 1 < len(parts):
                if parts[index + 1] in {"config", "loginfo", "modules", "passwd"}:
                    metadata_roots.add("/".join(parts[: index + 1]))
                    break
            elif (part == "rcs" and parts[-1].endswith(",v")) or (
                part == "sccs" and parts[-1].startswith("s.")
            ):
                metadata_roots.add("/".join(parts[: index + 1]))
                break

    metadata_roots.update(
        f"{parent}/changeset" if parent else "changeset" for parent in bitkeeper_parents
    )

    sorted_entries = sorted(entries)
    excluded: set[str] = set()
    ranges: list[tuple[int, int]] = []
    for root in metadata_roots:
        exact = bisect_left(sorted_entries, root)
        if exact < len(sorted_entries) and sorted_entries[exact] == root:
            excluded.add(root)

        prefix = f"{root}/"
        # Descendants form one lexical range between "root/" and "root0".
        # Store ranges rather than a trie node and ancestor tuple per path segment.
        start = bisect_left(sorted_entries, prefix)
        end = bisect_left(sorted_entries, f"{root}0", lo=start)
        if start < end:
            ranges.append((start, end))

    range_end = 0
    for start, end in sorted(ranges):
        if start > range_end:
            excluded.update(sorted_entries[start:end])
            range_end = end
        elif end > range_end:
            excluded.update(sorted_entries[range_end:end])
            range_end = end

    return frozenset(excluded)


def is_unsafe_path(path: str) -> bool:
    """Whether path points outside a relative path."""
    normalized = path.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(path)
    return (
        ".." in posix_path.parts
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
    )


def is_managed_vcs_metadata_path(
    path: str, metadata_dirs: Iterable[str] = MANAGED_VCS_METADATA_DIRS
) -> bool:
    """Whether path points to metadata used by a Weblate VCS backend."""
    normalized = normalize_archive_path(path)
    normalized_metadata_dirs = {
        _normalize_metadata_path_component(name) for name in metadata_dirs
    }
    return any(
        part in normalized_metadata_dirs for part in PurePosixPath(normalized).parts
    )


def is_path_within_directory(
    path: str | os.PathLike[str], directory: str | os.PathLike[str]
) -> bool:
    """Check whether resolved path is contained within resolved directory."""
    try:
        resolved_directory = Path(directory).resolve(strict=False)
    except OSError:
        return False
    return is_path_within_resolved_directory(path, resolved_directory)


def is_path_within_resolved_directory(
    path: str | os.PathLike[str], resolved_directory: Path
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


def _get_path_device_id(path: Path) -> int | None:
    current = path
    while True:
        try:
            return current.stat().st_dev
        except OSError:
            parent = current.parent
            if parent == current:
                return None
            current = parent


def get_repo_temp_dir(path: str | Path, temp_dir: str | Path | None = None) -> Path:
    """
    Return a temp directory suitable for atomic replacement into ``path``.

    The returned directory is the target directory itself, or the parent of
    ``path`` when ``path`` does not point to a directory. If ``temp_dir`` is
    provided, it is only used when it appears to be on the same filesystem
    device as the target directory; otherwise this falls back to the
    path-adjacent directory so atomic replace operations remain possible.
    """
    try:
        resolved = Path(path).resolve(strict=False)
    except OSError:
        resolved = Path(path)
    result = resolved if resolved.is_dir() else resolved.parent
    if temp_dir is not None:
        explicit = Path(temp_dir)
        result_device = _get_path_device_id(result)
        explicit_device = _get_path_device_id(explicit)
        if (
            result_device is not None
            and explicit_device is not None
            and result_device == explicit_device
        ):
            explicit.mkdir(parents=True, exist_ok=True)
            return explicit
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
