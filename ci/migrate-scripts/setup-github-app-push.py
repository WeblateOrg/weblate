# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Seed invalid integration settings on the pre-upgrade schema."""

from __future__ import annotations

from django.apps import apps

Project = apps.get_model("trans", "Project")
Component = apps.get_model("trans", "Component")
project = Project.objects.bulk_create(
    [Project(name="GitHub push upgrade", slug="github-push-upgrade")]
)[0]
Component.objects.bulk_create(
    [
        Component(
            project=project,
            name=slug,
            slug=slug,
            vcs=vcs,
            file_format="po",
            repo="https://github.com/example/repo.git",
            push=push,
            push_branch=branch,
        )
        for slug, vcs, push, branch in (
            ("app", "github-app", "https://example.org/repo.git", "translations"),
            ("branch-only", "github-app", "", "translations"),
            ("clean", "github-app", "", ""),
            ("git", "git", "https://example.org/repo.git", "translations"),
        )
    ]
)
