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
from django.test import TransactionTestCase

from weblate.auth.models import Group
from weblate.trans.models import Project


class GroupConcurrencyTest(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = Project.objects.create(
            name="Concurrent teams", slug="concurrent-teams", web="https://example.com/"
        )

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
                deadline = monotonic() + 5
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
                        "The competing team write did not wait for the project lock"
                    )
            finally:
                release.set()
            results = [future.result(timeout=10) for future in futures]
        self.assertCountEqual(results, ["saved", "conflict"])
        self.assertEqual(
            self.project.defined_groups.filter(name="Concurrent name").count(), 1
        )

    def test_concurrent_creation(self) -> None:
        self.check_race((None, None))

    def test_concurrent_rename(self) -> None:
        first = Group.objects.create(name="First", defining_project=self.project)
        second = Group.objects.create(name="Second", defining_project=self.project)
        self.check_race((first.pk, second.pk))
