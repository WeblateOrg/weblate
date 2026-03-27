# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Set up component links for migration testing."""

from weblate.trans.models import Component, Project

project = Project.objects.create(name="link-target", slug="link-target")
component = Component.objects.filter(project__slug="test").first()
component.links.add(project)
