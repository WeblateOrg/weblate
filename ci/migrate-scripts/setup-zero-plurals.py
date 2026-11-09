# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Populate duplicate and unaffected plural definitions before upgrade."""

from __future__ import annotations

from django.apps import apps

Language = apps.get_model("lang", "Language")
Plural = apps.get_model("lang", "Plural")
Project = apps.get_model("trans", "Project")
Component = apps.get_model("trans", "Component")
Translation = apps.get_model("trans", "Translation")

language, singleton_language = Language.objects.bulk_create(
    [
        Language(code="qaa_ZERO", name="Duplicate zero plurals"),
        Language(code="qab_ZERO", name="Singleton zero plural"),
    ]
)
Plural.objects.bulk_create(
    [
        Plural(language=language, source=0, number=2, formula="n != 1"),
        Plural(language=singleton_language, source=0, number=2, formula="n != 1"),
    ]
)
plurals = Plural.objects.bulk_create(
    [
        Plural(language=language, source=3, number=3, formula="n == 0 ? 0 : 1"),
        Plural(language=language, source=3, number=2, formula="n != 1"),
        Plural(language=language, source=3, number=2, formula="n != 1"),
        Plural(language=singleton_language, source=3, number=2, formula="n != 1"),
        Plural(language=language, source=2, number=2, formula="n != 1"),
        Plural(language=language, source=2, number=2, formula="n != 1"),
    ]
)
project = Project.objects.bulk_create(
    [Project(name="Zero plural upgrade", slug="zero-plural-upgrade")]
)[0]
for index, plural in enumerate(plurals):
    component = Component.objects.bulk_create(
        [
            Component(
                project=project,
                name=f"Plural {index}",
                slug=f"plural-{index}",
                source_language=language,
                repo="https://example.org/repo.git",
                file_format="po",
            )
        ]
    )[0]
    Translation.objects.bulk_create(
        [
            Translation(
                component=component,
                language_id=plural.language_id,
                plural=plural,
                filename=f"plural-{index}.po",
            )
        ]
    )
