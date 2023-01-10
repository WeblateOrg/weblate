# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from typing import Dict, List, Optional, Tuple


def get_env_list(name: str, default: Optional[List[str]] = None) -> List[str]:
    """Helper to get list from environment."""
    if name not in os.environ:
        return default or []
    return os.environ[name].split(",")


def get_env_map(name: str, default: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Helper to get mapping from environment.

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
        raise ValueError(f"{name} is not an integer: {error}")


def get_env_float(name: str, default: float = 0.0) -> float:
    """Helper to get float value from environment."""
    if name not in os.environ:
        return default
    try:
        return float(os.environ[name])
    except ValueError as error:
        raise ValueError(f"{name} is not an float: {error}")


def get_env_bool(name: str, default: bool = False) -> bool:
    """Helper to get boolean value from environment."""
    if name not in os.environ:
        return default
    true_values = {"true", "yes", "1"}
    return os.environ[name].lower() in true_values


def modify_env_list(current: List[str], name: str) -> List[str]:
    """Helper to modify list (for example checks)."""
    for item in reversed(get_env_list(f"WEBLATE_ADD_{name}")):
        current.insert(0, item)
    for item in get_env_list(f"WEBLATE_REMOVE_{name}"):
        current.remove(item)
    return current


def get_env_credentials(
    name: str,
) -> Tuple[Optional[str], Optional[str], Dict[str, Dict[str, str]]]:
    """Parses VCS integration credentials."""
    username = os.environ.get(f"WEBLATE_{name}_USERNAME")
    token = os.environ.get(f"WEBLATE_{name}_TOKEN")
    host = os.environ.get(f"WEBLATE_{name}_HOST")

    if host:
        return None, None, {host: {"username": username, "token": token}}
    return username, token, {}
