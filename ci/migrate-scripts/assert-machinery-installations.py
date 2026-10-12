# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.apps import apps

Installation = apps.get_model("machinery", "MachineryInstallation")
Exclusion = apps.get_model("machinery", "MachineryExclusion")
Project = apps.get_model("trans", "Project")

project = Project.objects.get(slug="test")
inherited = Project.objects.get(slug="machinery-inherited")
assert Installation.objects.get(
    engine="openai", project__isnull=True
).configuration == {"key": "migration-site"}
assert Installation.objects.get(engine="openai", project=project).configuration == {
    "key": "migration-project"
}
assert Exclusion.objects.filter(project=project, engine="openai").exists()
assert Exclusion.objects.filter(project=project, engine="deepl").exists()
assert not Installation.objects.filter(project=project, engine="deepl").exists()
project_engines = {item.split(":")[0] for item in project.get_machinery_settings()}
assert "openai" in project_engines
assert "deepl" not in project_engines
assert {item.split(":")[0] for item in inherited.get_machinery_settings()} >= {
    "openai",
    "deepl",
}
