# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Populate the branches of the alert lifecycle migration on the old schema."""

from __future__ import annotations

from weblate.addons.models import Addon
from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.trans.models import Alert, Component, Translation

component = Component.objects.get(pk=1)
source = component.source_translation
unit = source.unit_set.order_by("pk").first()
source.unit_set.filter(pk=unit.pk).update(
    source='Migration <a href="https://example.com/">link</a>', extra_flags="safe-html"
)
# Include both used and unused screenshots, and source units without screenshots.
for name in ("migration-used", "migration-unused"):
    screenshot = Screenshot.objects.create(
        name=name, translation=source, image="screenshots/migration.png"
    )
    if name == "migration-used":
        screenshot.units.add(unit)

# Avoid runtime translation/add-on initialization and external repository work.
Translation.objects.bulk_create(
    [
        Translation(
            component=component,
            language=Language.objects.get(code="ku"),
            language_code="ku",
            plural=source.plural,
            filename="ku.po",
        )
    ]
)
Addon.objects.bulk_create(
    [
        Addon(component=component, name="weblate.gettext.xgettext", configuration={}),
        Addon(
            project=component.project, name="weblate.gettext.msgmerge", configuration={}
        ),
    ]
)

# These names are stored as data even on releases predating the alert classes.
# Exercise every distinct context, including the default and normalization cases.
names = (
    "MissingLicense",
    "MissingRepositoryHook",
    "MissingPushURL",
    "MissingTranslationInstructions",
    "BrokenProjectURL",
    "MonolingualGlossary",
    "GlossaryStringManagementDisabled",
    "RepositoryChanges",
    "GitHubAppMigration",
    "MissingScreenshots",
    "MissingTranslationFlags",
    "MissingSafeHTMLFlag",
    "UnusedScreenshot",
    "AmbiguousLanguage",
    "RecommendedLanguageConsistencyAddon",
    "ExtractPotMissingMsgmerge",
    "MsgmergeAddonError",
    "UpdateFailure",
)
for name in (*names, "DuplicateString"):
    Alert.objects.update_or_create(
        component=component,
        name=name,
        defaults={
            "dismissed": name != "DuplicateString",  # type: ignore[misc]
            "details": {
                "migration_test": True,
                "error": "migration failure",
                "occurrences": [
                    {
                        "addon": "weblate.gettext.msgmerge",
                        "addon_id": "123",
                        "error": "failure",
                    }
                ],
            },
        },
    )
# The old schema has a dismissed field which is absent from current type stubs.
assert Alert.objects.filter(  # type: ignore[misc]
    component=component, details__migration_test=True, dismissed=True
).count() == len(names)
