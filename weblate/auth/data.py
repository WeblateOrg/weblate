#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Definition of permissions and default roles and groups."""


from django.utils.translation import gettext_noop as _

from weblate.utils.translation import pgettext_noop as pgettext

SELECTION_MANUAL = 0
SELECTION_ALL = 1
SELECTION_COMPONENT_LIST = 2
SELECTION_ALL_PUBLIC = 3
SELECTION_ALL_PROTECTED = 4

PERMISSIONS = (
    # Translators: Permission name
    ("billing.view", _("View billing info")),
    # Translators: Permission name
    ("change.download", _("Download changes")),
    # Translators: Permission name
    ("comment.add", _("Post comment")),
    # Translators: Permission name
    ("comment.delete", _("Delete comment")),
    # Translators: Permission name
    ("component.edit", _("Edit component settings")),
    # Translators: Permission name
    ("component.lock", _("Lock component, preventing translations")),
    # Translators: Permission name
    ("glossary.add", _("Add glossary entry")),
    # Translators: Permission name
    ("glossary.edit", _("Edit glossary entry")),
    # Translators: Permission name
    ("glossary.delete", _("Delete glossary entry")),
    # Translators: Permission name
    ("glossary.upload", _("Upload glossary entries")),
    # Translators: Permission name
    ("machinery.view", _("Use automatic suggestions")),
    # Translators: Permission name
    ("memory.edit", _("Edit translation memory")),
    # Translators: Permission name
    ("memory.delete", _("Delete translation memory")),
    # Translators: Permission name
    ("project.edit", _("Edit project settings")),
    # Translators: Permission name
    ("project.permissions", _("Manage project access")),
    # Translators: Permission name
    ("reports.view", _("Download reports")),
    # Translators: Permission name
    ("screenshot.add", _("Add screenshot")),
    # Translators: Permission name
    ("screenshot.edit", _("Edit screenshot")),
    # Translators: Permission name
    ("screenshot.delete", _("Delete screenshot")),
    # Translators: Permission name
    ("source.edit", _("Edit additional string info")),
    # Translators: Permission name
    ("unit.add", _("Add new string")),
    # Translators: Permission name
    ("unit.delete", _("Remove a string")),
    # Translators: Permission name
    ("unit.check", _("Ignore failing check")),
    # Translators: Permission name
    ("unit.edit", _("Edit strings")),
    # Translators: Permission name
    ("unit.review", _("Review strings")),
    # Translators: Permission name
    ("unit.override", _("Edit string when suggestions are enforced")),
    # Translators: Permission name
    ("unit.template", _("Edit source strings")),
    # Translators: Permission name
    ("suggestion.accept", _("Accept suggestion")),
    # Translators: Permission name
    ("suggestion.add", _("Add suggestion")),
    # Translators: Permission name
    ("suggestion.delete", _("Delete suggestion")),
    # Translators: Permission name
    ("suggestion.vote", _("Vote on suggestion")),
    # Translators: Permission name
    ("translation.add", _("Add language for translation")),
    # Translators: Permission name
    ("translation.auto", _("Perform automatic translation")),
    # Translators: Permission name
    ("translation.delete", _("Delete existing translation")),
    # Translators: Permission name
    ("translation.add_more", _("Add several languages for translation")),
    # Translators: Permission name
    ("upload.authorship", _("Define author of uploaded translation")),
    # Translators: Permission name
    ("upload.overwrite", _("Overwrite existing strings with upload")),
    # Translators: Permission name
    ("upload.perform", _("Upload translations")),
    # Translators: Permission name
    ("vcs.access", _("Access the internal repository")),
    # Translators: Permission name
    ("vcs.commit", _("Commit changes to the internal repository")),
    # Translators: Permission name
    ("vcs.push", _("Push change from the internal repository")),
    # Translators: Permission name
    ("vcs.reset", _("Reset changes in the internal repository")),
    # Translators: Permission name
    ("vcs.view", _("View upstream repository location")),
    # Translators: Permission name
    ("vcs.update", _("Update the internal repository")),
)

PERMISSION_NAMES = {perm[0] for perm in PERMISSIONS}

