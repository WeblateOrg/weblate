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


from appconf import AppConf
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from weblate.trans.models import Change
from weblate.utils.decorators import disable_for_loaddata


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

    RATELIMIT_TRIAL_ATTEMPTS = 1
    RATELIMIT_TRIAL_WINDOW = 60
    RATELIMIT_TRIAL_LOCKOUT = 600

    SENTRY_DSN = None
    SENTRY_SECURITY = None
    SENTRY_ENVIRONMENT = "devel"
    SENTRY_ORGANIZATION = "weblate"
    SENTRY_TOKEN = None
    SENTRY_PROJECTS = ["weblate"]
    SENTRY_EXTRA_ARGS = {}

    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_BROKER_URL = "memory://"

    DATABASE_BACKUP = "plain"

    HIDE_VERSION = False

    CSP_SCRIPT_SRC = []
    CSP_IMG_SRC = []
    CSP_CONNECT_SRC = []
    CSP_STYLE_SRC = []
    CSP_FONT_SRC = []

    class Meta:
        prefix = ""


@receiver(post_save, sender=Change)
@disable_for_loaddata
def update_source(sender, instance, created, **kwargs):
    if (
        not created
        or instance.action not in Change.ACTIONS_CONTENT
        or instance.translation is None
    ):
        return
    cache.set(
        f"last-content-change-{instance.translation.pk}",
        instance.pk,
        180 * 86400,
    )
