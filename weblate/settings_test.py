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

#
# Django settings for running testsuite
#

import os
import warnings

from weblate.settings_example import *  # noqa

CI_DATABASE = os.environ.get("CI_DATABASE", "")

default_user = "weblate"
default_name = "weblate"
if CI_DATABASE in ("mysql", "mariadb"):
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
    raise ValueError(f"Not supported database: {CI_DATABASE}")

DATABASES["default"]["HOST"] = os.environ.get("CI_DB_HOST", "")
DATABASES["default"]["NAME"] = os.environ.get("CI_DB_NAME", default_name)
DATABASES["default"]["USER"] = os.environ.get("CI_DB_USER", default_user)
DATABASES["default"]["PASSWORD"] = os.environ.get("CI_DB_PASSWORD", "")
DATABASES["default"]["PORT"] = os.environ.get("CI_DB_PORT", "")

# Configure admins
ADMINS = (("Weblate test", "noreply@weblate.org"),)

# The secret key is needed for tests
SECRET_KEY = "secret key used for tests only"

SITE_DOMAIN = "example.com"

# Different root for test repos
if "CI_BASE_DIR" in os.environ:
    BASE_DIR = os.environ["CI_BASE_DIR"]
DATA_DIR = os.path.join(BASE_DIR, "data-test")
MEDIA_ROOT = os.path.join(DATA_DIR, "media")
STATIC_ROOT = os.path.join(DATA_DIR, "static")
CELERY_BEAT_SCHEDULE_FILENAME = os.path.join(DATA_DIR, "celery", "beat-schedule")
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_BACKEND = None

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

# Use weak password hasher in tests, there is no point in spending CPU time
# in hashing test passwords
PASSWORD_HASHERS = ["django.contrib.auth.hashers.CryptPasswordHasher"]

# Test optional apps as well
INSTALLED_APPS += ("weblate.billing", "weblate.legal")

# Test GitHub auth
AUTHENTICATION_BACKENDS = (
    "social_core.backends.email.EmailAuth",
    "social_core.backends.github.GithubOAuth2",
    "weblate.accounts.auth.WeblateUserBackend",
)

warnings.filterwarnings(
    "error",
    r"DateTimeField .* received a naive datetime",
    RuntimeWarning,
    r"django\.db\.models\.fields",
)

# Generate junit compatible XML for AppVeyor
if "APPVEYOR" in os.environ:
    TEST_RUNNER = "xmlrunner.extra.djangotestrunner.XMLTestRunner"
    TEST_OUTPUT_FILE_NAME = "junit.xml"
