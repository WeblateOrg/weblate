#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from sys import exc_info
from unittest import mock


def immediate_on_commit(cls):
    """Wrapper to make transaction.on_commit execute immediately.

    TODO: Remove when immediate_on_commit function is actually implemented
    Django Ticket #: 30456, Link: https://code.djangoproject.com/ticket/30457#no1
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
