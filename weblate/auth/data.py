# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Definition of permissions and default roles and groups."""

from __future__ import annotations

from django.utils.translation import gettext_noop

from weblate.utils.translation import pgettext_noop

SELECTION_MANUAL = 0
SELECTION_ALL = 1
SELECTION_COMPONENT_LIST = 2
SELECTION_ALL_PUBLIC = 3
SELECTION_ALL_PROTECTED = 4

PERMISSIONS = (
    # Translators: Permission name
    ("billing.view", gettext_noop("View billing info")),
    # Translators: Permission name
    ("change.download", gettext_noop("Download changes")),
    # Translators: Permission name
    ("comment.add", gettext_noop("Post comment")),
    # Translators: Permission name
    ("comment.delete", gettext_noop("Delete comment")),
    # Translators: Permission name
    ("comment.resolve", gettext_noop("Resolve comment")),
    # Translators: Permission name
    ("component.edit", gettext_noop("Edit component settings")),
    # Translators: Permission name
    ("component.lock", gettext_noop("Lock component, preventing translations")),
    # Translators: Permission name
    ("glossary.add", gettext_noop("Add glossary entry")),
    # Translators: Permission name
    ("glossary.terminology", gettext_noop("Add glossary terminology")),
    # Translators: Permission name
    ("glossary.edit", gettext_noop("Edit glossary entry")),
    # Translators: Permission name
    ("glossary.delete", gettext_noop("Delete glossary entry")),
    # Translators: Permission name
    ("glossary.upload", gettext_noop("Upload glossary entries")),
    # Translators: Permission name
    ("machinery.view", gettext_noop("Use automatic suggestions")),
    # Translators: Permission name
    ("memory.edit", gettext_noop("Edit translation memory")),
    # Translators: Permission name
    ("memory.delete", gettext_noop("Delete translation memory")),
    # Translators: Permission name
    ("project.edit", gettext_noop("Edit project settings")),
    # Translators: Permission name
    ("project.permissions", gettext_noop("Manage project access")),
    # Translators: Permission name
    ("reports.view", gettext_noop("Download reports")),
    # Translators: Permission name
    ("screenshot.add", gettext_noop("Add screenshot")),
    # Translators: Permission name
    ("screenshot.edit", gettext_noop("Edit screenshot")),
    # Translators: Permission name
    ("screenshot.delete", gettext_noop("Delete screenshot")),
    # Translators: Permission name
    ("source.edit", gettext_noop("Edit additional string info")),
    # Translators: Permission name
    ("unit.add", gettext_noop("Add new string")),
    # Translators: Permission name
    ("unit.delete", gettext_noop("Remove a string")),
    # Translators: Permission name
    ("unit.check", gettext_noop("Dismiss failing check")),
    # Translators: Permission name
    ("unit.edit", gettext_noop("Edit strings")),
    # Translators: Permission name
    ("unit.review", gettext_noop("Review strings")),
    # Translators: Permission name
    ("unit.override", gettext_noop("Edit string when suggestions are enforced")),
    # Translators: Permission name
    ("unit.template", gettext_noop("Edit source strings")),
    # Translators: Permission name
    ("suggestion.accept", gettext_noop("Accept suggestion")),
    # Translators: Permission name
    ("suggestion.add", gettext_noop("Add suggestion")),
    # Translators: Permission name
    ("suggestion.delete", gettext_noop("Delete suggestion")),
    # Translators: Permission name
    ("suggestion.vote", gettext_noop("Vote on suggestion")),
    # Translators: Permission name
    ("translation.add", gettext_noop("Add language for translation")),
    # Translators: Permission name
    ("translation.auto", gettext_noop("Perform automatic translation")),
    # Translators: Permission name
    ("translation.delete", gettext_noop("Delete existing translation")),
    # Translators: Permission name
    ("translation.download", gettext_noop("Download translation file")),
    # Translators: Permission name
    ("translation.add_more", gettext_noop("Add several languages for translation")),
    # Translators: Permission name
    ("upload.authorship", gettext_noop("Define author of uploaded translation")),
    # Translators: Permission name
    ("upload.overwrite", gettext_noop("Overwrite existing strings with upload")),
    # Translators: Permission name
    ("upload.perform", gettext_noop("Upload translations")),
    # Translators: Permission name
    ("vcs.access", gettext_noop("Access the internal repository")),
    # Translators: Permission name
    ("vcs.commit", gettext_noop("Commit changes to the internal repository")),
    # Translators: Permission name
    ("vcs.push", gettext_noop("Push change from the internal repository")),
    # Translators: Permission name
    ("vcs.reset", gettext_noop("Reset changes in the internal repository")),
    # Translators: Permission name
    ("vcs.view", gettext_noop("View upstream repository location")),
    # Translators: Permission name
    ("vcs.update", gettext_noop("Update the internal repository")),
)

PERMISSION_NAMES = {perm[0] for perm in PERMISSIONS}

