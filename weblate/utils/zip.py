# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from shutil import copyfileobj
from typing import TYPE_CHECKING

from django.utils.translation import gettext

from weblate.utils.files import is_path_within_resolved_directory

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from zipfile import ZipFile, ZipInfo


class ZipSafetyError(ValueError):
    """Error raised for unsafe ZIP archive members."""


@dataclass(frozen=True, slots=True)
class ZipSafetyLimits:
    max_members: int | None = 100_000
    max_compressed_entry_size: int | None = 250 * 1024 * 1024
    min_compressed_ratio_size: int = 1 * 1024 * 1024
    max_compressed_entry_ratio: int | None = 250
    max_total_uncompressed_size: int | None = None


def _normalize_zip_member_path(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).as_posix().rstrip("/")


def validate_zip_member_path(filename: str) -> None:
    normalized = filename.replace("\\", "/")
    normalized_name = _normalize_zip_member_path(filename)
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(filename)
    if (
        not filename
        or normalized_name == "."
        or "\x00" in filename
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in posix_path.parts
        or ".." in windows_path.parts
    ):
        msg = gettext("ZIP file contains invalid path: {path}").format(path=filename)
        raise ZipSafetyError(msg)


def validate_zip_member_type(info: ZipInfo) -> None:
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if stat.S_ISLNK(mode):
        msg = gettext("ZIP file contains unsupported symbolic links.")
        raise ZipSafetyError(msg)
    if info.is_dir():
        if file_type and not stat.S_ISDIR(mode):
            msg = gettext("ZIP file contains unsupported special files.")
            raise ZipSafetyError(msg)
        return
    if file_type and not stat.S_ISREG(mode):
        msg = gettext("ZIP file contains unsupported special files.")
        raise ZipSafetyError(msg)


def validate_zip_members(
    zipfile: ZipFile,
    *,
    limits: ZipSafetyLimits,
    validate_member_name: Callable[[str], None] | None = None,
    validate_member: Callable[[ZipInfo], None] | None = None,
    skip_member: Callable[[ZipInfo], bool] | None = None,
) -> None:
    infos = zipfile.infolist()
    if limits.max_members is not None and len(infos) > limits.max_members:
        msg = gettext("The ZIP file contains too many entries.")
        raise ZipSafetyError(msg)

    total_uncompressed_size = 0
    seen_names: set[str] = set()
    for info in infos:
        validate_zip_member_path(info.filename)
        normalized_name = _normalize_zip_member_path(info.filename)
        if normalized_name in seen_names:
            msg = gettext(
                "The zip file contains duplicate files. Please generate a new backup with a newer version of Weblate."
            )
            raise ZipSafetyError(msg)
        seen_names.add(normalized_name)
        if validate_member_name is not None:
            validate_member_name(info.filename)
        if validate_member is not None:
            validate_member(info)
        if skip_member is not None and skip_member(info):
            continue

        validate_zip_member_type(info)
        if info.is_dir():
            continue

        total_uncompressed_size += info.file_size
        if (
            limits.max_total_uncompressed_size is not None
            and total_uncompressed_size > limits.max_total_uncompressed_size
        ):
            msg = gettext("The ZIP file contains too much uncompressed data.")
            raise ZipSafetyError(msg)

        if (
            limits.max_compressed_entry_size is not None
            and limits.max_compressed_entry_ratio is not None
            and info.file_size > limits.max_compressed_entry_size
        ):
            if info.file_size < limits.min_compressed_ratio_size:
                continue
            compressed_size = max(info.compress_size, 1)
            if info.file_size / compressed_size > limits.max_compressed_entry_ratio:
                msg = gettext(
                    "The ZIP file contains a compressed entry that is too large."
                )
                raise ZipSafetyError(msg)


def get_safe_zip_member_target(
    target: str | Path,
    filename: str,
    *,
    resolved_target: Path | None = None,
) -> Path:
    validate_zip_member_path(filename)
    root = resolved_target or Path(target).resolve(strict=False)
    destination = (root / filename.replace("\\", "/")).resolve(strict=False)
    if not is_path_within_resolved_directory(destination, root):
        msg = gettext("ZIP file contains invalid path: {path}").format(path=filename)
        raise ZipSafetyError(msg)
    return destination


def iter_safe_zip_members(
    zipfile: ZipFile,
    target: str | Path,
    *,
    members: Iterable[ZipInfo] | None = None,
    member_name: Callable[[ZipInfo], str] = lambda info: info.filename,
    skip_member: Callable[[ZipInfo], bool] | None = None,
) -> Iterator[tuple[ZipInfo, Path]]:
    resolved_target = Path(target).resolve(strict=False)
    source_members = zipfile.infolist() if members is None else members
    for info in source_members:
        if skip_member is not None and skip_member(info):
            continue
        validate_zip_member_type(info)
        yield (
            info,
            get_safe_zip_member_target(
                target,
                member_name(info),
                resolved_target=resolved_target,
            ),
        )


def extract_zip_member(zipfile: ZipFile, info: ZipInfo, target: Path) -> None:
    validate_zip_member_type(info)
    if info.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.open(info) as source, target.open("wb") as destination:
        copyfileobj(source, destination)
