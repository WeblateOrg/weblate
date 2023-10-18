# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import errno
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import chain
from typing import NamedTuple

from celery.exceptions import TimeoutError
from dateutil.parser import parse
from django.conf import settings
from django.core.cache import cache
from django.core.checks import Critical, Error, Info
from django.core.mail import get_connection
from django.db import DatabaseError
from django.utils import timezone
from packaging.version import Version

from weblate.utils.celery import get_queue_stats
from weblate.utils.data import data_dir
from weblate.utils.db import using_postgresql
from weblate.utils.docs import get_doc_url
from weblate.utils.site import check_domain, get_site_domain
from weblate.utils.version import VERSION_BASE

GOOD_CACHE = {"MemcachedCache", "PyLibMCCache", "DatabaseCache", "RedisCache"}
DEFAULT_MAILS = {
    "root@localhost",
    "webmaster@localhost",
    "noreply@example.com",
    "weblate@example.com",
}
DEFAULT_SECRET_KEYS = {
    "jm8fqjlg+5!#xu%e-oh#7!$aa7!6avf7ud*_v=chdrb9qdco6(",
    "secret key used for tests only",
}
DOC_LINKS = {
    "security.W001": ("admin/upgdade", "up-3-1"),
    "security.W002": ("admin/upgdade", "up-3-1"),
    "security.W003": ("admin/upgdade", "up-3-1"),
    "security.W004": ("admin/install", "production-ssl"),
    "security.W005": ("admin/install", "production-ssl"),
    "security.W006": ("admin/upgdade", "up-3-1"),
    "security.W007": ("admin/upgdade", "up-3-1"),
    "security.W008": ("admin/install", "production-ssl"),
    "security.W009": ("admin/install", "production-secret"),
    "security.W010": ("admin/install", "production-ssl"),
    "security.W011": ("admin/install", "production-ssl"),
    "security.W012": ("admin/install", "production-ssl"),
    "security.W018": ("admin/install", "production-debug"),
    "security.W019": ("admin/upgdade", "up-3-1"),
    "security.W020": ("admin/install", "production-hosts"),
    "security.W021": ("admin/install", "production-ssl"),
    "weblate.E002": ("admin/install", "file-permissions"),
    "weblate.E003": ("admin/install", "out-mail"),
    "weblate.E005": ("admin/install", "celery"),
    "weblate.E006": ("admin/install", "production-database"),
    "weblate.E007": ("admin/install", "production-cache"),
    "weblate.E008": ("admin/install", "production-cache-avatar"),
    "weblate.E009": ("admin/install", "celery"),
    "weblate.E011": ("admin/install", "production-admins"),
    "weblate.E012": ("admin/install", "production-email"),
    "weblate.E013": ("admin/install", "production-email"),
    "weblate.E014": ("admin/install", "production-secret"),
    "weblate.E015": ("admin/install", "production-hosts"),
    "weblate.E017": ("admin/install", "production-site"),
    "weblate.E018": ("admin/optionals", "avatars"),
    "weblate.E019": ("admin/install", "celery"),
    "weblate.E020": ("admin/install", "celery"),
    "weblate.I021": ("admin/install", "collecting-errors"),
    "weblate.E022": ("admin/optionals", "git-exporter"),
    "weblate.C023": ("admin/install", "production-encoding"),
    "weblate.C024": ("admin/install", "pangocairo"),
    "weblate.W025": ("admin/install", "optional-deps"),
    "weblate.E026": ("admin/install", "celery"),
    "weblate.E027": ("admin/install", "file-permissions"),
    "weblate.I028": ("admin/backup",),
    "weblate.C029": ("admin/backup",),
    "weblate.C030": ("admin/install", "celery"),
    "weblate.I031": ("admin/upgrade",),
    "weblate.C031": ("admin/upgrade",),
    "weblate.C032": ("admin/install",),
    "weblate.W033": ("vcs",),
    "weblate.E034": ("admin/install", "celery"),
    "weblate.C035": ("vcs",),
    "weblate.C036": ("admin/optionals", "gpg-sign"),
    "weblate.C037": ("admin/install", "production-database"),
    "weblate.C038": ("admin/install", "production-database"),
    "weblate.W039": ("admin/machine",),
    "weblate.C040": ("vcs",),
}


