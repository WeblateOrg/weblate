# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.db import OperationalError, connection, transaction
from django.db.models import QuerySet
from django.test import RequestFactory, TransactionTestCase
from django.urls import reverse

from weblate.screenshots.models import Screenshot
from weblate.screenshots.views import select_screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.trans.tests.utils import RepoTestMixin, clear_users_cache, create_test_user

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest, User


class ScreenshotSelectionLockTest(RepoTestMixin, TransactionTestCase):
    def setUp(self) -> None:
        clear_users_cache()
        self.addCleanup(clear_users_cache)
        self.clone_test_repos()
        super().setUp()
        self.component = self.create_component()
        self.user = create_test_user()
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.unit = Unit.objects.get(
            translation__component=self.component,
            translation__language__code="cs",
            source="Hello, world!\n",
        )
        self.screenshot = Screenshot.objects.create(
            name="Lock preview", translation=self.unit.translation
        )

    def test_selection_locks_screenshot_only(self) -> None:
        original = Screenshot.add_unit

        def probe() -> None:
            try:
                with transaction.atomic():
                    for model, pk in (
                        (Unit, self.unit.pk),
                        (Translation, self.unit.translation_id),
                        (Component, self.component.pk),
                        (Project, self.component.project_id),
                    ):
                        QuerySet(model=model).select_for_update(nowait=True).get(pk=pk)
                with (
                    self.assertRaisesMessage(OperationalError, "could not obtain lock"),
                    transaction.atomic(),
                ):
                    Screenshot.objects.select_for_update(nowait=True).get(
                        pk=self.screenshot.pk
                    )
            finally:
                connection.close()

        def add(screenshot: Screenshot, unit: Unit, user: User | None = None) -> None:
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(probe).result(timeout=10)
            original(screenshot, unit, user=user)

        with patch.object(Screenshot, "add_unit", add):
            for _ in range(2):
                request = cast(
                    "AuthenticatedHttpRequest",
                    RequestFactory().post(
                        reverse("screenshot-select", args=[self.unit.pk]),
                        {"screenshot": self.screenshot.pk},
                    ),
                )
                request.user = self.user
                self.assertEqual(
                    select_screenshot(request, self.unit.pk).status_code, 200
                )
        self.assertEqual(list(self.screenshot.units.all()), [self.unit])
        self.assertEqual(
            self.screenshot.change_set.filter(
                action=ActionEvents.SCREENSHOT_ADDED
            ).count(),
            1,
        )
