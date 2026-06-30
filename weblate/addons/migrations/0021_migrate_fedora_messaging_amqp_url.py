# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.db import migrations

FEDORA_MESSAGING_ADDON = "weblate.fedora_messaging.publish"
DEFAULT_PUBLISH_TIMEOUT = 5
DEFAULT_CONNECTION_ATTEMPTS = 1
DEFAULT_RETRY_DELAY = 2


def parse_int(value, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_amqp_url(configuration: dict) -> None:
    amqp_url = configuration.get("amqp_url")
    if not amqp_url:
        return

    parsed = urlsplit(amqp_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    connection_attempts = query.pop("connection_attempts", None)
    retry_delay = query.pop("retry_delay", None)
    configuration["amqp_url"] = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )
    configuration.setdefault("publish_timeout", DEFAULT_PUBLISH_TIMEOUT)
    configuration.setdefault(
        "connection_attempts",
        parse_int(connection_attempts, DEFAULT_CONNECTION_ATTEMPTS),
    )
    configuration.setdefault("retry_delay", parse_int(retry_delay, DEFAULT_RETRY_DELAY))


def migrate_fedora_messaging_amqp_url(apps, _schema_editor) -> None:
    Addon = apps.get_model("addons", "Addon")

    for addon in Addon.objects.filter(name=FEDORA_MESSAGING_ADDON):
        configuration = dict(addon.configuration or {})
        original = configuration.copy()

        if "amqp_url" not in configuration:
            amqp_host = configuration.get("amqp_host")
            if amqp_host:
                amqp_scheme = "amqps" if configuration.get("amqp_ssl") else "amqp"
                configuration["amqp_url"] = f"{amqp_scheme}://{amqp_host}"

        normalize_amqp_url(configuration)

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
