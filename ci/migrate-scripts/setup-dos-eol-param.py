# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.lang.models import Language, Plural
from weblate.trans.models import Component, Project, Translation, Unit

project = Project.objects.create(
    name="dos-eol-test-project",
    slug="dos-eol-test-project",
    set_language_team=False,
    check_flags="dos-eol",
)
component1, component2 = Component.objects.bulk_create(
    [
        Component(
            name="dos-eol-test-component1",
            slug="dos-eol-test-component1",
            project=project,
            file_format="po",
        ),
        Component(
            name="dos-eol-test-component2",
            slug="dos-eol-test-component2",
            project=project,
            file_format="po",
            check_flags="dos-eol",
        ),
    ]
)

en_language = Language.objects.get(code="en")
translation = Translation.objects.bulk_create(
    [
        Translation(
            component=component1,
            language=en_language,
            check_flags="dos-eol",
            language_code="en",
            plural=Plural.objects.create(
                language=en_language,
                number=1,
                formula="n != 1",
            ),
        ),
    ]
)[0]
unit = Unit.objects.create(
    translation=translation,
    source="dos-eol-source",
    target="dos-eol-target",
    extra_flags="dos-eol",
    position=1,
    id_hash=10001,
)

assert "dos-eol" in project.check_flags
assert "dos-eol" not in component1.check_flags
assert "dos-eol" in component2.check_flags
assert "dos-eol" in translation.check_flags
assert "dos-eol" in unit.extra_flags
