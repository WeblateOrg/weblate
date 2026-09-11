# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone

from weblate.utils.hash import calculate_json_fingerprint

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


# Keep these contexts local to the migration: runtime alert classes and model
# helpers can start querying fields which do not exist at this migration state.
def get_addon_names(apps: StateApps, component, database: str) -> list[str]:
    Addon = apps.get_model("addons", "Addon")
    category_ids = []
    category = component.category
    while category is not None:
        category_ids.append(category.pk)
        category = category.category
    query = (
        models.Q(component_id=component.pk)
        | models.Q(project_id=component.project_id)
        | models.Q(category_id__in=category_ids)
        | models.Q(component__isnull=True, category__isnull=True, project__isnull=True)
    )
    if component.linked_component_id:
        query |= models.Q(component_id=component.linked_component_id, repo_scope=True)
    return sorted(
        Addon.objects.using(database).filter(query).values_list("name", flat=True)
    )


def get_unit_context(apps: StateApps, component, name: str, database: str) -> dict:
    context: dict = {}
    Unit = apps.get_model("trans", "Unit")
    units = (
        Unit.objects.using(database)
        .filter(
            translation__component_id=component.pk,
            translation__language_id=component.source_language_id,
        )
        .order_by("pk")
    )
    if name == "MissingScreenshots":
        context["units_without_screenshots"] = list(
            units.filter(screenshots__isnull=True).values_list("pk", flat=True)
        )
    else:
        context["check_flags"] = component.check_flags
        if name == "MissingTranslationFlags":
            context["flags"] = list(
                units.exclude(extra_flags="").values_list("pk", "extra_flags")
            )
        else:
            context["units"] = list(
                units.filter(source__contains="<a ").values_list("pk", "extra_flags")
            )
    return context


def get_addon_error_context(details: dict) -> dict:
    context = {"details": details}
    occurrences = details.get("occurrences")
    if isinstance(occurrences, list):
        context["details"] = {
            **details,
            "occurrences": [
                {key: value for key, value in occurrence.items() if key != "addon_id"}
                if isinstance(occurrence, dict)
                else occurrence
                for occurrence in occurrences
            ],
        }
    return context


def get_repository_error_context(details: dict) -> dict:
    context: dict = {}
    # This formatter does not access the database.
    from weblate.vcs.base import format_stored_repository_error  # ruff: ignore[import-outside-top-level]

    context["details"] = {
        key: value
        for key, value in details.items()
        if key not in {"diagnoses", "error"}
    }
    if error := details.get("error"):
        context["details"]["error"] = format_stored_repository_error(error).replace(
            "repository URL", "..."
        )
    return context


def get_dismissal_context(
    apps: StateApps, component, name: str, details: dict, database: str
) -> dict:
    context: dict = {"details": details}
    match name:
        case "MissingRepositoryHook":
            context["repo"] = component.repo
        case "MissingPushURL":
            context.update(repo=component.repo, push=component.push)
        case "MissingTranslationInstructions":
            context.update(
                access_control=component.project.access_control,
                instructions=component.project.instructions,
            )
        case "BrokenProjectURL":
            context["web"] = component.project.web
        case "MonolingualGlossary":
            context["template"] = component.template
        case "GlossaryStringManagementDisabled":
            context.update(
                repo=component.repo, source_language=component.source_language_id
            )
        case "RepositoryChanges":
            context.update(
                branch=component.branch,
                local_revision=component.local_revision,
                repo=component.repo,
            )
        case "GitHubAppMigration":
            context.update(
                repo=component.repo,
                vcs=component.vcs,
                workspace=str(component.project.workspace_id or ""),
            )
        case "MissingScreenshots" | "MissingTranslationFlags" | "MissingSafeHTMLFlag":
            context.update(get_unit_context(apps, component, name, database))
        case "UnusedScreenshot":
            Screenshot = apps.get_model("screenshots", "Screenshot")
            context["screenshots"] = list(
                Screenshot.objects.using(database)
                .filter(translation__component_id=component.pk, units__isnull=True)
                .order_by("pk")
                .values_list("pk", flat=True)
            )
        case "AmbiguousLanguage":
            Translation = apps.get_model("trans", "Translation")
            context["languages"] = list(
                Translation.objects.using(database)
                .filter(component_id=component.pk, language__code__in=("ku", "kur"))
                .order_by("language__code")
                .values_list("language__code", flat=True)
            )
        case (
            "RecommendedLanguageConsistencyAddon"
            | "RecommendedLinguasAddon"
            | "RecommendedConfigureAddon"
            | "RecommendedCleanupAddon"
            | "RecommendedGenerateMoAddon"
            | "RecommendedXgettextAddon"
            | "RecommendedMesonAddon"
            | "RecommendedDjangoAddon"
            | "RecommendedSphinxAddon"
            | "ExtractPotMissingMsgmerge"
        ):
            addons = get_addon_names(apps, component, database)
            if name == "ExtractPotMissingMsgmerge":
                addons = [
                    addon
                    for addon in addons
                    if addon
                    in {
                        "weblate.gettext.xgettext",
                        "weblate.gettext.meson",
                        "weblate.gettext.django",
                        "weblate.gettext.sphinx",
                        "weblate.gettext.msgmerge",
                    }
                ]
            else:
                context["new_base"] = component.new_base
            context.update(addons=addons, file_format=component.file_format)
        case (
            "AddonScriptError"
            | "CDNAddonError"
            | "MsgmergeAddonError"
            | "ExtractPotAddonError"
        ):
            context.update(get_addon_error_context(details))
        case (
            "MergeFailure"
            | "RepositoryOperationFailure"
            | "PushFailure"
            | "UpdateFailure"
            | "AutomergeFailure"
        ):
            context.update(get_repository_error_context(details))
    return context


