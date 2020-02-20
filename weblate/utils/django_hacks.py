# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from django.utils.translation import trans_real

try:
    from unittest import mock
except ImportError:
    import mock

DjangoTranslation = trans_real.DjangoTranslation


class WeblateTranslation(DjangoTranslation):
    """Workaround to enforce our plural forms over Django ones.

    We hook into merge and overwrite plural with each merge. As Weblate locales
    load as last this way we end up using Weblate plurals.

    When loading locales, Django uses it's own plural forms for all
    localizations. This can break plurals for other applications as they can
    have different plural form. We don't use much of Django messages in the UI
    (with exception of the admin interface), so it's better to possibly break
    Django translations rather than breaking our own ones.

    See https://code.djangoproject.com/ticket/30439
    """

    def merge(self, other):
        DjangoTranslation.merge(self, other)
        # Override plural
        if hasattr(other, 'plural'):
            self.plural = other.plural


def monkey_patch_translate():
    """Monkey patch translation to workaround Django bug in handling plurals."""
    trans_real.DjangoTranslation = WeblateTranslation


def immediate_on_commit(cls):
    """Wrapper to make transaction.on_commit execute immediatelly.

    TODO: Remove when immediate_on_commit function is actually implemented
    Django Ticket #: 30456, Link: https://code.djangoproject.com/ticket/30457#no1
    """

    def handle_immediate_on_commit(func, using=None):
        func()

    # Context manager executing transaction.on_commit() hooks immediately
    # This is required when using a subclass of django.test.TestCase as all tests
    # are wrapped in a transaction that never gets committed.
    cls.on_commit_mgr = mock.patch(
        'django.db.transaction.on_commit', side_effect=handle_immediate_on_commit
    )
    cls.on_commit_mgr.__enter__()


def immediate_on_commit_leave(cls):
    cls.on_commit_mgr.__exit__()
