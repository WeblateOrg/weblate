# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy


class LangConfig(AppConfig):
    name = "weblate.lang"
    label = "lang"
    verbose_name = gettext_lazy("Weblate languages")

    def ready(self) -> None:
        from weblate.lang.models import setup_lang

        post_migrate.connect(setup_lang, sender=self)