# Permissions which are not scoped per project
GLOBAL_PERMISSIONS = (
    # Translators: Permission name
    ("management.use", _("Use management interface")),
    # Translators: Permission name
    ("project.add", _("Add new projects")),
    # Translators: Permission name
    ("language.add", _("Add language definitions")),
    # Translators: Permission name
    ("language.edit", _("Manage language definitions")),
    # Translators: Permission name
    ("group.edit", _("Manage groups")),
    # Translators: Permission name
    ("user.edit", _("Manage users")),
    # Translators: Permission name
    ("role.edit", _("Manage roles")),
    # Translators: Permission name
    ("announcement.edit", _("Manage announcements")),
    # Translators: Permission name
    ("memory.edit", _("Manage translation memory")),
    # Translators: Permission name
    ("componentlist.edit", _("Manage component lists")),
)

GLOBAL_PERM_NAMES = {perm[0] for perm in GLOBAL_PERMISSIONS}


def filter_perms(prefix):
    """Filter permission based on prefix."""
    return {perm[0] for perm in PERMISSIONS if perm[0].startswith(prefix)}


# Translator permissions
TRANSLATE_PERMS = {
    "comment.add",
    "suggestion.accept",
    "suggestion.add",
    "suggestion.vote",
    "unit.check",
    "unit.edit",
    "upload.overwrite",
    "upload.perform",
    "machinery.view",
}

# Default set of roles
ROLES = (
    (pgettext("Access-control role", "Administration"), [x[0] for x in PERMISSIONS]),
    (
        pgettext("Access-control role", "Edit source"),
        TRANSLATE_PERMS | {"unit.template", "source.edit"},
    ),
    (pgettext("Access-control role", "Add suggestion"), {"suggestion.add"}),
    (pgettext("Access-control role", "Access repository"), {"vcs.access", "vcs.view"}),
    (pgettext("Access-control role", "Manage glossary"), filter_perms("glossary.")),
    (
        pgettext("Access-control role", "Power user"),
        TRANSLATE_PERMS
        | {
            "translation.add",
            "unit.template",
            "suggestion.delete",
            "vcs.access",
            "vcs.view",
        }
        | filter_perms("glossary."),
    ),
    (
        pgettext("Access-control role", "Review strings"),
        TRANSLATE_PERMS | {"unit.review", "unit.override"},
    ),
    (pgettext("Access-control role", "Translate"), TRANSLATE_PERMS),
    (pgettext("Access-control role", "Manage languages"), filter_perms("translation.")),
    (
        pgettext("Access-control role", "Manage translation memory"),
        filter_perms("memory."),
    ),
    (
        pgettext("Access-control role", "Manage screenshots"),
        filter_perms("screenshot."),
    ),
    (pgettext("Access-control role", "Manage repository"), filter_perms("vcs.")),
    (pgettext("Access-control role", "Billing"), filter_perms("billing.")),
)

# Default set of roles for groups
GROUPS = (
    (
        pgettext("Access-control group", "Guests"),
        ("Add suggestion", "Access repository"),
        SELECTION_ALL_PUBLIC,
    ),
    (pgettext("Access-control group", "Viewers"), (), SELECTION_ALL_PROTECTED),
    (pgettext("Access-control group", "Users"), ("Power user",), SELECTION_ALL_PUBLIC),
    (pgettext("Access-control group", "Reviewers"), ("Review strings",), SELECTION_ALL),
    (pgettext("Access-control group", "Managers"), ("Administration",), SELECTION_ALL),
)

# Per project group definitions
ACL_GROUPS = {
    pgettext("Per-project access-control group", "Translate"): "Translate",
    pgettext("Per-project access-control group", "Sources"): "Edit source",
    pgettext("Per-project access-control group", "Languages"): "Manage languages",
    pgettext("Per-project access-control group", "Glossary"): "Manage glossary",
    pgettext("Per-project access-control group", "Memory"): "Manage translation memory",
    pgettext("Per-project access-control group", "Screenshots"): "Manage screenshots",
    pgettext("Per-project access-control group", "Review"): "Review strings",
    pgettext("Per-project access-control group", "VCS"): "Manage repository",
    pgettext("Per-project access-control group", "Administration"): "Administration",
    pgettext("Per-project access-control group", "Billing"): "Billing",
}
