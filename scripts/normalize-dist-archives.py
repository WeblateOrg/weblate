#!/usr/bin/env python

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import argparse
import copy
import gzip
import os
import stat
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import IO

TAR_PAX_METADATA = {
    "atime",
    "ctime",
    "gid",
    "gname",
    "mtime",
    "uid",
    "uname",
}


def parse_source_date_epoch(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        msg = "SOURCE_DATE_EPOCH must be an integer"
        raise argparse.ArgumentTypeError(msg) from None
    if result < 0:
        msg = "SOURCE_DATE_EPOCH must be non-negative"
        raise argparse.ArgumentTypeError(msg)
    return result


def replace_archive(original: Path, temporary: Path) -> None:
    mode = stat.S_IMODE(original.stat().st_mode)
    os.replace(temporary, original)
    original.chmod(mode)


def temporary_path(path: Path) -> Path:
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    return Path(name)


def normalized_tar_mode(member: tarfile.TarInfo) -> int:
    if member.isdir():
        return 0o755
    if member.isfile():
        if member.mode & 0o111:
            return 0o755
        return 0o644
    return member.mode


def normalize_tar_member(
    member: tarfile.TarInfo, source_date_epoch: int
) -> tarfile.TarInfo:
    result = copy.copy(member)
    result.uid = 0
    result.gid = 0
    result.uname = ""
    result.gname = ""
    result.mtime = source_date_epoch
    result.mode = normalized_tar_mode(member)
    result.pax_headers = {
        key: value
        for key, value in member.pax_headers.items()
        if key not in TAR_PAX_METADATA
    }
    return result


def extract_tar_file(source: tarfile.TarFile, member: tarfile.TarInfo) -> IO[bytes]:
    source_file = source.extractfile(member)
    if source_file is None:
        msg = f"Could not read regular tar member: {member.name}"
        raise ValueError(msg)
    return source_file


def normalized_zip_mode(info: zipfile.ZipInfo) -> int:
    mode = info.external_attr >> 16
    if info.is_dir():
        return stat.S_IFDIR | 0o755
    if stat.S_ISREG(mode) or stat.S_IFMT(mode) == 0:
        if mode & 0o111:
            return stat.S_IFREG | 0o755
        return stat.S_IFREG | 0o644
    return mode


def write_normalized_sdist(path: Path, temporary: Path, source_date_epoch: int) -> None:
    with (
        tarfile.open(path, "r:gz") as source,
        temporary.open("wb") as raw,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, mtime=source_date_epoch
        ) as gzip_file,
        tarfile.open(mode="w", fileobj=gzip_file, format=tarfile.PAX_FORMAT) as target,
    ):
        for member in source.getmembers():
            normalized = normalize_tar_member(member, source_date_epoch)
            if member.isfile():
                with extract_tar_file(source, member) as source_file:
                    target.addfile(normalized, source_file)
            else:
                target.addfile(normalized)


def normalize_sdist(path: Path, source_date_epoch: int) -> None:
    temporary = temporary_path(path)
    try:
        write_normalized_sdist(path, temporary, source_date_epoch)
        replace_archive(path, temporary)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def normalize_zip_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    # Setuptools already writes wheel timestamps from SOURCE_DATE_EPOCH and does
    # not emit timestamp extra fields in these wheels. Keep those fields as-is
    # so the two-build comparison catches backend regressions instead of hiding
    # them in this narrow metadata normalizer.
    result = zipfile.ZipInfo(info.filename, info.date_time)
    result.comment = info.comment
    result.compress_type = info.compress_type
    result.create_system = info.create_system
    result.create_version = info.create_version
    result.external_attr = normalized_zip_mode(info) << 16
    result.extract_version = info.extract_version
    result.extra = info.extra
    result.flag_bits = info.flag_bits
    result.internal_attr = info.internal_attr
    result.volume = info.volume
    return result


def write_normalized_wheel(path: Path, temporary: Path) -> None:
    with (
        zipfile.ZipFile(path) as source,
        zipfile.ZipFile(temporary, "w", allowZip64=True) as target,
    ):
        target.comment = source.comment
        for info in source.infolist():
            normalized = normalize_zip_info(info)
            if info.is_dir():
                target.writestr(normalized, b"")
            else:
                with source.open(info) as source_file:
                    target.writestr(normalized, source_file.read())


def normalize_wheel(path: Path) -> None:
    temporary = temporary_path(path)
    try:
        write_normalized_wheel(path, temporary)
        replace_archive(path, temporary)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def normalize_archive(path: Path, source_date_epoch: int) -> None:
    if path.name.endswith(".tar.gz"):
        normalize_sdist(path, source_date_epoch)
    elif path.suffix == ".whl":
        # Wheel timestamps are intentionally left unchanged; see
        # normalize_zip_info() for the setuptools expectation.
        normalize_wheel(path)
    else:
        msg = f"Unsupported archive type: {path}"
        raise ValueError(msg)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize known non-reproducible metadata in package archives."
    )
    parser.add_argument(
        "--source-date-epoch",
        type=parse_source_date_epoch,
        help="Timestamp to use for archive metadata; defaults to SOURCE_DATE_EPOCH.",
    )
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    if args.source_date_epoch is None:
        value = os.environ.get("SOURCE_DATE_EPOCH")
        if value is None:
            parser.error("SOURCE_DATE_EPOCH is not set")
        try:
            args.source_date_epoch = parse_source_date_epoch(value)
        except argparse.ArgumentTypeError as error:
            parser.error(str(error))
    return args


def main() -> int:
    args = parse_args()
    for archive in args.archives:
        normalize_archive(archive, args.source_date_epoch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
