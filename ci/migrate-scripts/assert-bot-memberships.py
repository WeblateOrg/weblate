# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assert bot memberships after cleanup migration."""

from weblate.auth.models import User

project_token = User.objects.get(username="bot-test-migration")
project_token_groups = set(
    project_token.groups.values_list("name", "defining_project__slug")
)
expected_project_token_groups = {("Administration", "test")}
assert project_token_groups == expected_project_token_groups, (
    f"Unexpected project token memberships: expected "
    f"{expected_project_token_groups!r}, got {project_token_groups!r}"
)

internal_bot = User.objects.get(username="weblate:migration")
internal_bot_groups = set(internal_bot.groups.values_list("name", flat=True))
assert not internal_bot_groups, (
    f"Unexpected internal bot memberships: got {internal_bot_groups!r}"
)

custom_bot = User.objects.get(username="custom-migration-bot")
custom_bot_groups = set(custom_bot.groups.values_list("name", flat=True))
expected_custom_bot_groups = {
    "Administration",
    "Users",
    "Viewers",
}
assert expected_custom_bot_groups <= custom_bot_groups, (
    f"Missing custom bot memberships: expected at least "
    f"{expected_custom_bot_groups!r}, got {custom_bot_groups!r}"
)

human = User.objects.get(username="migration-human")
human_groups = set(human.groups.values_list("name", flat=True))
expected_human_groups = {"Users", "Viewers"}
assert human_groups == expected_human_groups, (
    f"Unexpected human memberships: expected {expected_human_groups!r}, "
    f"got {human_groups!r}"
)
