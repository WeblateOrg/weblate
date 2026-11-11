# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Project-scoped team name serialization."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier, Event
from time import monotonic, sleep

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.http import Http404
from django.test import TransactionTestCase

from weblate.auth.audit import audit_team_changes
from weblate.auth.models import (
    Group,
    Invitation,
    InvitationRemovedError,
    TeamMembership,
    User,
)
from weblate.trans.models import Project
from weblate.trans.views.acl import lock_project_member
from weblate.utils.change_origin import acting_user_context


class GroupConcurrencyTest(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = Project.objects.create(
            name="Concurrent teams", slug="concurrent-teams", web="https://example.com/"
        )

    def wait_for_blocked_connection(self, pid: int) -> None:
        deadline = monotonic() + 5
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT cardinality(pg_blocking_pids(%s)) > 0", [pid])
                if cursor.fetchone()[0]:
                    return
            sleep(0.01)
        self.fail("The competing operation did not wait for the audit locks")

    def check_race(self, group_ids: tuple[int | None, int | None]) -> None:
        barrier = Barrier(2)
        first_saved = Event()
        release = Event()
        blocked_pid: Queue[int] = Queue()

        def save_group(position: int, group_id: int | None) -> str:
            close_old_connections()
            try:
                group = (
                    Group.objects.get(pk=group_id)
                    if group_id
                    else Group(defining_project_id=self.project.pk)
                )
                group.name = "Concurrent name"
                group.clean()
                barrier.wait(timeout=10)
                if position == 0:
                    with transaction.atomic():
                        group.save()
                        first_saved.set()
                        self.assertTrue(release.wait(timeout=10))
                else:
                    self.assertTrue(first_saved.wait(timeout=10))
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_backend_pid()")
                        blocked_pid.put(cursor.fetchone()[0])
                    try:
                        group.save()
                    except ValidationError as error:
                        self.assertIn("name", error.message_dict)
                        return "conflict"
                return "saved"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(save_group, position, group_id)
                for position, group_id in enumerate(group_ids)
            ]
            try:
                pid = blocked_pid.get(timeout=10)
                self.wait_for_blocked_connection(pid)
            finally:
                release.set()
            results = [future.result(timeout=10) for future in futures]
        self.assertCountEqual(results, ["saved", "conflict"])
        self.assertEqual(
            self.project.defined_groups.filter(name="Concurrent name").count(), 1
        )

    def test_concurrent_creation(self) -> None:
        self.check_race((None, None))

    def test_project_member_removal_waits_before_locking_memberships(self) -> None:
        actor = User.objects.create_user("audit-manager", "manager@example.org")
        member = User.objects.create_user("audit-member", "member@example.org")
        team = Group.objects.create(
            name="Concurrent removal", defining_project=self.project
        )
        membership = TeamMembership.objects.create(user=member, group=team)
        editing = Event()
        release = Event()
        removal_pid: Queue[int] = Queue()

        def edit_team() -> str:
            close_old_connections()
            try:
                with acting_user_context(actor), audit_team_changes(team, actor):
                    editing.set()
                    self.assertTrue(release.wait(timeout=10))
                    member.remove_team(None, team)
                return "removed from team"
            finally:
                connection.close()

        def remove_project_member() -> str:
            close_old_connections()
            try:
                self.assertTrue(editing.wait(timeout=10))
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    removal_pid.put(cursor.fetchone()[0])
                with transaction.atomic(), acting_user_context(actor):
                    try:
                        locked_member = lock_project_member(self.project, member)
                    except Http404:
                        return "already removed"
                    self.project.remove_user(locked_member)
                return "removed from project"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(edit_team),
                executor.submit(remove_project_member),
            ]
            try:
                pid = removal_pid.get(timeout=10)
                self.wait_for_blocked_connection(pid)
                # A waiting project removal must leave the membership available
                # to the team operation holding the project and team locks.
                with transaction.atomic():
                    TeamMembership.objects.select_for_update(nowait=True).get(
                        pk=membership.pk
                    )
            finally:
                release.set()
            results = [future.result(timeout=10) for future in futures]
        self.assertCountEqual(results, ["removed from team", "already removed"])
        self.assertFalse(TeamMembership.objects.filter(pk=membership.pk).exists())

    def test_concurrent_rename(self) -> None:
        first = Group.objects.create(name="First", defining_project=self.project)
        second = Group.objects.create(name="Second", defining_project=self.project)
        self.check_race((first.pk, second.pk))

    def test_invitation_acceptance_waits_before_locking_invitation(self) -> None:
        actor = User.objects.create_user("invitation-manager", "manager@example.org")
        member = User.objects.create_user("invitation-member", "member@example.org")
        team = Group.objects.create(
            name="Concurrent deletion", defining_project=self.project
        )
        team_id = team.pk
        invitation = Invitation.objects.create(
            author=actor, user=member, group=team, team_admin=True
        )
        deleting = Event()
        release = Event()
        acceptance_pid: Queue[int] = Queue()

        def delete_team() -> str:
            close_old_connections()
            try:
                with acting_user_context(actor), audit_team_changes(team, actor):
                    deleting.set()
                    self.assertTrue(release.wait(timeout=10))
                    team.delete()
                return "team deleted"
            finally:
                connection.close()

        def accept_invitation() -> str:
            close_old_connections()
            try:
                self.assertTrue(deleting.wait(timeout=10))
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    acceptance_pid.put(cursor.fetchone()[0])
                try:
                    invitation.accept(None, member)
                except InvitationRemovedError:
                    return "invitation removed"
                return "accepted"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(delete_team), executor.submit(accept_invitation)]
            try:
                pid = acceptance_pid.get(timeout=10)
                self.wait_for_blocked_connection(pid)
                # Deleting the team must remain able to cascade to this row.
                with transaction.atomic():
                    Invitation.objects.select_for_update(nowait=True).get(
                        pk=invitation.pk
                    )
            finally:
                release.set()
            results = [future.result(timeout=10) for future in futures]
        self.assertCountEqual(results, ["team deleted", "invitation removed"])
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())
        self.assertFalse(
            TeamMembership.objects.filter(user=member, group_id=team_id).exists()
        )
