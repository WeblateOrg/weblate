# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import mock


def immediate_on_commit(cls) -> None:
    """
    Execute transaction.on_commit immediately.

    This is alternative approach to TestCase.captureOnCommitCallbacks() which
    was implemented Django Ticket https://code.djangoproject.com/ticket/30457
    """

    def handle_immediate_on_commit(func, using=None) -> None:
        func()

    # Context manager executing transaction.on_commit() hooks immediately
    # This is required when using a subclass of django.test.TestCase as all tests
    # are wrapped in a transaction that never gets committed.
    cls.on_commit_mgr = mock.patch(
        "django.db.transaction.on_commit", side_effect=handle_immediate_on_commit
    )
    cls.on_commit_mgr.start()


def immediate_on_commit_leave(cls) -> None:
    cls.on_commit_mgr.stop()
