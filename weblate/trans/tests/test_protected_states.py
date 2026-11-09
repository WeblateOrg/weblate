# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Permissions for copied states and vote-driven suggestion acceptance."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.http import HttpResponse
from django.urls import reverse
from rest_framework.test import APIClient

from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component, Suggestion, Unit, Vote
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.views.edit import handle_merge, handle_revert
from weblate.utils.state import STATE_APPROVED, STATE_READONLY, STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.utils.state import StringState


class ProtectedStateTransitionTest(FixtureTestCase):
    def request(
        self, data: dict[str, int] | None = None, *, user: User | None = None
    ) -> AuthenticatedHttpRequest:
        request = cast("AuthenticatedHttpRequest", self.factory.post("/", data or {}))
        request.user = user or self.user
        request.session = self.client.session
        MessageMiddleware(lambda _request: HttpResponse()).process_request(request)
        return request

    def destination(self, *, voting: bool = False, review: bool = True) -> Unit:
        self.project.translation_review = review
        self.project.save(update_fields=["translation_review"])
        Component.objects.filter(pk=self.component.pk).update(
            suggestion_voting=voting, suggestion_autoaccept=2 if voting else 0
        )
        pk = self.get_unit().pk
        Unit.objects.filter(pk=pk).update(
            target="Current translation\n",
            state=STATE_TRANSLATED,
            original_state=STATE_TRANSLATED,
        )
        return Unit.objects.get(pk=pk)

    def check_merge(
        self, state: StringState, expected: StringState, *, review: bool = True
    ) -> None:
        unit = self.destination(review=review)
        peer = self.create_po(name="Peer", slug="peer", project=self.project)
        merged = peer.translation_set.get(
            language=unit.translation.language
        ).unit_set.get(source=unit.source)
        Unit.objects.filter(pk=merged.pk).update(
            target="Copied translation\n", state=state
        )

        response = handle_merge(unit, self.request({"merge": merged.pk}), "/")

        self.assertIsNotNone(response)
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Copied translation\n")
        self.assertEqual(unit.state, expected)

    def check_revert(
        self, state: StringState, expected: StringState, *, review: bool = True
    ) -> None:
        unit = self.destination(review=review)
        change = unit.change_set.create(
            action=ActionEvents.CHANGE,
            user=self.user,
            old="Previous translation\n",
            target=unit.target,
            details={"old_state": state},
        )

        response = handle_revert(unit, self.request({"revert": change.pk}), "/")

        self.assertIsNotNone(response)
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Previous translation\n")
        self.assertEqual(unit.state, expected)

    def test_merge_readonly_becomes_translated(self) -> None:
        self.check_merge(STATE_READONLY, STATE_TRANSLATED)

    def test_revert_readonly_becomes_translated(self) -> None:
        self.check_revert(STATE_READONLY, STATE_TRANSLATED)

    def test_merge_approved_requires_review_permission(self) -> None:
        self.check_merge(STATE_APPROVED, STATE_TRANSLATED)

    def test_revert_approved_requires_review_permission(self) -> None:
        self.check_revert(STATE_APPROVED, STATE_TRANSLATED)

    def test_reviewer_merge_preserves_approval(self) -> None:
        self.make_manager()
        self.check_merge(STATE_APPROVED, STATE_APPROVED)

    def test_reviewer_revert_preserves_approval(self) -> None:
        self.make_manager()
        self.check_revert(STATE_APPROVED, STATE_APPROVED)

    def test_reviewer_cannot_copy_readonly(self) -> None:
        self.make_manager()
        self.check_merge(STATE_READONLY, STATE_TRANSLATED)

    def test_merge_approval_requires_enabled_reviews(self) -> None:
        self.make_manager()
        self.check_merge(STATE_APPROVED, STATE_TRANSLATED, review=False)

    def test_revert_approval_requires_enabled_reviews(self) -> None:
        self.make_manager()
        self.check_revert(STATE_APPROVED, STATE_TRANSLATED, review=False)

    def test_bulk_user_revert_does_not_copy_readonly(self) -> None:
        unit = self.destination()
        change = unit.change_set.create(
            action=ActionEvents.CHANGE,
            user=self.user,
            old="Previous translation\n",
            target=unit.target,
            details={"old_state": STATE_READONLY},
        )

        self.assertTrue(change.revert_user_edits(self.user))

        unit.refresh_from_db()
        self.assertEqual(unit.target, "Previous translation\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)

    def vote_through_api(self, state: StringState) -> tuple[Unit, int]:
        unit = self.destination(voting=True)
        Unit.objects.filter(pk=unit.pk).update(state=state, original_state=state)
        unit.refresh_from_db()
        self.assertFalse(self.user.has_perm("unit.review", unit))
        self.assertFalse(self.user.has_perm("suggestion.accept", unit))
        self.assertTrue(self.user.has_perm("suggestion.vote", unit))
        suggestion = Suggestion.objects.create(
            unit=unit, target="Voted translation\n", user=self.anotheruser
        )
        pk = suggestion.pk
        Vote.objects.create(
            suggestion=suggestion, user=self.anotheruser, value=Vote.POSITIVE
        )
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.post(
            reverse("api:suggestion-vote", kwargs={"pk": pk}),
            {"value": Vote.POSITIVE},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        unit.refresh_from_db()
        return unit, pk

    def test_vote_can_replace_approved_translation(self) -> None:
        unit, pk = self.vote_through_api(STATE_APPROVED)

        self.assertFalse(Suggestion.objects.filter(pk=pk).exists())
        self.assertEqual(unit.target, "Voted translation\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)
        change = unit.change_set.get(action=ActionEvents.ACCEPT)
        self.assertEqual(change.user, self.user)
        self.assertEqual(change.author, self.anotheruser)

    def test_vote_keeps_readonly_string_and_pending_suggestion(self) -> None:
        unit, pk = self.vote_through_api(STATE_READONLY)

        self.assertTrue(Suggestion.objects.filter(pk=pk).exists())
        self.assertEqual(Vote.objects.filter(suggestion_id=pk).count(), 2)
        self.assertEqual(unit.target, "Current translation\n")
        self.assertEqual(unit.state, STATE_READONLY)
        self.assertFalse(unit.change_set.filter(action=ActionEvents.ACCEPT).exists())

    def test_automatic_acceptance_rechecks_readonly_after_lookup(self) -> None:
        unit = self.destination(voting=True)
        suggestion = Suggestion.objects.create(
            unit=unit, target="Voted translation\n", user=self.user
        )
        Vote.objects.create(
            suggestion=suggestion, user=self.anotheruser, value=Vote.POSITIVE
        )
        Unit.objects.filter(pk=unit.pk).update(
            state=STATE_READONLY, original_state=STATE_READONLY
        )
        request = self.request()

        suggestion.add_vote(request, Vote.POSITIVE)

        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_READONLY)
        self.assertEqual(unit.target, "Current translation\n")
        self.assertTrue(Suggestion.objects.filter(pk=suggestion.pk).exists())
        self.assertEqual(suggestion.get_num_votes(override=True), 2)
        self.assertEqual(list(get_messages(request)), [])
