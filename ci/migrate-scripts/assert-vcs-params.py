# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.models import Component

component1 = Component.objects.get(slug="vcs-params-force-push")
component2 = Component.objects.get(slug="vcs-params-plain-git")

# the dedicated force push backend became a Git parameter
assert component1.vcs == "git"
assert component1.vcs_params["git_force_push"] is True

# unrelated components are untouched
assert component2.vcs == "git"
assert "git_force_push" not in component2.vcs_params