# Permissions which are not scoped per project
GLOBAL_PERMISSIONS = (
    # Translators: Permission name
    ("management.use", gettext_noop("Use management interface")),
    # Translators: Permission name
    ("project.add", gettext_noop("Add new projects")),
    # Translators: Permission name
    ("language.add", gettext_noop("Add language definitions")),
    # Translators: Permission name
    ("language.edit", gettext_noop("Manage language definitions")),
    # Translators: Permission name
    ("group.edit", gettext_noop("Manage teams")),
    # Translators: Permission name
    ("user.edit", gettext_noop("Manage users")),
    # Translators: Permission name
    ("role.edit", gettext_noop("Manage roles")),
    # Translators: Permission name
    ("announcement.edit", gettext_noop("Manage announcements")),
    # Translators: Permission name
    ("memory.manage", gettext_noop("Manage translation memory")),
    # Translators: Permission name
    ("machinery.edit", gettext_noop("Manage machinery")),
    # Translators: Permission name
    ("componentlist.edit", gettext_noop("Manage component lists")),
    # Translators: Permission name
    ("billing.manage", gettext_noop("Manage billing")),
    # Translators: Permission name
    ("management.addons", gettext_noop("Manage site-wide add-ons")),
)

GLOBAL_PERM_NAMES = {perm[0] for perm in GLOBAL_PERMISSIONS}


def filter_perms(prefix: str, exclude: set | None = None):
    """Filter permission based on prefix."""
    result = {perm[0] for perm in PERMISSIONS if perm[0].startswith(prefix)}
    if exclude:
        result = result.difference(exclude)
    return result


# Translator permissions
TRANSLATE_PERMS = {
    "comment.add",
    "suggestion.accept",
    "suggestion.add",
    "suggestion.vote",
    "unit.check",
    "unit.edit",
    "translation.download",
    "upload.overwrite",
    "upload.perform",
    "machinery.view",
}

# Default set of roles
ROLES = (
    (
        pgettext_noop("Access-control role", "Administration"),
        [x[0] for x in PERMISSIONS],
    ),
    (
        pgettext_noop("Access-control role", "Edit source"),
        TRANSLATE_PERMS | {"unit.template", "source.edit"},
    ),
    (pgettext_noop("Access-control role", "Add suggestion"), {"suggestion.add"}),
    (
        pgettext_noop("Access-control role", "Access repository"),
        {"translation.download", "vcs.access", "vcs.view"},
    ),
    (
        pgettext_noop("Access-control role", "Manage glossary"),
        filter_perms("glossary."),
    ),
    (
        pgettext_noop("Access-control role", "Power user"),
        TRANSLATE_PERMS
        | {
            "translation.add",
            "unit.template",
            "suggestion.delete",
            "vcs.access",
            "vcs.view",
        }
        | filter_perms("glossary.", {"glossary.terminology"}),
    ),
    (
        pgettext_noop("Access-control role", "Review strings"),
        TRANSLATE_PERMS | {"unit.review", "unit.override", "comment.resolve"},
    ),
    (pgettext_noop("Access-control role", "Translate"), TRANSLATE_PERMS),
    (
        pgettext_noop("Access-control role", "Manage languages"),
        filter_perms("translation.", {"translation.auto"}),
    ),
    (
        pgettext_noop("Access-control role", "Automatic translation"),
        {"translation.auto"},
    ),
    (
        pgettext_noop("Access-control role", "Manage translation memory"),
        filter_perms("memory."),
    ),
    (
        pgettext_noop("Access-control role", "Manage screenshots"),
        filter_perms("screenshot."),
    ),
    (
        pgettext_noop("Access-control role", "Manage repository"),
        filter_perms("vcs.") | {"component.lock"},
    ),
    (pgettext_noop("Access-control role", "Billing"), filter_perms("billing.")),
    (pgettext_noop("Access-control role", "Add new projects"), {"project.add"}),
)

# Default set of roles for groups
GROUPS = (
    (
        pgettext_noop("Access-control team name", "Guests"),
        ("Add suggestion", "Access repository"),
        SELECTION_ALL_PUBLIC,
    ),
    (pgettext_noop("Access-control team name", "Viewers"), (), SELECTION_ALL_PROTECTED),
    (
        pgettext_noop("Access-control team name", "Users"),
        ("Power user",),
        SELECTION_ALL_PUBLIC,
    ),
    (
        pgettext_noop("Access-control team name", "Reviewers"),
        ("Review strings",),
        SELECTION_ALL,
    ),
    (
        pgettext_noop("Access-control team name", "Managers"),
        ("Administration",),
        SELECTION_ALL,
    ),
    (
        pgettext_noop("Access-control team name", "Project creators"),
        ("Add new projects",),
        SELECTION_ALL,
    ),
)

# Per project group definitions
ACL_GROUPS = {
    pgettext_noop(
        "Per-project access-control team name", "Administration"
    ): "Administration",
    pgettext_noop("Per-project access-control team name", "Review"): "Review strings",
    pgettext_noop("Per-project access-control team name", "Translate"): "Translate",
    pgettext_noop("Per-project access-control team name", "Sources"): "Edit source",
    pgettext_noop(
        "Per-project access-control team name", "Languages"
    ): "Manage languages",
    pgettext_noop(
        "Per-project access-control team name", "Glossary"
    ): "Manage glossary",
    pgettext_noop(
        "Per-project access-control team name", "Memory"
    ): "Manage translation memory",
    pgettext_noop(
        "Per-project access-control team name", "Screenshots"
    ): "Manage screenshots",
    pgettext_noop(
        "Per-project access-control team name", "Automatic translation"
    ): "Automatic translation",
    pgettext_noop("Per-project access-control team name", "VCS"): "Manage repository",
    pgettext_noop("Per-project access-control team name", "Billing"): "Billing",
}
