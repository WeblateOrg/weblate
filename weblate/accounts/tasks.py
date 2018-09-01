# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import absolute_import, unicode_literals

from datetime import timedelta
import time

from django.conf import settings
from django.utils.timezone import now

from social_django.models import Partial, Code

from weblate.celery import app


@app.task
def cleanup_social_auth():
    """Cleanup expired partial social authentications."""
    for partial in Partial.objects.all():
        kwargs = partial.data['kwargs']
        if ('weblate_expires' not in kwargs or
                kwargs['weblate_expires'] < time.time()):
            # Old entry without expiry set, or expired entry
            partial.delete()

    age = now() + timedelta(seconds=settings.AUTH_TOKEN_VALID)
    # Delete old not verified codes
    Code.objects.filter(
        verified=False,
        timestamp__lt=age
    ).delete()

    # Delete old partial data
    Partial.objects.filter(
        timestamp__lt=age
    ).delete()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600,
        cleanup_social_auth.s(),
        name='social-auth-cleanup',
    )
