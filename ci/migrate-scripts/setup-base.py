# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Basic setup for migration testing."""

from django.http.request import HttpRequest

from weblate.auth.models import get_anonymous
from weblate.lang.models import Language
from weblate.memory.models import Memory
from weblate.metrics.models import METRIC_ORDER, Metric
from weblate.trans.models import Component, Project, Suggestion, Translation

# Force creating project groups including billing
for project in Project.objects.iterator():
    project.access_control = Project.ACCESS_PROTECTED
    project.save()

# Enable suggestion voting
Component.objects.all().update(suggestion_voting=True, suggestion_autoaccept=2)

# Add suggestions
translation = Translation.objects.get(language__code="cs", component__slug="test")
request = HttpRequest()
request.user = get_anonymous()
with open("weblate/trans/tests/data/cs.po", "rb") as handle:
    translation.handle_upload(
        request,  # type: ignore[arg-type]
        handle,
        conflicts="",
        method="suggest",
        author_email="noreply@weblate.org",
    )

# Add vote for suggestion
suggestion = Suggestion.objects.all()[0]
suggestion.vote_set.create(user=suggestion.user, value=1)

# Add a global metric
Metric.objects.create(
    scope=Metric.SCOPE_GLOBAL, data=[1] * len(METRIC_ORDER), relation=0, changes=1
)

# Create huge translation memory entry
Memory.objects.create(
    source_language=Language.objects.get(code="en"),
    target_language=Language.objects.get(code="cs"),
    source="source" * 1000,
    target="target" * 1000,
    origin="origin" * 1000,
)

# Load translation memory
with open("./weblate/trans/tests/data/memory.json", "rb") as handle:
    Memory.objects.import_file(None, handle)
