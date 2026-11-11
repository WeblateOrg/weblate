# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify repaired authority and credentials, including unaffected controls."""

from __future__ import annotations

from rest_framework.authtoken.models import Token

from weblate.auth.models import User

for name in ("orphan-sentinel", "orphan-normal", "orphan-inactive", "orphan-revoked"):
    user = User.objects.get(username=f"bot-repair-{name}")
    assert not user.is_active, name
    assert not user.has_usable_password(), name
    assert not Token.objects.filter(user=user).exists(), name
    assert not user.groups.exists(), name
    assert not user.administered_group_set.exists(), name
    assert user.full_name == (
        "Deleted User" if name.endswith("sentinel") else "Repair control"
    ), name
    assert user.auditlog_set.filter(activity="token-removed").count() == (
        0 if name == "orphan-revoked" else 1
    ), name

user = User.objects.get(username="bot-repair-live-sentinel")
assert user.is_active
assert user.has_usable_password()
assert Token.objects.get(user=user).key == "repair-live-sentinel"
assert set(user.groups.values_list("name", flat=True)) == {
    "Project token repair project"
}
assert set(user.administered_group_set.values_list("name", flat=True)) == {
    "Project token repair project"
}
assert not user.auditlog_set.filter(activity="token-removed").exists()

for username, is_active, token_key in (
    ("bot-repair-human", True, "repair-human"),
    ("repair-custom", True, "repair-custom"),
    ("weblate:repair-internal", False, "repair-internal"),
):
    user = User.objects.get(username=username)
    assert user.is_active == is_active, username
    assert user.has_usable_password(), username
    assert Token.objects.get(user=user).key == token_key, username
    assert set(user.groups.values_list("name", flat=True)) == {
        "Owners",
        "Project token repair global",
    }, username
    assert set(user.administered_group_set.values_list("name", flat=True)) == {
        "Owners",
        "Project token repair global",
        "Project token repair project",
    }, username
    assert not user.auditlog_set.filter(activity="token-removed").exists(), username
