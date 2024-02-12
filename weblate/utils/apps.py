# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import errno
import os
import sys
import time
from datetime import timedelta
from itertools import chain
from typing import cast

from celery.exceptions import TimeoutError
from django.apps import AppConfig
from django.conf import settings
from django.core.cache import cache
from django.core.checks import Error, Info, register
from django.core.mail import get_connection
from django.db import DatabaseError
from django.db.models import CharField, TextField
from django.db.models.functions import MD5, Lower
from django.db.models.lookups import Regex
from django.utils import timezone
from packaging.version import Version

from .celery import is_celery_queue_long
from .checks import weblate_check
from .data import data_dir
from .db import (
    MySQLSearchLookup,
    PostgreSQLRegexLookup,
    PostgreSQLSearchLookup,
    PostgreSQLSubstringLookup,
    measure_database_latency,
    using_postgresql,
)
from .errors import init_error_collection
from .site import check_domain, get_site_domain
from .version import VERSION_BASE, get_latest_version

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


@register(deploy=True)
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


@register(deploy=True)
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
    now = time.time()
    if loaded and now - loaded > 60 and (not heartbeat or now - heartbeat > 600):
        errors.append(
            weblate_check(
                "weblate.C030",
                "The Celery beat scheduler is not executing periodic tasks "
                "in a timely manner.",
            )
        )

    return errors


@register(deploy=True)
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


@register(deploy=True)
def check_cache(app_configs, **kwargs):
    """Check for sane caching."""
    errors = []

    cache_backend = cast(str, settings.CACHES["default"]["BACKEND"]).split(".")[-1]
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


@register(deploy=True)
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


@register
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


@register
def check_site(app_configs, **kwargs):
    errors = []
    if not check_domain(get_site_domain()):
        errors.append(weblate_check("weblate.E017", "Correct the site domain"))
    return errors


@register(deploy=True)
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


@register(deploy=True)
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


@register
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


@register(deploy=True)
def check_diskspace(app_configs=None, **kwargs):
    """Check free disk space."""
    if settings.DATA_DIR:
        stat = os.statvfs(settings.DATA_DIR)
        if stat.f_bavail * stat.f_bsize < 10000000:
            return [weblate_check("weblate.C032", "The disk is nearly full")]
    return []


@register(deploy=True)
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


class UtilsConfig(AppConfig):
    name = "weblate.utils"
    label = "utils"
    verbose_name = "Utils"

    def ready(self):
        super().ready()
        init_error_collection()

        if using_postgresql():
            lookups = [
                (PostgreSQLSearchLookup,),
                (PostgreSQLSubstringLookup,),
                (PostgreSQLRegexLookup, "trgm_regex"),
            ]
        else:
            lookups = [
                (MySQLSearchLookup,),
                (MySQLSearchLookup, "substring"),
                (Regex, "trgm_regex"),
            ]

        lookups.append((MD5,))
        lookups.append((Lower,))

        for lookup in lookups:
            CharField.register_lookup(*lookup)
            TextField.register_lookup(*lookup)
