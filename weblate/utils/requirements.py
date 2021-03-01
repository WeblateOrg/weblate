#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


import email.parser
import sys

import pkg_resources
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

import weblate.utils.version
from weblate.utils.db import using_postgresql
from weblate.utils.errors import report_error
from weblate.vcs.git import GitRepository, GitWithGerritRepository, SubversionRepository
from weblate.vcs.mercurial import HgRepository

REQUIRES = [
    "Django",
    "siphashc",
    "translate-toolkit",
    "lxml",
    "Pillow",
    "bleach",
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
    "setuptools",
    "jellyfish",
    "openpyxl",
    "celery",
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
    "misaka",
    "GitPython",
    "borgbackup",
    "pyparsing",
    "pyahocorasick",
]

OPTIONAL = [
    "psycopg2",
    "psycopg2-binary",
    "phply",
    "chardet",
    "ruamel.yaml",
    "tesserocr",
    "akismet",
    "boto3",
    "zeep",
    "aeidon",
    "iniparse",
    "mysqlclient",
]


def get_version_module(name, optional=False):
    """Return module object.

    On error raises verbose exception with name and URL.
    """
    try:
        dist = pkg_resources.get_distribution(name)
        metadata = email.parser.Parser().parsestr(dist.get_metadata(dist.PKG_INFO))
        return (
            name,
            metadata.get("Home-page"),
            pkg_resources.get_distribution(name).version,
        )
    except pkg_resources.DistributionNotFound:
        if optional:
            return None
        raise ImproperlyConfigured(
            "Missing dependency {0}, please install using: pip install {0}".format(name)
        )


def get_optional_versions():
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


def get_versions():
    """Return list of used versions."""
    result = [get_version_module(name) for name in REQUIRES]

    result.append(("Python", "https://www.python.org/", sys.version.split()[0]))

    try:
        result.append(("Git", "https://git-scm.com/", GitRepository.get_version()))
    except OSError:
        raise ImproperlyConfigured("Failed to run git, please install it.")

    return result


def get_db_version():
    if using_postgresql():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SHOW server_version")
                version = cursor.fetchone()
        except RuntimeError:
            report_error(cause="PostgreSQL version check")
            return None

        return (
            "PostgreSQL server",
            "https://www.postgresql.org/",
            version[0].split(" ")[0],
        )
    try:
        with connection.cursor() as cursor:
            version = cursor.connection.get_server_info()
    except RuntimeError:
        report_error(cause="MySQL version check")
        return None
    return (
        f"{connection.display_name} sever",
        "https://mariadb.org/"
        if connection.mysql_is_mariadb
        else "https://www.mysql.com/",
        version.split("-", 1)[0],
    )


def get_cache_version():
    if settings.CACHES["default"]["BACKEND"] == "django_redis.cache.RedisCache":
        try:
            version = cache.client.get_client().info()["redis_version"]
        except RuntimeError:
            report_error(cause="Redis version check")
            return None

        return ("Redis server", "https://redis.io/", version)

    return None


def get_db_cache_version():
    """Returns the list of all the Database and Cache version."""
    result = []
    cache_version = get_cache_version()
    if cache_version:
        result.append(cache_version)
    db_version = get_db_version()
    if db_version:
        result.append(db_version)
    return result


def get_versions_list():
    """Return list with version information summary."""
    return (
        [("Weblate", "https://weblate.org/", weblate.utils.version.GIT_VERSION)]
        + get_versions()
        + get_optional_versions()
        + get_db_cache_version()
    )
