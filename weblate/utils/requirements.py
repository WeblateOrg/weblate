# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
from importlib.metadata import PackageNotFoundError, metadata
from typing import TYPE_CHECKING, cast

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connection

import weblate.utils.version
from weblate.utils.cache import is_redis_cache
from weblate.utils.db import using_postgresql
from weblate.utils.errors import report_error
from weblate.vcs.git import GitRepository, GitWithGerritRepository, SubversionRepository
from weblate.vcs.mercurial import HgRepository

if TYPE_CHECKING:
    from django_redis.cache import RedisCache

REQUIRES = [
    "Django",
    "siphashc",
    "translate-toolkit",
    "lxml",
    "Pillow",
    "nh3",
    "python-dateutil",
    "social-auth-core",
    "social-auth-app-django",
    "django-crispy-forms",
    "oauthlib",
    "django-compressor",
    "djangorestframework",
    "django-filter",
    "django-appconf",
    "user-agents",
    "filelock",
    "rapidfuzz",
    "openpyxl",
    "celery",
    "django-celery-beat",
    "kombu",
    "translation-finder",
    "weblate-language-data",
    "html2text",
    "pycairo",
    "pygobject",
    "diff-match-patch",
    "requests",
    "django-redis",
    "hiredis",
    "sentry_sdk",
    "Cython",
    "mistletoe",
    "GitPython",
    "borgbackup",
    "pyparsing",
    "ahocorasick_rs",
    "charset-normalizer",
    "cyrtranslit",
    "drf_spectacular",
]

OPTIONAL = [
    "psycopg",
    "psycopg-binary",
    "phply",
    "ruamel.yaml",
    "tesserocr",
    "boto3",
    "aeidon",
    "iniparse",
    "mysqlclient",
    "google-cloud-translate",
    "openai",
]


def get_version_module(name, optional=False) -> tuple[str, str, str] | None:
    """
    Return module object.

    On error raises verbose exception with name and URL.
    """
    try:
        package = metadata(name)
    except PackageNotFoundError as exc:
        if optional:
            return None
        msg = f"Missing dependency {name}, please install using: pip install {name}"
        raise ImproperlyConfigured(msg) from exc
    url = package.get("Home-page")
    if url is None and (project_urls := package.get_all("Project-URL")):
        for project_url in project_urls:
            url_name, current_url = project_url.split(",", 1)
            if url_name.lower().strip() == "homepage":
                url = current_url.strip()
                break
    if url is None:
        url = f"https://pypi.org/project/{name}/"
    return (
        package["Name"],
        url,
        package["Version"],
    )


def get_optional_versions() -> list[tuple[str, str, str]]:
    """Return versions of optional modules."""
    result = []

    for name in OPTIONAL:
        module = get_version_module(name, True)
        if module is not None:
            result.append(module)

    if HgRepository.is_supported():
        result.append(
            ("Mercurial", "https://www.mercurial-scm.org/", HgRepository.get_version())
        )

    if SubversionRepository.is_supported():
        result.append(
            (
                "git-svn",
                "https://git-scm.com/docs/git-svn",
                SubversionRepository.get_version(),
            )
        )

    if GitWithGerritRepository.is_supported():
        result.append(
            (
                "git-review",
                "https://pypi.org/project/git-review/",
                GitWithGerritRepository.get_version(),
            )
        )

    return result


def get_versions() -> list[tuple[str, str, str]]:
    """Return list of used versions."""
    result: list[tuple[str, str, str]] = [
        module for name in REQUIRES if (module := get_version_module(name))
    ]

    result.append(("Python", "https://www.python.org/", sys.version.split()[0]))

    try:
        result.append(("Git", "https://git-scm.com/", GitRepository.get_version()))
    except OSError as exc:
        msg = "Could not run git, please install it."
        raise ImproperlyConfigured(msg) from exc

    return result


def get_db_version() -> tuple[str, str, str] | None:
    if using_postgresql():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SHOW server_version")
                version = cursor.fetchone()
        except (RuntimeError, DatabaseError):
            report_error("PostgreSQL version check")
            return None

        return (
            "PostgreSQL server",
            "https://www.postgresql.org/",
            version[0].split(" ")[0],
        )
    try:
        with connection.cursor() as cursor:
            version = cursor.connection.get_server_info()
    except (RuntimeError, DatabaseError):
        report_error("MySQL version check")
        return None
    return (
        f"{connection.display_name} sever",
        "https://mariadb.org/"
        if connection.mysql_is_mariadb  # type: ignore[attr-defined]
        else "https://www.mysql.com/",
        version.split("-", 1)[0],
    )


def get_cache_version() -> tuple[str, str, str] | None:
    if is_redis_cache():
        try:
            client_info = cast("RedisCache", cache).client.get_client().info()
        except RuntimeError:
            report_error("Redis version check")
            return None

        if version := client_info.get("valkey_version"):
            return ("Valkey server", "https://valkey.io/", version)
        if version := client_info.get("redis_version"):
            return ("Redis server", "https://redis.io/", version)

    return None


def get_db_cache_version() -> list[tuple[str, str, str]]:
    """Return the list of all the Database and Cache version."""
    result = []
    cache_version = get_cache_version()
    if cache_version:
        result.append(cache_version)
    db_version = get_db_version()
    if db_version:
        result.append(db_version)
    return result


def get_versions_list() -> list[tuple[str, str, str]]:
    """Return list with version information summary."""
    return [
        ("Weblate", "https://weblate.org/", weblate.utils.version.GIT_VERSION),
        *get_versions(),
        *get_optional_versions(),
        *get_db_cache_version(),
    ]
