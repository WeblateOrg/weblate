# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check the targeted cleanup against populated upgraded rows."""

from __future__ import annotations

from django.apps import apps

Component = apps.get_model("trans", "Component")
components = Component.objects.filter(project__slug="github-push-upgrade")
assert components.count() == 4
assert (
    list(components.filter(vcs="github-app").values_list("push", "push_branch"))
    == [("", "")] * 3
)
assert components.filter(
    vcs="git", push="https://example.org/repo.git", push_branch="translations"
).exists()
