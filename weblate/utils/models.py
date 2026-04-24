# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# mypy: disable-error-code="var-annotated"

from __future__ import annotations

from typing import ClassVar

from appconf import AppConf

from weblate.utils.version_display import (
    VERSION_DISPLAY_HIDE,
    normalize_version_display,
)


class WeblateConf(AppConf):
    WEBLATE_GPG_IDENTITY = None
    WEBLATE_GPG_ALGO = "default"

    RATELIMIT_ATTEMPTS = 5
    RATELIMIT_WINDOW = 300
    RATELIMIT_LOCKOUT = 600

    RATELIMIT_SEARCH_ATTEMPTS = 30
    RATELIMIT_SEARCH_WINDOW = 60
    RATELIMIT_SEARCH_LOCKOUT = 60

    RATELIMIT_COMMENT_ATTEMPTS = 30
    RATELIMIT_COMMENT_WINDOW = 60

    RATELIMIT_TRANSLATE_ATTEMPTS = 30
    RATELIMIT_TRANSLATE_WINDOW = 60

    RATELIMIT_GLOSSARY_ATTEMPTS = 30
    RATELIMIT_GLOSSARY_WINDOW = 60

    RATELIMIT_LANGUAGE_ATTEMPTS = 2
    RATELIMIT_LANGUAGE_WINDOW = 300
    RATELIMIT_LANGUAGE_LOCKOUT = 600

    RATELIMIT_MESSAGE_ATTEMPTS = 2

    RATELIMIT_TRIAL_ATTEMPTS = 1
    RATELIMIT_TRIAL_WINDOW = 60
    RATELIMIT_TRIAL_LOCKOUT = 600

    RATELIMIT_PROJECT_ATTEMPTS = 5
    RATELIMIT_PROJECT_WINDOW = 600
    RATELIMIT_PROJECT_LOCKOUT = 600

    SENTRY_DSN = None
    SENTRY_SECURITY = None
    SENTRY_ENVIRONMENT = "devel"
    SENTRY_MONITOR_BEAT_TASKS = True
    SENTRY_TOKEN = None
    SENTRY_SEND_PII = False
    SENTRY_PROJECTS: ClassVar[list[str]] = ["weblate"]
    SENTRY_RELEASES_API_URL = (
        "https://sentry.io/api/0/organizations/4507304895905792/releases/"
    )
    SENTRY_EXTRA_ARGS: ClassVar[dict] = {}
    SENTRY_TRACES_SAMPLE_RATE = 0
    SENTRY_PROFILES_SAMPLE_RATE = 0

    ZAMMAD_URL = None

    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_BROKER_URL = "memory://"

    STATS_LAZY = False

    DATABASE_BACKUP = "plain"

    BORG_EXTRA_ARGS = None

    VERSION_DISPLAY = None
    HIDE_VERSION = False

    CSP_SCRIPT_SRC: ClassVar[list[str]] = []
    CSP_IMG_SRC: ClassVar[list[str]] = []
    CSP_CONNECT_SRC: ClassVar[list[str]] = []
    CSP_STYLE_SRC: ClassVar[list[str]] = []
    CSP_FONT_SRC: ClassVar[list[str]] = []
    CSP_FORM_SRC: ClassVar[list[str]] = []

    PROJECT_NAME_RESTRICT_RE = None
    PROJECT_WEB_RESTRICT_RE = None
    PROJECT_WEB_RESTRICT_HOST: ClassVar[set[str]] = {"localhost"}
    PROJECT_WEB_RESTRICT_ALLOWLIST: ClassVar[set[str]] = set()
    PROJECT_WEB_RESTRICT_NUMERIC = True
    PROJECT_WEB_RESTRICT_PRIVATE = True
    WEBHOOK_RESTRICT_PRIVATE = True
    WEBHOOK_PRIVATE_ALLOWLIST: ClassVar[list[str]] = []

    LOCALE_FILTER_FILES = True

    ALLOWED_ASSET_DOMAINS: ClassVar[list[str]] = ["*"]
    ALLOWED_MACHINERY_DOMAINS: ClassVar[list[str]] = []
    ALLOWED_ASSET_SIZE: ClassVar[int] = 10_000_000
    TRANSLATION_UPLOAD_MAX_SIZE: ClassVar[int] = 50_000_000
    COMPONENT_ZIP_UPLOAD_MAX_SIZE: ClassVar[int] = 50_000_000

    def configure(self):
        data = AppConf.configure(self).copy()
        data["VERSION_DISPLAY"] = normalize_version_display(
            data["VERSION_DISPLAY"], data["HIDE_VERSION"]
        )
        data["HIDE_VERSION"] = data["VERSION_DISPLAY"] == VERSION_DISPLAY_HIDE
        return data

    class Meta:
        prefix = ""
