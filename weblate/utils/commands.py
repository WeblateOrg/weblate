# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import sys
from pathlib import Path

from django.core.management.utils import find_command

from weblate.utils.data import data_dir

DEFAULT_PATH = "/bin:/usr/bin:/usr/local/bin"


def get_runtime_interpreter_dir() -> Path | None:
    """Return the active interpreter directory when it is safely resolvable."""
    executable = sys.executable
    if not executable:
        return None
    executable_path = Path(executable)
    if not executable_path.is_absolute():
        return None
    return executable_path.parent


def build_runtime_path(
    current_path: str,
    *,
    extra_path: str | None = None,
) -> str:
    """Build PATH for subprocesses."""
    return os.pathsep.join(
        build_runtime_path_entries(current_path, extra_path=extra_path)
    )


def build_runtime_path_entries(
    current_path: str,
    *,
    extra_path: str | None = None,
) -> list[str]:
    """Build PATH entries for subprocesses and runtime command resolution."""
    path_entries = current_path.split(os.pathsep) if current_path else []
    interpreter_dir = get_runtime_interpreter_dir()
    additional_paths = [
        extra_path,
        None if interpreter_dir is None else os.fspath(interpreter_dir),
        os.path.join(sys.exec_prefix, "bin"),
    ]
    unique_additional_paths: list[str] = []
    for candidate in additional_paths:
        if not candidate or candidate in unique_additional_paths:
            continue
        unique_additional_paths.append(candidate)
    merged_paths: list[str] = []
    for candidate in path_entries:
        if not candidate or candidate in merged_paths:
            continue
        merged_paths.append(candidate)
    missing_paths = [
        candidate
        for candidate in unique_additional_paths
        if candidate and candidate not in merged_paths
    ]
    return [*missing_paths, *merged_paths]


def get_clean_env(
    extra: dict[str, str] | None = None, extra_path: str | None = None
) -> dict[str, str]:
    """Return cleaned up environment for subprocess execution."""
    environ = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": data_dir("home"),
        "PATH": DEFAULT_PATH,
    }
    if extra is not None:
        environ.update(extra)
    variables = (
        # Keep PATH setup
        "PATH",
        # Keep Python search path
        "PYTHONPATH",
        # Keep linker configuration
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        # Fontconfig configuration by weblate.fonts
        "FONTCONFIG_FILE",
        # Needed by Git on Windows
        "SystemRoot",
        # Pass proxy configuration
        "http_proxy",
        "https_proxy",
        "HTTPS_PROXY",
        "NO_PROXY",
        # below two are needed for openshift3 deployment,
        # where nss_wrapper is used
        # more on the topic on below link:
        # https://docs.openshift.com/enterprise/3.2/creating_images/guidelines.html
        "NSS_WRAPPER_GROUP",
        "NSS_WRAPPER_PASSWD",
    )
    for var in variables:
        if var in os.environ:
            environ[var] = os.environ[var]
    environ["PATH"] = build_runtime_path(environ["PATH"], extra_path=extra_path)
    return environ


def find_runtime_command(command: str, *, extra_path: str | None = None) -> str | None:
    """Find executable using the same PATH used for subprocess execution."""
    return find_command(
        command,
        path=build_runtime_path_entries(
            os.environ.get("PATH", DEFAULT_PATH), extra_path=extra_path
        ),
    )
