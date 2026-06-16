# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

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


def get_category_depth(category, categories_by_id) -> int:
    depth = 0
    while category.category_id is not None:
        depth += 1
        category = categories_by_id[category.category_id]
    return depth


def promote_agreements(
    contributor_agreement, owner_filter: dict[str, int], components, child_categories
) -> None:
    accepted_users = set()
    component_ids = [component.pk for component in components]
    if component_ids:
        accepted_users.update(
            contributor_agreement.objects.filter(
                component_id__in=component_ids
            ).values_list("user_id", flat=True)
        )
    category_ids = [child.pk for child in child_categories]
    if category_ids:
        accepted_users.update(
            contributor_agreement.objects.filter(
                category_id__in=category_ids
            ).values_list("user_id", flat=True)
        )
    if not accepted_users:
        return

    existing = set(
        contributor_agreement.objects.filter(**owner_filter).values_list(
            "user_id", flat=True
        )
    )
    contributor_agreement.objects.bulk_create(
        [
            contributor_agreement(user_id=user_id, **owner_filter)
            for user_id in accepted_users
            if user_id not in existing
        ],
        ignore_conflicts=True,
    )


# ruff: ignore[complex-structure, too-many-locals]
def consolidate_category_settings(apps, schema_editor) -> None:
    Category = apps.get_model("trans", "Category")
    Component = apps.get_model("trans", "Component")
    ContributorAgreement = apps.get_model("trans", "ContributorAgreement")
    Project = apps.get_model("trans", "Project")
    Workspace = apps.get_model("workspaces", "Workspace")

    categories = list(Category.objects.all())
    categories_by_id = {category.pk: category for category in categories}
    projects_by_id = {project.pk: project for project in Project.objects.all()}
    workspaces_by_id = {
        workspace.pk: workspace for workspace in Workspace.objects.all()
    }
    components_by_category: dict[int, list] = {}
    for component in Component.objects.exclude(category_id=None):
        components_by_category.setdefault(component.category_id, []).append(component)
    categories_by_parent: dict[int, list] = {}
    for category in categories:
        if category.category_id is not None:
            categories_by_parent.setdefault(category.category_id, []).append(category)

    category_updates = {}
    component_updates = {}
    category_update_fields = {
        "check_flags",
        *INHERITABLE_COMPONENT_SETTINGS,
        *(inherit_field(field) for field in INHERITABLE_COMPONENT_SETTINGS),
    }
    component_update_fields = {
        "check_flags",
        *(inherit_field(field) for field in INHERITABLE_COMPONENT_SETTINGS),
    }
    effective_category_cache: dict[tuple[int, str], object] = {}
    effective_project_cache: dict[tuple[int, str], object] = {}

    def get_project_effective_setting(project, field: str):
        cache_key = (project.pk, field)
        if cache_key in effective_project_cache:
            return effective_project_cache[cache_key]
        if project.workspace_id is not None and getattr(
            project, inherit_field(field), False
        ):
            value = get_value(workspaces_by_id[project.workspace_id], field)
        else:
            value = get_value(project, field)
        effective_project_cache[cache_key] = value
        return value

    def get_category_effective_setting(category, field: str):
        cache_key = (category.pk, field)
        if cache_key in effective_category_cache:
            return effective_category_cache[cache_key]
        if getattr(category, inherit_field(field), False):
            if category.category_id is not None:
                value = get_category_effective_setting(
                    categories_by_id[category.category_id], field
                )
            else:
                value = get_project_effective_setting(
                    projects_by_id[category.project_id], field
                )
        else:
            value = get_value(category, field)
        effective_category_cache[cache_key] = value
        return value

    def get_project_effective_setting_owner(project, field: str) -> dict[str, int]:
        if project.workspace_id is not None and getattr(
            project, inherit_field(field), False
        ):
            return {"workspace_id": project.workspace_id}
        return {"project_id": project.pk}

    def get_category_effective_setting_owner(category, field: str) -> dict[str, int]:
        if getattr(category, inherit_field(field), False):
            if category.category_id is not None:
                return get_category_effective_setting_owner(
                    categories_by_id[category.category_id], field
                )
            return get_project_effective_setting_owner(
                projects_by_id[category.project_id], field
            )
        return {"category_id": category.pk}

    def get_category_parent_effective_setting(category, field: str):
        if category.category_id is not None:
            return get_category_effective_setting(
                categories_by_id[category.category_id], field
            )
        return get_project_effective_setting(projects_by_id[category.project_id], field)

    def get_category_parent_effective_setting_owner(
        category, field: str
    ) -> dict[str, int]:
        if category.category_id is not None:
            return get_category_effective_setting_owner(
                categories_by_id[category.category_id], field
            )
        return get_project_effective_setting_owner(
            projects_by_id[category.project_id], field
        )

    def clear_category_effective_cache(category) -> None:
        for cache_key in list(effective_category_cache):
            if cache_key[0] == category.pk:
                del effective_category_cache[cache_key]

    for category in sorted(
        categories,
        key=lambda item: get_category_depth(item, categories_by_id),
        reverse=True,
    ):
        components = components_by_category.get(category.pk, [])
        child_categories = categories_by_parent.get(category.pk, [])

        for field in INHERITABLE_COMPONENT_SETTINGS:
            values = []
            has_explicit_child = False
            inherit_name = inherit_field(field)

            for component in components:
                if getattr(component, inherit_name):
                    value = get_category_effective_setting(category, field)
                else:
                    value = get_value(component, field)
                    has_explicit_child = True
                values.append(value)

            for child in child_categories:
                values.append(get_category_effective_setting(child, field))
                if not getattr(child, inherit_name):
                    has_explicit_child = True

            if values and has_explicit_child and len(set(values)) == 1:
                value = values[0]
                inherit = value == get_category_parent_effective_setting(
                    category, field
                )
                set_value(category, field, value)
                setattr(category, inherit_name, inherit)
                category_updates[category.pk] = category
                clear_category_effective_cache(category)
                if field == "agreement" and value:
                    promote_agreements(
                        ContributorAgreement,
                        (
                            get_category_parent_effective_setting_owner(category, field)
                            if inherit
                            else {"category_id": category.pk}
                        ),
                        components,
                        child_categories,
                    )
                for component in components:
                    setattr(component, inherit_name, True)
                    component_updates[component.pk] = component
                for child in child_categories:
                    setattr(child, inherit_name, True)
                    category_updates[child.pk] = child
                    clear_category_effective_cache(child)

        flag_values = [
            *(component.check_flags for component in components),
            *(child.check_flags for child in child_categories),
        ]
        if flag_values and len(set(flag_values)) == 1:
            common_flags = flag_values[0]
            if common_flags:
                category.check_flags = merge_flags(category.check_flags, common_flags)
                category_updates[category.pk] = category
                for component in components:
                    component.check_flags = ""
                    component_updates[component.pk] = component
                for child in child_categories:
                    child.check_flags = ""
                    category_updates[child.pk] = child

    if category_updates:
        Category.objects.bulk_update(
            category_updates.values(), sorted(category_update_fields), batch_size=1000
        )
    if component_updates:
        Component.objects.bulk_update(
            component_updates.values(),
            sorted(component_update_fields),
            batch_size=1000,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0086_category_inherited_settings"),
    ]

    operations = [
        migrations.RunPython(consolidate_category_settings, migrations.RunPython.noop),
    ]
