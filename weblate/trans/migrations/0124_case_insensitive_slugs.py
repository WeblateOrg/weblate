# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.postgres.aggregates import ArrayAgg
from django.db import NotSupportedError, migrations, models
from django.db.models.functions import Upper

if TYPE_CHECKING:
    from django.apps.registry import Apps
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def check_postgresql_version(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    if schema_editor.connection.get_database_version() < (15,):
        msg = (
            "Weblate requires PostgreSQL 15 or later. "
            "Upgrade the database server before upgrading Weblate."
        )
        raise NotSupportedError(msg)


def check_slug_conflicts(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    using = schema_editor.connection.alias
    project = apps.get_model("trans", "Project")
    category = apps.get_model("trans", "Category")
    component = apps.get_model("trans", "Component")
    project_conflicts = (
        project.objects.using(using)
        .values(folded_slug=Upper("slug"))
        .annotate(count=models.Count("pk"), slugs=ArrayAgg("slug", order_by="slug"))
        .filter(count__gt=1)
        .order_by("folded_slug")
    )
    component_conflicts = (
        component.objects.using(using)
        .values("project__slug", "category_id", folded_slug=Upper("slug"))
        .annotate(count=models.Count("pk"), slugs=ArrayAgg("slug", order_by="slug"))
        .filter(count__gt=1)
        .order_by("project__slug", "category_id", "folded_slug")
    )

    conflicts = [", ".join(row["slugs"]) for row in project_conflicts]
    for row in component_conflicts:
        parents = []
        category_id = row["category_id"]
        while category_id is not None:
            slug, category_id = (
                category.objects.using(using)
                .values_list("slug", "category_id")
                .get(pk=category_id)
            )
            parents.append(slug)
        prefix = "/".join((row["project__slug"], *reversed(parents)))
        conflicts.append(", ".join(f"{prefix}/{slug}" for slug in row["slugs"]))

    if conflicts:
        details = "\n".join(conflicts)
        msg = (
            "Case-insensitive URL slug conflicts prevent this upgrade. "
            "Rename the conflicting projects or components using the previous "
            f"Weblate release, then retry the upgrade.\n{details}"
        )
        raise RuntimeError(msg)


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0123_unit_line_number"),
    ]

    operations = [
        migrations.RunPython(check_postgresql_version, migrations.RunPython.noop),
        migrations.RunPython(check_slug_conflicts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.UniqueConstraint(
                Upper("slug"), name="project_slug_ci_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="component",
            constraint=models.UniqueConstraint(
                models.F("project"),
                models.F("category"),
                Upper("slug"),
                name="component_slug_ci_unique",
                nulls_distinct=False,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="component",
            name="component_slug_unique",
        ),
    ]
