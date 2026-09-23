# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Set up bot memberships for cleanup migration testing."""

from weblate.auth.models import Group, User
from weblate.trans.models import Project

project = Project.objects.get(slug="test")
administration = project.defined_groups.get(name="Administration")
users = Group.objects.get(name="Users", defining_project=None)
viewers = Group.objects.get(name="Viewers", defining_project=None)

project_token = User.objects.create_user(
    "bot-test-migration",
    "bot-test-migration@bots.noreply.weblate.org",
    full_name="Deleted User",
    is_bot=True,
)
project_token.groups.add(administration, users, viewers)

internal_bot = User.objects.create_user(
    "weblate:migration",
    "internal-migration@example.org",
    full_name="Migration internal bot",
    is_active=False,
    is_bot=True,
)
internal_bot.groups.add(administration, users, viewers)

custom_bot = User.objects.create_user(
    "custom-migration-bot",
    "custom-migration-bot@example.org",
    full_name="Migration custom bot",
    is_bot=True,
)
custom_bot.groups.add(administration, users, viewers)

human = User.objects.create_user(
    "migration-human",
    "migration-human@example.org",
    full_name="Migration human",
)
human.groups.add(users, viewers)
