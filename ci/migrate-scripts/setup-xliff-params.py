# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Add components for XLIFF placeables/whitespace migration testing."""

from weblate.trans.models import Component

Component.objects.bulk_create(
    [
        Component(
            name="XLIFF plain",
            slug="xliff-plain",
            project_id=1,
            repo="weblate://test/xliff-plain",
            file_format="plainxliff",
            filemask="xliff/*.xliff",
        ),
        Component(
            name="XLIFF 2 placeables",
            slug="xliff2-placeables",
            project_id=1,
            repo="weblate://test/xliff2-placeables",
            file_format="xliff2-placeables",
            filemask="xliff2/*.xlf",
        ),
    ]
)
