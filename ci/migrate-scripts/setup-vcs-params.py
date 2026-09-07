# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.models import Component, Project

project = Project.objects.create(
    name="vcs-params-test-project",
    slug="vcs-params-test-project",
)
component1, component2 = Component.objects.bulk_create(
    [
        Component(
            name="vcs-params-force-push",
            slug="vcs-params-force-push",
            project=project,
            file_format="po",
            vcs="git-force-push",
        ),
        Component(
            name="vcs-params-plain-git",
            slug="vcs-params-plain-git",
            project=project,
            file_format="po",
            vcs="git",
        ),
    ]
)

assert component1.vcs == "git-force-push"
assert component2.vcs == "git"
