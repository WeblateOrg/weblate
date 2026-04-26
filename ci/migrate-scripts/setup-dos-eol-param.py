# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.lang.models import Language
from weblate.trans.models import Component, Project, Translation, Unit

project = Project.objects.create(
    name="dos-eol-test-project",
    slug="dos-eol-test-project",
    set_language_team=False,
    check_flags="dos-eol",
)
component1 = Component.objects.create(
    name="dos-eol-test-component1",
    slug="dos-eol-test-component1",
    project=project,
    file_format="po",
)
component2 = Component.objects.create(
    name="dos-eol-test-component2",
    slug="dos-eol-test-component2",
    project=project,
    file_format="po",
    check_flags="dos-eol",
)

translation = Translation.objects.create(
    component=component1,
    language=Language.objects.get(code="en"),
    source="source",
    target="target",
    check_flags="dos-eol",
)
unit = Unit.objects.create(
    translation=translation,
    source="dos-eol-source",
    target="dos-eol-target",
    extra_flags="dos-eol",
    check_flags="dos-eol",
)

assert "dos-eol" not in component1.check_flags
assert "dos-eol" in component2.check_flags
assert "dos-eol" in translation.check_flags
assert "dos-eol" in unit.check_flags
assert "dos-eol" in unit.extra_flags
