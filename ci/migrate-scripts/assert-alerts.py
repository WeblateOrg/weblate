# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify populated alert lifecycle migration results after upgrading."""

from __future__ import annotations

from weblate.trans.models import Alert

alerts = Alert.objects.filter(component_id=1, details__migration_test=True)
assert alerts.count() == 19, "Migration test alerts were lost"
for alert in alerts:
    assert alert.details == {
        "migration_test": True,
        "error": "migration failure",
        "occurrences": [
            {"addon": "weblate.gettext.msgmerge", "addon_id": "123", "error": "failure"}
        ],
    }, f"Alert details changed: {alert.name}"
    assert alert.dismissed_by_id is None
    assert not alert.dismissal_reason
    if alert.name == "DuplicateString":
        assert alert.dismissed_at is None
        assert not alert.dismissal_fingerprint
    else:
        assert alert.dismissed_at is not None, f"Dismissal lost: {alert.name}"
        assert alert.dismissed_at >= alert.timestamp
        assert (
            alert.dismissal_fingerprint
            == alert.alert_class.get_dismissal_fingerprint(
                alert.component, alert.details
            )
        ), f"Dismissal context changed: {alert.name}"
