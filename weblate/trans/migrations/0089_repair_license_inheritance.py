# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict

from django.db import migrations

PROJECT_FALLBACK_LICENSES = {"", "proprietary"}
IGNORED_COMPONENT_LICENSES = PROJECT_FALLBACK_LICENSES


def get_most_common_component_licenses(component) -> dict[int, str]:
    stats: dict[int, dict[str, list[int]]] = defaultdict(dict)
    for component_id, project_id, license_code in (
        component.objects.exclude(license__in=IGNORED_COMPONENT_LICENSES)
        .order_by("project_id", "id")
        .values_list("id", "project_id", "license")
        .iterator(chunk_size=2000)
    ):
        project_stats = stats[project_id]
        if license_code not in project_stats:
            project_stats[license_code] = [0, component_id]
        project_stats[license_code][0] += 1

    return {
        project_id: max(
            project_stats.items(),
            key=lambda item: (item[1][0], -item[1][1]),
        )[0]
        for project_id, project_stats in stats.items()
    }


def repair_project_licenses(project, component) -> None:
    common_licenses = get_most_common_component_licenses(component)
    project_updates = []

    for item in (
        project.objects.filter(id__in=common_licenses)
        .only("id", "license", "inherit_license")
        .iterator(chunk_size=2000)
    ):
        if item.license not in PROJECT_FALLBACK_LICENSES:
            continue
        item.license = common_licenses[item.pk]
        item.inherit_license = False
        project_updates.append(item)

    if project_updates:
        project.objects.bulk_update(
            project_updates, ("license", "inherit_license"), batch_size=1000
        )


def repair_workspace_licenses(project, workspace) -> None:
    workspace_licenses: dict[int, str] = {}
    for workspace_id, license_code in (
        project.objects.filter(workspace_id__isnull=False)
        .exclude(license="")
        .order_by("workspace_id", "id")
        .values_list("workspace_id", "license")
        .iterator(chunk_size=2000)
    ):
        workspace_licenses.setdefault(workspace_id, license_code)

    workspace_updates = []
    for item in (
        workspace.objects.filter(
            id__in=workspace_licenses, license__in=PROJECT_FALLBACK_LICENSES
        )
        .only("id", "license")
        .iterator(chunk_size=2000)
    ):
        license_code = workspace_licenses[item.pk]
        if item.license == license_code:
            continue
        item.license = license_code
        workspace_updates.append(item)

    if workspace_updates:
        workspace.objects.bulk_update(workspace_updates, ("license",), batch_size=1000)


def repair_license_inheritance(apps, schema_editor) -> None:
    Component = apps.get_model("trans", "Component")
    Project = apps.get_model("trans", "Project")
    Workspace = apps.get_model("workspaces", "Workspace")

    repair_project_licenses(Project, Component)
    repair_workspace_licenses(Project, Workspace)


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0088_change_workspace_backfill"),
    ]

    operations = [
        migrations.RunPython(repair_license_inheritance, migrations.RunPython.noop),
    ]