def check_doc_link(docid, strict=False):
    while docid.count(".") > 1:
        docid = docid.rsplit(".", 1)[0]
    try:
        return get_doc_url(*DOC_LINKS[docid])
    except KeyError:
        if strict:
            raise
        return None


def weblate_check(id, message, cls=Critical):
    """Returns Django check instance."""
    return cls(message, hint=check_doc_link(id), id=id)


def check_mail_connection(app_configs, **kwargs):
    errors = []
    try:
        connection = get_connection(timeout=5)
        connection.open()
        connection.close()
    except Exception as error:
        message = "Cannot send e-mail ({}), please check EMAIL_* settings."
        errors.append(weblate_check("weblate.E003", message.format(error)))

    return errors


def is_celery_queue_long():
    """
    Checks whether celery queue is too long.

    It does trigger if it is too long for at least one hour. This way peaks are
    filtered out, and no warning need be issued for big operations (for example
    site-wide autotranslation).
    """
    from weblate.trans.models import Translation

    cache_key = "celery_queue_stats"
    queues_data = cache.get(cache_key, {})

    # Hours since epoch
    current_hour = int(time.monotonic() / 3600)
    test_hour = current_hour - 1

    # Fetch current stats
    stats = get_queue_stats()

    # Update counters
    if current_hour not in queues_data:
        # Delete stale items
        for key in list(queues_data.keys()):
            if key < test_hour:
                del queues_data[key]
        # Add current one
        queues_data[current_hour] = stats

        # Store to cache
        cache.set(cache_key, queues_data, 7200)

    # Do not fire if we do not have counts for two hours ago
    if test_hour not in queues_data:
        return False

    # Check if any queue got bigger
    base = queues_data[test_hour]
    thresholds = defaultdict(lambda: 50)
    # Set the limit to avoid trigger on auto-translating all components
    # nightly.
    thresholds["translate"] = max(1000, Translation.objects.count() / 30)
    return any(
        stat > thresholds[key] and base.get(key, 0) > thresholds[key]
        for key, stat in stats.items()
    )


def check_celery(app_configs, **kwargs):
    # Import this lazily to avoid evaluating settings too early
    from weblate.utils.tasks import ping

    errors = []
    if settings.CELERY_TASK_ALWAYS_EAGER:
        errors.append(
            weblate_check(
                "weblate.E005", "Celery is configured in the eager mode", Error
            )
        )
    elif settings.CELERY_BROKER_URL == "memory://":
        errors.append(
            weblate_check(
                "weblate.E026", "Celery is configured to store queue in local memory"
            )
        )
    else:
        if is_celery_queue_long():
            errors.append(
                weblate_check(
                    "weblate.E009",
                    "The Celery tasks queue is too long, either the worker "
                    "is not running, or is too slow.",
                )
            )

        start = time.monotonic()
        result = ping.delay()
        try:
            pong = result.get(timeout=10, disable_sync_subtasks=False)
            cache.set("celery_latency", round(1000 * (time.monotonic() - start)))
            current = ping()
            # Check for outdated Celery running different version of configuration
            if current != pong:
                if pong is None:
                    # Celery runs Weblate 4.0 or older
                    differing = ["version"]
                else:
                    differing = [
                        key
                        for key, value in current.items()
                        if key not in pong or value != pong[key]
                    ]
                errors.append(
                    weblate_check(
                        "weblate.E034",
                        "The Celery process is outdated or misconfigured."
                        " Following items differ: {}".format(", ".join(differing)),
                    )
                )
        except TimeoutError:
            errors.append(
                weblate_check(
                    "weblate.E019",
                    "The Celery does not process tasks, or is too slow "
                    "in processing them.",
                )
            )
        except NotImplementedError:
            errors.append(
                weblate_check(
                    "weblate.E020",
                    "The Celery is not configured to store results, "
                    "CELERY_RESULT_BACKEND is probably not set.",
                )
            )

    heartbeat = cache.get("celery_heartbeat")
    loaded = cache.get("celery_loaded")
    now = time.monotonic()
    if loaded and now - loaded > 60 and (not heartbeat or now - heartbeat > 600):
        errors.append(
            weblate_check(
                "weblate.C030",
                "The Celery beat scheduler is not executing periodic tasks "
                "in a timely manner.",
            )
        )

    return errors


