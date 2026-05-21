# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assertion for team membership through-model migration."""

from weblate.auth.models import TeamMembership, User

user = User.objects.get(username="membership-migrate")
membership = TeamMembership.objects.get(
    user=user, group__name="Translate", group__defining_project__slug="test"
)

assert user.groups.filter(pk=membership.group_id).exists(), (
    "Migrated team membership is not visible through user.groups"
)
assert not membership.limit_languages.exists(), (
    "Migrated team membership should not have language limits"
)
