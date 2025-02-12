# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

#
# Django settings for running testsuite
#

import os
import warnings
from tempfile import TemporaryDirectory

from weblate.settings_example import *  # noqa: F403

CI_DATABASE = os.environ.get("CI_DATABASE", "")

default_user = "weblate"
default_name = "weblate"
if CI_DATABASE in {"mysql", "mariadb"}:
    DATABASES["default"]["ENGINE"] = "django.db.backends.mysql"
    default_user = "root"
    DATABASES["default"]["OPTIONS"] = {
        "init_command": (
            "SET NAMES utf8mb4, "
            "wait_timeout=28800, "
            "default_storage_engine=INNODB, "
            'sql_mode="STRICT_TRANS_TABLES"'
        ),
        "charset": "utf8",
        "isolation_level": "read committed",
    }
elif CI_DATABASE == "postgresql":
    DATABASES["default"]["ENGINE"] = "django.db.backends.postgresql"
    default_user = "postgres"
else:
    if not CI_DATABASE:
        msg = "Missing CI_DATABASE configuration in the environment"
        raise ValueError(msg)
    msg = f"Not supported database: {CI_DATABASE}"
    raise ValueError(msg)

DATABASES["default"]["HOST"] = os.environ.get("CI_DB_HOST", "")
DATABASES["default"]["NAME"] = os.environ.get("CI_DB_NAME", default_name)
DATABASES["default"]["USER"] = os.environ.get("CI_DB_USER", default_user)
DATABASES["default"]["PASSWORD"] = os.environ.get("CI_DB_PASSWORD", "")
DATABASES["default"]["PORT"] = os.environ.get("CI_DB_PORT", "")

# Configure admins
ADMINS = (("Weblate test", "noreply@weblate.org"),)

# The secret key is needed for tests
SECRET_KEY = "secret key used for tests only"  # noqa: S105

SITE_DOMAIN = "example.com"
OTP_WEBAUTHN_RP_NAME = SITE_DOMAIN
OTP_WEBAUTHN_RP_ID = SITE_DOMAIN
OTP_WEBAUTHN_ALLOWED_ORIGINS = [f"https://{SITE_DOMAIN}"]

# Different root for test repos
if "CI_BASE_DIR" in os.environ:
    BASE_DIR = os.environ["CI_BASE_DIR"]
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data-test")

# Use random data directory when running in parallel
if "PYTEST_XDIST_TESTRUNUID" in os.environ:
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    DATA_DIR_TMP = TemporaryDirectory(dir=DATA_DIR, prefix="xdist-")
    DATA_DIR = DATA_DIR_TMP.name

CACHE_DIR = os.path.join(DATA_DIR, "cache")
MEDIA_ROOT = os.path.join(DATA_DIR, "media")
STATIC_ROOT = os.path.join(DATA_DIR, "static")
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_BACKEND = None

# Enable lazy stats for testing
STATS_LAZY = True

VCS_API_DELAY = 0
VCS_FILE_PROTOCOL = True

# Localize CDN addon
LOCALIZE_CDN_URL = "https://cdn.example.com/"
LOCALIZE_CDN_PATH = os.path.join(DATA_DIR, "l10n-cdn")

# Needed for makemessages, otherwise it does not discover all available locales
# and the -a parameter does not work
LOCALE_PATHS = [os.path.join(os.path.dirname(__file__), "locale")]

# Silent logging setup
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "formatters": {"simple": {"format": "%(levelname)s %(message)s"}},
    "handlers": {
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        "weblate": {"handlers": [], "level": "ERROR"},
        "social": {"handlers": [], "level": "ERROR"},
    },
}

# Reset caches
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

if "CI_REDIS_HOST" in os.environ:
    CACHES["avatar"] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://{}:{}/0".format(
            os.environ["CI_REDIS_HOST"], os.environ.get("CI_REDIS_PORT", "6379")
        ),
    }

# Selenium can not clear HttpOnly cookies in MSIE
SESSION_COOKIE_HTTPONLY = False

# Use database backed sessions for transaction consistency in tests
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Test optional apps as well
INSTALLED_APPS += ("weblate.billing", "weblate.legal")

# Test GitHub auth
AUTHENTICATION_BACKENDS = (
    "social_core.backends.email.EmailAuth",
    "social_core.backends.github.GithubOAuth2",
    "weblate.accounts.auth.WeblateUserBackend",
)

# Disable random admin checks trigger
BACKGROUND_ADMIN_CHECKS = False

# Use weak password hasher for testing
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Let the testsuite fail on timezone issues
warnings.filterwarnings(
    "error",
    r"DateTimeField .* received a naive datetime",
    RuntimeWarning,
    r"django\.db\.models\.fields",
)