def measure_database_latency():
    from weblate.trans.models import Project

    start = time.monotonic()
    Project.objects.exists()
    return round(1000 * (time.monotonic() - start))


def measure_cache_latency():
    start = time.monotonic()
    cache.get("celery_loaded")
    return round(1000 * (time.monotonic() - start))


def check_database(app_configs, **kwargs):
    errors = []
    if not using_postgresql():
        errors.append(
            weblate_check(
                "weblate.E006",
                "Weblate performs best with PostgreSQL, consider migrating to it.",
                Info,
            )
        )

    try:
        delta = measure_database_latency()
        if delta > 100:
            errors.append(
                weblate_check(
                    "weblate.C038",
                    f"The database seems slow, the query took {delta} milliseconds",
                )
            )

    except DatabaseError as error:
        errors.append(
            weblate_check(
                "weblate.C037",
                f"Could not connect to the database: {error}",
            )
        )

    return errors


def check_cache(app_configs, **kwargs):
    """Check for sane caching."""
    errors = []

    cache_backend = settings.CACHES["default"]["BACKEND"].split(".")[-1]
    if cache_backend not in GOOD_CACHE:
        errors.append(
            weblate_check(
                "weblate.E007",
                "The configured cache back-end will lead to serious "
                "performance or consistency issues.",
            )
        )

    if settings.ENABLE_AVATARS and "avatar" not in settings.CACHES:
        errors.append(
            weblate_check(
                "weblate.E008",
                "Please set up separate avatar caching to reduce pressure "
                "on the default cache.",
                Error,
            )
        )

    return errors


def check_settings(app_configs, **kwargs):
    """Check for sane settings."""
    errors = []

    if not settings.ADMINS or any(x[1] in DEFAULT_MAILS for x in settings.ADMINS):
        errors.append(
            weblate_check(
                "weblate.E011",
                "E-mail addresses for site admins is misconfigured",
                Error,
            )
        )

    if settings.SERVER_EMAIL in DEFAULT_MAILS:
        errors.append(
            weblate_check(
                "weblate.E012",
                "The server e-mail address should be changed from its default value",
            )
        )
    if settings.DEFAULT_FROM_EMAIL in DEFAULT_MAILS:
        errors.append(
            weblate_check(
                "weblate.E013",
                'The "From" e-mail address should be changed from its default value',
            )
        )

    if settings.SECRET_KEY in DEFAULT_SECRET_KEYS:
        errors.append(
            weblate_check(
                "weblate.E014",
                "The cookie secret key should be changed from its default value",
            )
        )

    if not settings.ALLOWED_HOSTS:
        errors.append(weblate_check("weblate.E015", "No allowed hosts are set up"))
    return errors


def check_data_writable(app_configs=None, **kwargs):
    """Check we can write to data dir."""
    errors = []
    if not settings.DATA_DIR:
        return [
            weblate_check(
                "weblate.E002",
                "DATA_DIR is not configured.",
            )
        ]
    dirs = [
        settings.DATA_DIR,
        data_dir("home"),
        data_dir("ssh"),
        data_dir("vcs"),
        data_dir("backups"),
        data_dir("fonts"),
        data_dir("cache", "fonts"),
    ]
    message = "Path {} is not writable, check your DATA_DIR settings."
    for path in dirs:
        if not os.path.exists(path):
            os.makedirs(path)
        elif not os.access(path, os.W_OK):
            errors.append(weblate_check("weblate.E002", message.format(path)))

    return errors


