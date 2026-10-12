# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.apps import apps

Setting = apps.get_model("configuration", "Setting")
Project = apps.get_model("trans", "Project")

Setting.objects.update_or_create(
    category=2, name="openai", defaults={"value": {"key": "migration-site"}}
)
Setting.objects.update_or_create(
    category=2, name="deepl", defaults={"value": {"key": "migration-deepl"}}
)
project = Project.objects.get(slug="test")
project.machinery_settings = {
    "openai": {"key": "migration-project"},
    "deepl": None,
}
project.save(update_fields=["machinery_settings"])
Project.objects.create(
    slug="machinery-inherited", name="Machinery inherited", web="https://example.com/"
)
