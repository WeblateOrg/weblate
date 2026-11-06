# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Current-state permission checks for unit writers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.contrib.messages.middleware import MessageMiddleware
from django.db import close_old_connections, connection, transaction
from django.http import HttpResponse
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from weblate.api.views import SuggestionViewSet, UnitViewSet
from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, Role, User
from weblate.lang.models import Language
from weblate.trans.models import Project, Suggestion, Unit
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import RepoTestMixin, clear_users_cache
from weblate.trans.views.edit import handle_merge, handle_revert
from weblate.utils.state import STATE_APPROVED, STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class UnitStateLockTest(FixtureTestCase):
    def load_before_approval(self) -> Unit:
        self.project.translation_review = True
        self.project.save(update_fields=["translation_review"])
        pk = self.get_unit().pk
        Unit.objects.filter(pk=pk).update(
            target="Unreviewed", state=STATE_TRANSLATED, original_state=STATE_TRANSLATED
        )
        stale = Unit.objects.get(pk=pk)
        self.assertTrue(self.user.has_perm("unit.edit", stale))
        Unit.objects.filter(pk=pk).update(
            target="Approved", state=STATE_APPROVED, original_state=STATE_APPROVED
        )
        self.assertFalse(self.user.has_perm("unit.edit", Unit.objects.get(pk=pk)))
        return stale

    def request(self) -> AuthenticatedHttpRequest:
        request = cast("AuthenticatedHttpRequest", self.factory.post("/"))
        request.user = self.user
        request.session = self.client.session
        MessageMiddleware(lambda _request: HttpResponse()).process_request(request)
        return request

    def assert_approval_preserved(self, unit: Unit) -> None:
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Approved")
        self.assertEqual(unit.state, STATE_APPROVED)

    def test_api_update_rechecks_locked_state(self) -> None:
        stale = self.load_before_approval()
        client = APIClient()
        client.force_authenticate(self.user)
        with patch.object(UnitViewSet, "get_object", return_value=stale):
            response = client.patch(
                reverse("api:unit-detail", kwargs={"pk": stale.pk}),
                {"target": ["Translator update"], "state": STATE_TRANSLATED},
                format="json",
            )
        self.assertEqual(response.status_code, 403, response.data)
        self.assert_approval_preserved(stale)

    def test_api_suggestion_rechecks_locked_state(self) -> None:
        stale = self.load_before_approval()
        suggestion = Suggestion.objects.create(
            unit=stale, target="Suggestion", user=self.user
        )
        client = APIClient()
        client.force_authenticate(self.user)
        with patch.object(SuggestionViewSet, "get_object", return_value=suggestion):
            response = client.post(
                reverse("api:suggestion-accept", kwargs={"pk": suggestion.pk}),
                {},
                format="json",
            )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertTrue(Suggestion.objects.filter(pk=suggestion.pk).exists())
        self.assert_approval_preserved(stale)

    def test_model_suggestion_rechecks_locked_state(self) -> None:
        stale = self.load_before_approval()
        suggestion = Suggestion.objects.create(
            unit=stale, target="Suggestion", user=self.user
        )
        suggestion.accept(self.request())
        self.assertTrue(Suggestion.objects.filter(pk=suggestion.pk).exists())
        self.assert_approval_preserved(stale)

    def test_merge_rechecks_locked_state(self) -> None:
        stale = self.load_before_approval()
        with patch("weblate.trans.views.edit.MergeForm") as form:
            form.return_value.is_valid.return_value = True
            form.return_value.cleaned_data = {"merge_unit": stale}
            self.assertIsNone(handle_merge(stale, self.request(), "/"))
        self.assert_approval_preserved(stale)

    def test_revert_rechecks_locked_state(self) -> None:
        stale = self.load_before_approval()
        with patch("weblate.trans.views.edit.RevertForm") as form:
            form.return_value.is_valid.return_value = True
            change = form.return_value.cleaned_data["revert_change"]
            self.assertIsNone(handle_revert(stale, self.request(), "/"))
            change.revert.assert_not_called()
        self.assert_approval_preserved(stale)


class UnitStateConcurrencyTest(RepoTestMixin, TransactionTestCase):
    def test_api_update_waits_for_approval_and_rechecks_permission(self) -> None:
        Language.objects.flush_object_cache()
        self.addCleanup(Language.objects.flush_object_cache)
        clear_users_cache()
        self.addCleanup(clear_users_cache)
        self.clone_test_repos()
        component = self.create_component()
        Project.objects.filter(pk=component.project_id).update(translation_review=True)
        user = User.objects.create_user("racing-translator", "translator@example.org")
        group = Group.objects.create(
            name="Race translators", language_selection=SELECTION_ALL
        )
        group.projects.add(component.project)
        group.roles.add(Role.objects.get(name="Translate"))
        user.groups.add(group)
        unit = component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        Unit.objects.filter(pk=unit.pk).update(
            target="Unreviewed", state=STATE_TRANSLATED, original_state=STATE_TRANSLATED
        )
        pids: Queue[int] = Queue()

        def update() -> int:
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids.put(cursor.fetchone()[0])
                client = APIClient()
                client.force_authenticate(user)
                response = client.patch(
                    reverse("api:unit-detail", kwargs={"pk": unit.pk}),
                    {"target": ["Translator update"], "state": STATE_TRANSLATED},
                    format="json",
                )
                return response.status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                Unit.objects.select_for_update().get(pk=unit.pk)
                Unit.objects.filter(pk=unit.pk).update(
                    target="Approved",
                    state=STATE_APPROVED,
                    original_state=STATE_APPROVED,
                )
                future = executor.submit(update)
                pid = pids.get(timeout=10)
                deadline = monotonic() + 4
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT cardinality(pg_blocking_pids(%s)) > 0", [pid]
                        )
                        if cursor.fetchone()[0]:
                            break
                    sleep(0.01)
                else:
                    self.fail(
                        "Translator request did not wait for the approving transaction"
                    )
            self.assertEqual(future.result(timeout=10), 403)
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Approved")
        self.assertEqual(unit.state, STATE_APPROVED)
