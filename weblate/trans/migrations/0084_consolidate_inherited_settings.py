# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.conf import settings
from django.db import migrations

INHERITABLE_COMPONENT_SETTINGS = (
    "license",
    "agreement",
    "new_lang",
    "language_code_style",
    "secondary_language",
    "commit_message",
    "add_message",
    "delete_message",
    "merge_message",
    "addon_message",
    "pull_message",
)


def value_field(field: str) -> str:
    if field == "secondary_language":
        return "secondary_language_id"
    return field


def inherit_field(field: str) -> str:
    return f"inherit_{field}"


def get_value(obj, field: str):
    return getattr(obj, value_field(field))


def set_value(obj, field: str, value) -> None:
    setattr(obj, value_field(field), value)


def split_flags(flags: str) -> list[str]:
    return [flag.strip() for flag in flags.split(",") if flag.strip()]


def merge_flags(*values: str) -> str:
    result: list[str] = []
    for value in values:
        for flag in split_flags(value):
            if flag not in result:
                result.append(flag)
    return ", ".join(result)


def promote_project_agreements(contributor_agreement, project, component_ids) -> None:
    if not component_ids:
        return
    accepted_users = (
        contributor_agreement.objects.filter(component_id__in=component_ids)
        .values_list("user_id", flat=True)
        .distinct()
    )
    existing = set(
        contributor_agreement.objects.filter(project_id=project.pk).values_list(
            "user_id", flat=True
        )
    )
    contributor_agreement.objects.bulk_create(
        [
            contributor_agreement(user_id=user_id, project_id=project.pk)
            for user_id in accepted_users
            if user_id not in existing
        ],
        ignore_conflicts=True,
    )


def promote_workspace_agreements(contributor_agreement, workspace, project_ids) -> None:
    if not project_ids:
        return
    accepted_users = (
        contributor_agreement.objects.filter(project_id__in=project_ids)
        .values_list("user_id", flat=True)
        .distinct()
    )
    existing = set(
        contributor_agreement.objects.filter(workspace_id=workspace.pk).values_list(
            "user_id", flat=True
        )
    )
    contributor_agreement.objects.bulk_create(
        [
            contributor_agreement(user_id=user_id, workspace_id=workspace.pk)
            for user_id in accepted_users
            if user_id not in existing
        ],
        ignore_conflicts=True,
    )


def consolidate_component_settings(apps, schema_editor) -> None:
    Project = apps.get_model("trans", "Project")
    Component = apps.get_model("trans", "Component")
    ContributorAgreement = apps.get_model("trans", "ContributorAgreement")

    project_updates = {}
    component_updates = {}
    component_update_fields = {
        "check_flags",
        *(inherit_field(field) for field in INHERITABLE_COMPONENT_SETTINGS),
    }
    project_update_fields = {"check_flags", *INHERITABLE_COMPONENT_SETTINGS}

    for project in Project.objects.all().iterator():
        components = list(Component.objects.filter(project_id=project.pk))
        if not components:
            continue

        for field in INHERITABLE_COMPONENT_SETTINGS:
            values = {get_value(component, field) for component in components}
            if len(values) == 1:
                value = values.pop()
                set_value(project, field, value)
                project_updates[project.pk] = project
                if field == "agreement" and value:
                    promote_project_agreements(
                        ContributorAgreement,
                        project,
                        [component.pk for component in components],
                    )
                inherit = True
            else:
                inherit = False

            inherit_name = inherit_field(field)
            for component in components:
                setattr(component, inherit_name, inherit)
                component_updates[component.pk] = component

        flag_values = {component.check_flags for component in components}
        if len(flag_values) == 1:
            common_flags = flag_values.pop()
            if common_flags:
                project.check_flags = merge_flags(project.check_flags, common_flags)
                project_updates[project.pk] = project
                for component in components:
                    component.check_flags = ""
                    component_updates[component.pk] = component

    if project_updates:
        Project.objects.bulk_update(
            project_updates.values(), sorted(project_update_fields), batch_size=1000
        )
    if component_updates:
        Component.objects.bulk_update(
            component_updates.values(),
            sorted(component_update_fields),
            batch_size=1000,
        )


def consolidate_workspace_settings(apps, schema_editor) -> None:
    Project = apps.get_model("trans", "Project")
    Workspace = apps.get_model("workspaces", "Workspace")
    ContributorAgreement = apps.get_model("trans", "ContributorAgreement")

    workspace_updates = {}
    project_updates = {}
    workspace_update_fields = {"check_flags", *INHERITABLE_COMPONENT_SETTINGS}
    project_update_fields = {
        "check_flags",
        *(inherit_field(field) for field in INHERITABLE_COMPONENT_SETTINGS),
    }

    Project.objects.filter(workspace_id__isnull=True).update(
        **{inherit_field(field): False for field in INHERITABLE_COMPONENT_SETTINGS}
    )

    for workspace in Workspace.objects.all().iterator():
        projects = list(Project.objects.filter(workspace_id=workspace.pk))
        if not projects:
            continue

        for field in INHERITABLE_COMPONENT_SETTINGS:
            values = {get_value(project, field) for project in projects}
            if len(values) == 1:
                value = values.pop()
                set_value(workspace, field, value)
                workspace_updates[workspace.pk] = workspace
                if field == "agreement" and value:
                    promote_workspace_agreements(
                        ContributorAgreement,
                        workspace,
                        [project.pk for project in projects],
                    )
                inherit = True
            else:
                inherit = False

            inherit_name = inherit_field(field)
            for project in projects:
                setattr(project, inherit_name, inherit)
                project_updates[project.pk] = project

        flag_values = {project.check_flags for project in projects}
        if len(flag_values) == 1:
            common_flags = flag_values.pop()
            if common_flags:
                workspace.check_flags = merge_flags(workspace.check_flags, common_flags)
                workspace_updates[workspace.pk] = workspace
                for project in projects:
                    project.check_flags = ""
                    project_updates[project.pk] = project

    if workspace_updates:
        Workspace.objects.bulk_update(
            workspace_updates.values(),
            sorted(workspace_update_fields),
            batch_size=1000,
        )
    if project_updates:
        Project.objects.bulk_update(
            project_updates.values(), sorted(project_update_fields), batch_size=1000
        )


def consolidate_inherited_settings(apps, schema_editor) -> None:
    consolidate_component_settings(apps, schema_editor)
    consolidate_workspace_settings(apps, schema_editor)


def get_dependencies() -> list[tuple[str, str]]:
    dependencies = [
        ("trans", "0083_alter_contributoragreement_unique_together_and_more"),
        ("workspaces", "0002_workspace_add_message_workspace_addon_message_and_more"),
    ]
    if "weblate.billing" in settings.INSTALLED_APPS:
        dependencies.append(("billing", "0011_workspace"))
    return dependencies


class Migration(migrations.Migration):
    dependencies = get_dependencies()

    operations = [
        migrations.RunPython(consolidate_inherited_settings, migrations.RunPython.noop),
    ]
