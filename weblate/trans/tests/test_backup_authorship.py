# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Consent races retain content authorship without changing initiating actors."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from weblate.auth.models import Group, Invitation, User, get_anonymous
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.models import (
    BackupAuthorClaim,
    BackupAuthorVote,
    Change,
    Component,
    Project,
    Suggestion,
    Translation,
    Unit,
    Vote,
)
from weblate.trans.models.backup import backup_author_context
from weblate.trans.tests.utils import clear_users_cache


class BackupAuthorshipConcurrencyTest(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        clear_users_cache()
        self.addCleanup(clear_users_cache)

    def check_consent_race(self, insert_before_accept: bool) -> None:
        actor = User.objects.create_user("backup-importer", "importer@example.org")
        author = User.objects.create_user("backup-author", "author@example.org")
        project = Project.objects.create(
            name="Claim race", slug="claim-race", web="https://example.org/"
        )
        team = Group.objects.create(name="Imported authors", defining_project=project)
        invitation = Invitation.objects.create(
            author=actor, user=author, group=team, backup_authorship=True
        )
        claim = BackupAuthorClaim.objects.create(
            project=project, user=author, invitation=invitation
        )
        ready = Event()
        release = Event()

        def consume() -> int:
            close_old_connections()
            try:
                with backup_author_context(claim.pk, project.pk):
                    change = Change(
                        project=project,
                        user=actor,
                        author=get_anonymous(),
                        action=ActionEvents.CHANGE,
                    )
                    if insert_before_accept:
                        change.save()
                    ready.set()
                    self.assertTrue(release.wait(timeout=10))
                    if not insert_before_accept:
                        change.save()
                    return change.pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(consume)
            try:
                self.assertTrue(ready.wait(timeout=10))
                invitation.accept(None, author)
            finally:
                release.set()
            pk = future.result(timeout=10)
        change = Change.objects.get(pk=pk)
        self.assertEqual(change.author, author)
        self.assertEqual(change.user, actor)
        claim.refresh_from_db()
        self.assertIsNotNone(claim.accepted_at)

    def test_consent_while_consumption_is_preparing_history(self) -> None:
        self.check_consent_race(insert_before_accept=False)

    def test_consent_while_consumption_has_uncommitted_history(self) -> None:
        self.check_consent_race(insert_before_accept=True)

    def test_concurrent_vote_claims_retire_shared_anonymous_votes(self) -> None:
        project = Project.objects.create(
            name="Vote race", slug="vote-race", web="https://example.org/"
        )
        language = Language.objects.get(code="en")
        # This race only needs relational state; no repository operations run.
        component = Component.objects.bulk_create(
            [
                Component(
                    project=project,
                    name="Votes",
                    slug="votes",
                    repo="local:",
                    filemask="*.po",
                    file_format="po",
                    source_language=language,
                )
            ]
        )[0]
        translation = Translation.objects.bulk_create(
            [
                Translation(
                    component=component,
                    language=language,
                    plural=language.plural,
                    filename="en.po",
                    language_code="en",
                )
            ]
        )[0]
        unit = Unit.objects.bulk_create(
            [Unit(translation=translation, source="Vote", position=1, id_hash=1)]
        )[0]
        authors = [
            User.objects.create_user(f"voter-{index}", f"voter-{index}@example.org")
            for index in range(2)
        ]
        claims = [
            BackupAuthorClaim.objects.create(
                project=project, user=user, accepted_at=timezone.now()
            )
            for user in authors
        ]
        suggestions = [
            Suggestion.objects.create(
                unit=unit,
                user=get_anonymous(),
                target=f"target {index}",
                backup_author_claim=claim,
            )
            for index, claim in enumerate(claims)
        ]
        for suggestion in suggestions:
            placeholder = Vote.objects.create(
                suggestion=suggestion, user=get_anonymous(), value=1
            )
            for index, claim in enumerate(claims):
                BackupAuthorVote.objects.create(
                    claim=claim,
                    suggestion=suggestion,
                    placeholder=placeholder,
                    value=1 if index == 0 else -1,
                )
        barrier = Barrier(2)

        def reconcile(claim: BackupAuthorClaim) -> None:
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                claim.reconcile()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(reconcile, claim) for claim in claims]
            for future in futures:
                future.result(timeout=10)
        for suggestion in suggestions:
            self.assertCountEqual(
                suggestion.vote_set.values_list("user_id", "value"),
                [(authors[0].pk, 1), (authors[1].pk, -1)],
            )
        self.assertFalse(BackupAuthorVote.objects.filter(claim__in=claims).exists())