def backfill_dismissals(apps: StateApps, alerts) -> None:
    Component = apps.get_model("trans", "Component")
    dismissed_at = timezone.now()
    components = Component.objects.using(alerts.db).in_bulk(
        alerts.values_list("component_id", flat=True).distinct()
    )
    for alert in alerts.iterator():
        context = get_dismissal_context(
            apps, components[alert.component_id], alert.name, alert.details, alerts.db
        )
        alert.dismissed_at = dismissed_at
        alert.dismissal_fingerprint = calculate_json_fingerprint(context)
        alert.save(
            using=alerts.db, update_fields=("dismissed_at", "dismissal_fingerprint")
        )


def backfill_dismissed_at(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Alert = apps.get_model("trans", "Alert")
    backfill_dismissals(
        apps, Alert.objects.using(schema_editor.connection.alias).filter(dismissed=True)
    )


def restore_dismissed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Alert = apps.get_model("trans", "Alert")
    Alert.objects.using(schema_editor.connection.alias).filter(
        dismissed_at__isnull=False
    ).update(dismissed=True)


class Migration(migrations.Migration):
    dependencies = [
        ("addons", "0014_addon_category"),
        ("screenshots", "0001_squashed_weblate_5"),
        ("trans", "0093_project_workspace_tm"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="dismissal_fingerprint",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="alert",
            name="dismissal_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="alert",
            name="dismissed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="alert",
            name="dismissed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="dismissed_alerts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_dismissed_at, restore_dismissed),
        migrations.RemoveField(
            model_name="alert",
            name="dismissed",
        ),
        migrations.AlterField(
            model_name="change",
            name="action",
            field=models.IntegerField(
                choices=[
                    (0, "Resource updated"),
                    (1, "Translation completed"),
                    (2, "Translation changed"),
                    (3, "Comment added"),
                    (4, "Suggestion added"),
                    (5, "Translation added"),
                    (6, "Automatically translated"),
                    (7, "Suggestion accepted"),
                    (8, "Translation reverted"),
                    (9, "Translation uploaded"),
                    (13, "Source string added"),
                    (14, "Component locked"),
                    (15, "Component unlocked"),
                    (17, "Changes committed"),
                    (18, "Changes pushed"),
                    (19, "Repository reset"),
                    (20, "Repository merged"),
                    (21, "Repository rebased"),
                    (22, "Repository merge failed"),
                    (23, "Repository rebase failed"),
                    (24, "Parsing failed"),
                    (25, "Translation removed"),
                    (26, "Suggestion removed"),
                    (27, "Translation replaced"),
                    (28, "Repository push failed"),
                    (29, "Suggestion removed during cleanup"),
                    (30, "Source string changed"),
                    (31, "String added"),
                    (32, "Bulk status changed"),
                    (33, "Visibility changed"),
                    (34, "User added"),
                    (35, "User removed"),
                    (36, "Translation approved"),
                    (37, "Marked for edit"),
                    (38, "Component removed"),
                    (39, "Project removed"),
                    (41, "Project renamed"),
                    (42, "Component renamed"),
                    (43, "Moved component"),
                    (45, "Contributor joined"),
                    (46, "Announcement posted"),
                    (47, "Alert triggered"),
                    (48, "Language added"),
                    (49, "Language requested"),
                    (50, "Project created"),
                    (51, "Component created"),
                    (52, "User invited"),
                    (53, "Repository notification received"),
                    (54, "Translation replaced file by upload"),
                    (55, "License changed"),
                    (56, "Contributor license agreement changed"),
                    (57, "Screenshot added"),
                    (58, "Screenshot uploaded"),
                    (59, "String updated in the repository"),
                    (60, "Add-on installed"),
                    (61, "Add-on configuration changed"),
                    (62, "Add-on uninstalled"),
                    (63, "String removed"),
                    (64, "Comment removed"),
                    (65, "Comment resolved"),
                    (66, "Explanation updated"),
                    (67, "Category removed"),
                    (68, "Category renamed"),
                    (69, "Category moved"),
                    (70, "Saving string failed"),
                    (71, "String added in the repository"),
                    (72, "String updated in the upload"),
                    (73, "String added in the upload"),
                    (74, "Translation updated by source upload"),
                    (75, "Component translation completed"),
                    (76, "Applied enforced check"),
                    (77, "Propagated change"),
                    (78, "File uploaded"),
                    (79, "Extra flags updated"),
                    (80, "Font uploaded"),
                    (81, "Font changed"),
                    (82, "Font removed"),
                    (83, "Forced synchronization of translations"),
                    (84, "Forced rescan of translations"),
                    (85, "Screenshot removed"),
                    (86, "Label added"),
                    (87, "Label removed"),
                    (88, "Repository cleanup"),
                    (89, "Source string added in the upload"),
                    (90, "Source string added in the repository"),
                    (91, "Project backed up"),
                    (92, "Project restored"),
                    (93, "Component restored"),
                    (94, "User edit reverted"),
                    (95, "Project setting changed"),
                    (96, "Component setting changed"),
                    (97, "User access changed"),
                    (98, "Workspace created"),
                    (99, "Workspace setting changed"),
                    (100, "Project moved"),
                    (101, "Remote repository updated"),
                    (102, "Remote repository update failed"),
                    (103, "Alert dismissed"),
                    (104, "Alert reopened"),
                ],
                default=2,
            ),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(
                condition=models.Q(("dismissed_at__isnull", True)),
                fields=["component", "severity"],
                name="trans_alert_active_idx",
            ),
        ),
    ]
