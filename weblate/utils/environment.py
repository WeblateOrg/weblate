# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os


def get_env_list(name: str, default: list[str] | None = None) -> list[str]:
    """Helper to get list from environment."""
    if name not in os.environ:
        return default or []
    return os.environ[name].split(",")


def get_env_map(name: str, default: dict[str, str] | None = None) -> dict[str, str]:
    """
    Helper to get mapping from environment.

    parses 'full_name:name,email:mail' into {'email': 'mail', 'full_name': 'name'}
    """
    if os.environ.get(name):
        return dict(e.split(":") for e in os.environ[name].split(","))
    return default or {}


def get_env_int(name: str, default: int = 0) -> int:
    """Helper to get integer value from environment."""
    if name not in os.environ:
        return default
    try:
        return int(os.environ[name])
    except ValueError as error:
        raise ValueError(f"{name} is not an integer: {error}") from error


def get_env_float(name: str, default: float = 0.0) -> float:
    """Helper to get float value from environment."""
    if name not in os.environ:
        return default
    try:
        return float(os.environ[name])
    except ValueError as error:
        raise ValueError(f"{name} is not an float: {error}") from error


def get_env_bool(name: str, default: bool = False) -> bool:
    """Helper to get boolean value from environment."""
    if name not in os.environ:
        return default
    true_values = {"true", "yes", "1"}
    return os.environ[name].lower() in true_values


def modify_env_list(current: list[str], name: str) -> list[str]:
    """Helper to modify list (for example checks)."""
    for item in reversed(get_env_list(f"WEBLATE_ADD_{name}")):
        current.insert(0, item)
    for item in get_env_list(f"WEBLATE_REMOVE_{name}"):
        current.remove(item)
    return current


def get_env_credentials(
    name: str,
) -> dict[str, dict[str, str]]:
    """Parses VCS integration credentials."""
    username = os.environ.get(f"WEBLATE_{name}_USERNAME")
    token = os.environ.get(f"WEBLATE_{name}_TOKEN")
    host = os.environ.get(f"WEBLATE_{name}_HOST")

    if not host and (username or token):
        raise ValueError(
            f"Incomplete {name}_CREDENTIALS configuration: missing WEBLATE_{name}_HOST"
        )
    return {host: {"username": username, "token": token}}


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
    if period[0] not in ("s", "m", "h", "d"):
        raise ValueError(f"Could not parse {name}: unknown period: {period}")

    return value
