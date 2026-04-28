# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.models import Component, Project, Translation, Unit

project = Project.objects.get(slug="dos-eol-test-project")
component1 = Component.objects.get(slug="dos-eol-test-component1")
component2 = Component.objects.get(slug="dos-eol-test-component2")
translation = Translation.objects.get(component=component1, language__code="en")
unit = Unit.objects.get(
    translation=translation,
    source="dos-eol-source",
    target="dos-eol-target",
)

# check params are set
assert component1.file_format_params["dos_eol"] is True
assert component2.file_format_params["dos_eol"] is True

# check flags are removed
assert "dos-eol" not in project.check_flags
assert "dos-eol" not in component1.check_flags
assert "dos-eol" not in component2.check_flags
assert "dos-eol" not in translation.check_flags
assert "dos-eol" not in unit.extra_flags
