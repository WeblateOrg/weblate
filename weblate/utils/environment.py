# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from django.core.exceptions import ImproperlyConfigured


def get_env_str(
    name: str,
    default: str | None = None,
    required: bool = False,
    fallback_name: str | None = None,
) -> str:
    file_env = f"{name}_FILE"
    if filename := os.environ.get(file_env):
        try:
            result = Path(filename).read_text()
        except OSError as error:
            msg = f"Failed to open {filename} as specified by {file_env}: {error}"
            raise ImproperlyConfigured(msg) from error
    else:
        result = os.environ.get(
            name,
            default if not fallback_name else None,  # type: ignore[arg-type]
        )
    # Also allow files for fallback names.
    # The logic is as follows (if fallback is given):
    # 1) Try `_FILE` variant of `name` first.
    # 2) Try `name` directly but do not pass default to get `None` in case it does not exist.
    # 3) Try `_FILE` variant of `fallback_name`.
    # 4) Finally, try `fallback_name` directly, using the given default.
    # If after all these steps no value is found, but it is required => fail.
    if not result and fallback_name:
        result = get_env_str(
            fallback_name, default=default, required=False, fallback_name=None
        )
    if required and not result:
        msg = f"{name} has to be configured!"
        raise ImproperlyConfigured(msg)
    return result


def get_env_list_or_none(name: str) -> list[str] | None:
    """Get list from environment."""
    string_value = get_env_str(name)
    if string_value is not None:
        return string_value.split(",")
    return None


def get_env_list(name: str, default: list[str] | None = None) -> list[str]:
    """Get list from environment."""
    env_list = get_env_list_or_none(name)
    if env_list is not None:
        return env_list
    return default or []


def get_env_map_or_none(name: str) -> dict[str, str] | None:
    """
    Get mapping from environment.

    parses 'full_name:name,email:mail' into {'email': 'mail', 'full_name': 'name'}
    """
    parsed_list = get_env_list_or_none(name)
    if parsed_list is not None:
        return dict(e.split(":") for e in parsed_list)
    return None


def get_env_map(name: str, default: dict[str, str] | None = None) -> dict[str, str]:
    """
    Get mapping from environment.

    parses 'full_name:name,email:mail' into {'email': 'mail', 'full_name': 'name'}
    """
    env_map = get_env_map_or_none(name)
    if env_map is not None:
        return env_map
    return default or {}


def get_env_int_or_none(name: str) -> int | None:
    """Get integer value from environment."""
    string_value = get_env_str(name)
    if string_value is None:
        return None
    try:
        return int(string_value)
    except ValueError as error:
        msg = f"{name} is not an integer: {error}"
        raise ImproperlyConfigured(msg) from error


def get_env_int(name: str, default: int = 0) -> int:
    """Get integer value from environment."""
    env_int = get_env_int_or_none(name)
    if env_int is not None:
        return env_int
    return default


def get_env_float(name: str, default: float = 0.0) -> float:
    """Get float value from environment."""
    string_value = get_env_str(name)
    if string_value is None:
        return default
    try:
        return float(string_value)
    except ValueError as error:
        msg = f"{name} is not an float: {error}"
        raise ImproperlyConfigured(msg) from error


def get_env_bool(name: str, default: bool = False) -> bool:
    """Get boolean value from environment."""
    string_value = get_env_str(name)
    if string_value is None:
        return default
    true_values = {"true", "yes", "1"}
    return string_value.lower() in true_values


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
        try:
            return ast.literal_eval(found_env_credentials)
        except ValueError as error:
            msg = f"Could not parse {name}_CREDENTIALS: {error}"
            raise ImproperlyConfigured(msg) from error

    host = get_env_str(f"WEBLATE_{name}_HOST")
    username = get_env_str(f"WEBLATE_{name}_USERNAME", "")
    token = get_env_str(f"WEBLATE_{name}_TOKEN", "")
    organization = get_env_str(f"WEBLATE_{name}_ORGANIZATION")

    if not host:
        if username or token:
            msg = f"Incomplete {name}_CREDENTIALS configuration: missing WEBLATE_{name}_HOST"
            raise ImproperlyConfigured(msg)
        return {}

    credentials = {host: {"username": username, "token": token}}

    if organization is not None:
        credentials[host]["organization"] = organization

    return credentials


def get_env_ratelimit(name: str, default: str) -> str:
    value = get_env_str(name, default)

    # Taken from rest_framework.throttling.SimpleRateThrottle.parse_rate
    # it can not be imported here as that breaks config loading for
    # rest_framework

    try:
        num, period = value.split("/")
    except ValueError as error:
        msg = f"Could not parse {name}: {error}"
        raise ImproperlyConfigured(msg) from error
    if not num.isdigit():
        msg = f"Could not parse {name}: rate is not numeric: {num}"
        raise ImproperlyConfigured(msg)
    if period[0] not in {"s", "m", "h", "d"}:
        msg = f"Could not parse {name}: unknown period: {period}"
        raise ImproperlyConfigured(msg)

    return value


def url_quote_part(value: str) -> str:
    return quote(value, safe="")


def get_env_redis_url() -> str:
    # Get values from the environment
    redis_proto = "rediss" if get_env_bool("REDIS_TLS") else "redis"
    redis_host = url_quote_part(get_env_str("REDIS_HOST", "cache", required=True))
    redis_port = get_env_int("REDIS_PORT", 6379)
    redis_db = get_env_int("REDIS_DB", 1)
    redis_password = url_quote_part(get_env_str("REDIS_PASSWORD", ""))
    redis_user = url_quote_part(get_env_str("REDIS_USER", ""))

    # Build user/password part of the URL
    redis_user_password: str | None
    if redis_user and redis_password:
        redis_user_password = f"{redis_user}:{redis_password}@"
    elif redis_password:
        redis_user_password = f":{redis_password}@"
    elif redis_user:
        redis_user_password = f"{redis_user}@"
    else:
        redis_user_password = ""

    return f"{redis_proto}://{redis_user_password}{redis_host}:{redis_port}/{redis_db}"


def get_saml_idp() -> dict[str, Any] | None:
    idp_entity_id = get_env_str("WEBLATE_SAML_IDP_ENTITY_ID")
    if not idp_entity_id:
        return None
    # Identity Provider
    saml_idp = {
        "entity_id": idp_entity_id,
        "url": get_env_str("WEBLATE_SAML_IDP_URL"),
        "x509cert": get_env_str("WEBLATE_SAML_IDP_X509CERT"),
    }

    for field in (
        "attr_full_name",
        "attr_first_name",
        "attr_last_name",
        "attr_username",
        "attr_email",
        "attr_user_permanent_id",
    ):
        env_name = f"WEBLATE_SAML_ID_{field.upper()}"
        value = get_env_str(env_name)
        if value:
            saml_idp[field] = value

    return saml_idp
