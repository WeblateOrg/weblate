# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from sys import exc_info
from unittest import mock


def immediate_on_commit(cls):
    """
    Wrapper to make transaction.on_commit execute immediately.

    This is alternative approach to TestCase.captureOnCommitCallbacks() which
    was implemented Django Ticket https://code.djangoproject.com/ticket/30457
    """

    def handle_immediate_on_commit(func, using=None):
        func()

    # Context manager executing transaction.on_commit() hooks immediately
    # This is required when using a subclass of django.test.TestCase as all tests
    # are wrapped in a transaction that never gets committed.
    cls.on_commit_mgr = mock.patch(
        "django.db.transaction.on_commit", side_effect=handle_immediate_on_commit
    )
    cls.on_commit_mgr.__enter__()


def immediate_on_commit_leave(cls):
    cls.on_commit_mgr.__exit__(*exc_info())
