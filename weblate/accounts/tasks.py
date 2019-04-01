# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
from django.core.exceptions import ObjectDoesNotExist
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


@app.task
def cleanup_auditlog():
    """Cleanup old auditlog entries."""
    from weblate.accounts.models import AuditLog
    AuditLog.objects.filter(
        timestamp__lt=now() - timedelta(days=settings.AUDITLOG_EXPIRY)
    ).delete()


# Retry for not existing object (maybe transaction not yet committed) with
# delay of 10 minutes growing exponentially
@app.task(autoretry_for=(ObjectDoesNotExist,), retry_backoff=600)
def notify_change(change_id):
    from weblate.trans.models import Change
    from weblate.accounts.notifications import (
        notify_merge_failure, notify_parse_error, notify_new_string,
        notify_new_contributor, notify_new_suggestion, notify_new_comment,
        notify_new_translation, notify_new_language,
    )
    change = Change.objects.get(pk=change_id)
    if change.action in (Change.ACTION_FAILED_MERGE, Change.ACTION_FAILED_REBASE):
        notify_merge_failure(change)
    elif change.action == Change.ACTION_PARSE_ERROR:
        notify_parse_error(change)
    elif change.action == Change.ACTION_NEW_STRING:
        notify_new_string(change)
    elif change.action == Change.ACTION_NEW_CONTRIBUTOR:
        notify_new_contributor(change)
    elif change.action == Change.ACTION_SUGGESTION:
        notify_new_suggestion(change)
    elif change.action == Change.ACTION_COMMENT:
        notify_new_comment(change)
    elif change.action in Change.ACTIONS_CONTENT:
        notify_new_translation(change)
    elif change.action in (Change.ACTION_ADDED_LANGUAGE, Change.ACTION_REQUESTED_LANGUAGE):
        notify_new_language(change)


@app.task(autoretry_for=(ObjectDoesNotExist,))
def notify_auditlog(log_id):
    from weblate.accounts.models import AuditLog
    from weblate.accounts.notifications import send_notification_email
    audit = AuditLog.objects.get(pk=log_id)
    send_notification_email(
        audit.user.profile.language,
        audit.user.email,
        'account_activity',
        context={
            'message': audit.get_message,
            'extra_message': audit.get_extra_message,
            'address': audit.address,
            'user_agent': audit.user_agent,
        },
        info='{0} from {1}'.format(audit.activity, audit.address),
    )


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600,
        cleanup_social_auth.s(),
        name='social-auth-cleanup',
    )
    sender.add_periodic_task(
        3600,
        cleanup_auditlog.s(),
        name='auditlog-cleanup',
    )