def check_site(app_configs, **kwargs):
    errors = []
    if not check_domain(get_site_domain()):
        errors.append(weblate_check("weblate.E017", "Correct the site domain"))
    return errors


def check_perms(app_configs=None, **kwargs):
    """Check that the data dir can be written to."""
    if not settings.DATA_DIR:
        return []
    start = time.monotonic()
    errors = []
    uid = os.getuid()
    message = "The path {} is owned by a different user, check your DATA_DIR settings."
    for dirpath, dirnames, filenames in os.walk(settings.DATA_DIR):
        for name in chain(dirnames, filenames):
            # Skip toplevel lost+found dir, that one is typically owned by root
            # on filesystem toplevel directory. Also skip settings-override.py
            # used in the Docker container as that one is typically bind mouted
            # with different permissions (and Weblate is not expected to write
            # to it).
            if dirpath == settings.DATA_DIR and name in (
                "lost+found",
                "settings-override.py",
            ):
                continue
            path = os.path.join(dirpath, name)
            try:
                stat = os.lstat(path)
            except OSError as error:
                # File was removed meanwhile
                if error.errno == errno.ENOENT:
                    continue
                raise
            if stat.st_uid != uid:
                errors.append(weblate_check("weblate.E027", message.format(path)))
        if time.monotonic() - start > 15:
            break

    return errors


def check_errors(app_configs=None, **kwargs):
    """Check that error collection is configured."""
    if hasattr(settings, "ROLLBAR") or settings.SENTRY_DSN:
        return []
    return [
        weblate_check(
            "weblate.I021",
            "Error collection is not set up, "
            "it is highly recommended for production use",
            Info,
        )
    ]


def check_encoding(app_configs=None, **kwargs):
    """Check that the encoding is UTF-8."""
    if sys.getfilesystemencoding() == "utf-8" and sys.getdefaultencoding() == "utf-8":
        return []
    return [
        weblate_check(
            "weblate.C023",
            "System encoding is not UTF-8, processing non-ASCII strings will break",
        )
    ]


def check_diskspace(app_configs=None, **kwargs):
    """Check free disk space."""
    if settings.DATA_DIR:
        stat = os.statvfs(settings.DATA_DIR)
        if stat.f_bavail * stat.f_bsize < 10000000:
            return [weblate_check("weblate.C032", "The disk is nearly full")]
    return []


# Python Package Index URL
PYPI = "https://pypi.org/pypi/weblate/json"

# Cache to store fetched PyPI version
CACHE_KEY = "weblate-version-check"


class Release(NamedTuple):
    version: str
    timestamp: datetime


def download_version_info():
    from weblate.utils.requests import request

    response = request("get", PYPI)
    result = []
    for version, info in response.json()["releases"].items():
        if not info:
            continue
        result.append(Release(version, parse(info[0]["upload_time_iso_8601"])))
    return sorted(result, key=lambda x: x[1], reverse=True)


def flush_version_cache():
    cache.delete(CACHE_KEY)


def get_version_info():
    result = cache.get(CACHE_KEY)
    if not result:
        result = download_version_info()
        cache.set(CACHE_KEY, result, 86400)
    return result


def get_latest_version():
    return get_version_info()[0]


def check_version(app_configs=None, **kwargs):
    try:
        latest = get_latest_version()
    except (ValueError, OSError):
        return []
    if Version(latest.version) > Version(VERSION_BASE):
        # With release every two months, this gets triggered after three releases
        if latest.timestamp + timedelta(days=180) < timezone.now():
            return [
                weblate_check(
                    "weblate.C031",
                    "You Weblate version is outdated, please upgrade to {}.".format(
                        latest.version
                    ),
                )
            ]
        return [
            weblate_check(
                "weblate.I031",
                f"New Weblate version is available, please upgrade to {latest.version}.",
                Info,
            )
        ]
    return []
