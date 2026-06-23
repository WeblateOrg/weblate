# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations

FEDORA_MESSAGING_ADDON = "weblate.fedora_messaging.publish"


def migrate_fedora_messaging_amqp_url(apps, _schema_editor) -> None:
    Addon = apps.get_model("addons", "Addon")

    for addon in Addon.objects.filter(name=FEDORA_MESSAGING_ADDON):
        configuration = dict(addon.configuration or {})
        original = configuration.copy()

        if "amqp_url" not in configuration:
            amqp_host = configuration.get("amqp_host")
            if amqp_host:
                amqp_scheme = "amqps" if configuration.get("amqp_ssl") else "amqp"
                configuration["amqp_url"] = (
                    f"{amqp_scheme}://{amqp_host}?connection_attempts=3&retry_delay=5"
                )

        configuration.pop("amqp_host", None)
        configuration.pop("amqp_ssl", None)

        if configuration != original:
            Addon.objects.filter(pk=addon.pk).update(configuration=configuration)


class Migration(migrations.Migration):
    dependencies = [
        ("addons", "0020_remove_obsolete_cleanup_tasks"),
    ]

    operations = [
        migrations.RunPython(
            migrate_fedora_messaging_amqp_url,
            migrations.RunPython.noop,
        ),
    ]
