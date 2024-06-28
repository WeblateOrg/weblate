# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import os


def get_env_str(
    name: str,
    default: str | None = None,
    required: bool = False,
    fallback_name: str | None = None,
) -> str:
    file_env = f"{name}_FILE"
    if filename := os.environ.get(file_env):
        try:
            with open(filename) as handle:
                result = handle.read()
        except OSError as error:
            raise ValueError(
                f"Failed to open {filename} as specified by {file_env}: {error}"
            ) from error
    else:
        if fallback_name and name not in os.environ:
            name = fallback_name
        result = os.environ.get(
            name,
            default,  # type: ignore[arg-type]
        )
    if required and not result:
        raise ValueError(f"{name} has to be configured!")
    return result


def get_env_list(name: str, default: list[str] | None = None) -> list[str]:
    """Get list from environment."""
    if name not in os.environ:
        return default or []
    return os.environ[name].split(",")


def get_env_map(name: str, default: dict[str, str] | None = None) -> dict[str, str]:
    """
    Get mapping from environment.

    parses 'full_name:name,email:mail' into {'email': 'mail', 'full_name': 'name'}
    """
    if os.environ.get(name):
        return dict(e.split(":") for e in os.environ[name].split(","))
    return default or {}


def get_env_int(name: str, default: int = 0) -> int:
    """Get integer value from environment."""
    if name not in os.environ:
        return default
    try:
        return int(os.environ[name])
    except ValueError as error:
        raise ValueError(f"{name} is not an integer: {error}") from error


def get_env_float(name: str, default: float = 0.0) -> float:
    """Get float value from environment."""
    if name not in os.environ:
        return default
    try:
        return float(os.environ[name])
    except ValueError as error:
        raise ValueError(f"{name} is not an float: {error}") from error


def get_env_bool(name: str, default: bool = False) -> bool:
    """Get boolean value from environment."""
    if name not in os.environ:
        return default
    true_values = {"true", "yes", "1"}
    return os.environ[name].lower() in true_values


def modify_env_list(current: list[str], name: str) -> list[str]:
    """Modify list based on environment (for example checks)."""
    for item in reversed(get_env_list(f"WEBLATE_ADD_{name}")):
        current.insert(0, item)
    for item in get_env_list(f"WEBLATE_REMOVE_{name}"):
        current.remove(item)
    return current


def get_env_credentials(
    name: str,
) -> dict[str, dict[str, str]]:
    """Get VCS integration credentials from environment."""
    if found_env_credentials := get_env_str(f"WEBLATE_{name}_CREDENTIALS"):
        return ast.literal_eval(found_env_credentials)
    username = os.environ.get(f"WEBLATE_{name}_USERNAME", "")
    token = os.environ.get(f"WEBLATE_{name}_TOKEN", "")
    host = os.environ.get(f"WEBLATE_{name}_HOST")
    organization = os.environ.get(f"WEBLATE_{name}_ORGANIZATION")

    if not host:
        if username or token:
            raise ValueError(
                f"Incomplete {name}_CREDENTIALS configuration: missing WEBLATE_{name}_HOST"
            )
        return {}

    credentials = {host: {"username": username, "token": token}}

    if organization is not None:
        credentials[host]["organization"] = organization

    return credentials


def get_env_ratelimit(name: str, default: str) -> str:
    value = os.environ.get(name, default)

    # Taken from rest_framework.throttling.SimpleRateThrottle.parse_rate
    # it can not be imported here as that breaks config loading for
    # rest_framework

    try:
        num, period = value.split("/")
    except ValueError as error:
        raise ValueError(f"Could not parse {name}: {error}") from error
    if not num.isdigit():
        raise ValueError(f"Could not parse {name}: rate is not numeric: {num}")
    if period[0] not in {"s", "m", "h", "d"}:
        raise ValueError(f"Could not parse {name}: unknown period: {period}")

    return value
