# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from functools import cache
from importlib import import_module
from typing import TYPE_CHECKING

from weblate.utils.tracing import start_span

if TYPE_CHECKING:
    from weblate.trans.alerts.base import BaseAlert
    from weblate.trans.models.component import Component


ALERTS: dict[str, type[BaseAlert]] = {}
ALERTS_IMPORT: set[str] = set()


def register(cls: type[BaseAlert]) -> type[BaseAlert]:
    name = cls.__name__
    ALERTS[name] = cls
    if cls.on_import:
        ALERTS_IMPORT.add(name)
    return cls


@cache
def load_alerts() -> None:
    for module in (
        "weblate.trans.alerts.config",
        "weblate.trans.alerts.files",
        "weblate.trans.alerts.vcs",
        "weblate.trans.alerts.addons",
        "weblate.trans.alerts.community",
    ):
        import_module(module)


def get_alert_class(name: str) -> type[BaseAlert]:
    load_alerts()
    return ALERTS[name]


def get_import_alerts() -> set[str]:
    load_alerts()
    return ALERTS_IMPORT


def update_alerts(component: Component, alerts: set[str] | None = None) -> None:
    load_alerts()
    for name, alert in ALERTS.items():
        if alerts and name not in alerts:
            continue
        with start_span(op="alerts.update", name=f"ALERT {name}"):
            result = alert.check_component(component)
            if result is None:
                continue
            if isinstance(result, dict):
                component.add_alert(alert.__name__, **result)
            elif result:
                component.add_alert(alert.__name__)
            else:
                component.delete_alert(alert.__name__)
