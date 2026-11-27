# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.urls import reverse
from django.utils.timezone import now

from weblate.accounts.models import AccountActivity
from weblate.accounts.notifications import get_notification_emails
from weblate.accounts.tasks import queue_mails
from weblate.accounts.utils import remove_user
from weblate.auth.bots import InternalBot
from weblate.auth.models import User
from weblate.trans.models import Change
from weblate.utils.change_origin import acting_user_context
from weblate.utils.errors import report_error

if TYPE_CHECKING:
    from datetime import datetime

    from django.db.models import QuerySet

    from weblate.accounts.tasks import OutgoingEmail

BATCH_SIZE = 200
ACTIVITY_REFRESH_SECONDS = 3600
WARNING_PERIOD = timedelta(days=30)
REMINDER_PERIOD = timedelta(days=5)


def account_expiry_days() -> int:
    days = settings.INACTIVE_ACCOUNT_EXPIRY
    return (
        days if isinstance(days, int) and not isinstance(days, bool) and days > 0 else 0
    )


def can_expire_account(user: User, timestamp: datetime) -> bool:
    return (
        user.is_active
        and not user.is_anonymous
        and not user.is_bot
        and not user.is_superuser
        and bool(user.email)
        and (user.date_expires is None or user.date_expires > timestamp)
    )


def record_account_activity(user: User, *, record: bool = True) -> bool:
    """Record use and reject an account removed during the locked refresh."""
    if not account_expiry_days():
        return True
    timestamp = now()
    if not can_expire_account(user, timestamp):
        return True
    cache_key = f"account-activity:{user.pk}"
    if cache.get(cache_key):
        return True

    with transaction.atomic():
        # Serialize the activity write with the final eligibility check.
        current = User.objects.select_for_update(no_key=True).filter(pk=user.pk).first()
        if current is None or not current.is_active:
            return False
        if not record or not can_expire_account(current, timestamp):
            return True
        state, _created = AccountActivity.objects.get_or_create(user=current)
        last_activity = state.last_activity
        if (
            state.removal_at is not None
            or last_activity is None
            or last_activity <= timestamp - timedelta(seconds=ACTIVITY_REFRESH_SECONDS)
        ):
            last_activity = max(last_activity or timestamp, timestamp)
            state.last_activity = last_activity
            state.removal_at = None
            state.reminded = False
            state.save(update_fields=["last_activity", "removal_at", "reminded"])
        # A second request might have just updated the database after our cache
        # miss. Expire the cache relative to the stored timestamp in either case.
        timeout = ACTIVITY_REFRESH_SECONDS - int(
            (timestamp - last_activity).total_seconds()
        )
        transaction.on_commit(lambda: cache.set(cache_key, True, timeout))
    return True


def old_activity(cutoff: datetime) -> Q:
    return (
        Q(last_login__lte=cutoff) | Q(last_login__isnull=True, date_joined__lte=cutoff)
    ) & (
        Q(activity_state__last_activity__isnull=True)
        | Q(activity_state__last_activity__lte=cutoff)
    )


def change_activity(user_id: int | OuterRef) -> QuerySet:
    # The leading fields of trans_change_user_idx support this ordered probe.
    # Authorship can describe someone other than the user who performed the action.
    return (
        Change.objects.filter(user_id=user_id)
        .order_by("-timestamp")
        .values_list("timestamp", flat=True)
    )


def historical_activity(user_ids: list[int], cutoff: datetime) -> QuerySet:
    return (
        User.objects.filter(old_activity(cutoff), pk__in=user_ids)
        .annotate(last_change=Subquery(change_activity(OuterRef("pk"))[:1]))
        .order_by()
        .values_list("pk", "last_change")
    )


def get_removal_notice(
    user: User, state: AccountActivity, *, final: bool = False
) -> list[OutgoingEmail]:
    return get_notification_emails(
        user.profile.language,
        [cast("str", user.email)],
        "inactive_account",
        context={
            "removal_at": state.removal_at,
            "reminder": state.reminded,
            "final": final,
            "login_url": reverse("login"),
        },
        info="inactive account removal",
        user=user,
    )


def get_inactive_state(
    user: User,
    last_change: datetime | None,
    timestamp: datetime,
    cutoff: datetime,
) -> AccountActivity | None:
    """Merge activity and check eligibility while the account row is locked."""
    state = AccountActivity.objects.filter(user=user).first()
    if state is None:
        state = AccountActivity(user=user)
    if can_expire_account(user, timestamp):
        if last_change is not None and (
            state.last_activity is None or last_change > state.last_activity
        ):
            state.last_activity = last_change
            state.save()
        last_login = user.last_login or user.date_joined
        if max(last_login, state.last_activity or last_login) <= cutoff:
            return state
    if state.removal_at is not None:
        state.removal_at = None
        state.reminded = False
        state.save(update_fields=["removal_at", "reminded"])
    return None


@transaction.atomic
def check_account(
    user_id: int, last_change: datetime | None, cutoff: datetime
) -> User | None:
    user = (
        User.objects.select_related("profile")
        .select_for_update(of=("self",), no_key=True)
        .filter(pk=user_id)
        .first()
    )
    if user is None:
        return None
    timestamp = now()
    state = get_inactive_state(user, last_change, timestamp, cutoff)
    if state is None:
        return None
    if state.removal_at is not None:
        if state.reminded:
            return user if state.removal_at <= timestamp else None
        if state.removal_at > timestamp + REMINDER_PERIOD:
            return None

    # The batched lookup may predate a change committed before we locked the user.
    if recent_change := change_activity(user.pk).filter(timestamp__gt=cutoff).first():
        get_inactive_state(user, recent_change, timestamp, cutoff)
        return None

    if state.removal_at is None:
        state.removal_at = timestamp + WARNING_PERIOD
        state.save()
    else:
        state.removal_at = timestamp + REMINDER_PERIOD
        state.reminded = True
        state.save(update_fields=["removal_at", "reminded"])
    # Advance the schedule only after publishing to the best-effort mail queue.
    queue_mails(get_removal_notice(user, state))
    return None


def confirm_inactive_removal(user: User, cutoff: datetime) -> bool:
    """Recheck after the repository flush, within the removal transaction."""
    timestamp = now()
    state = get_inactive_state(
        user, change_activity(user.pk).first(), timestamp, cutoff
    )
    if (
        state is None
        or not state.reminded
        or state.removal_at is None
        or state.removal_at > timestamp
    ):
        return False
    notice = get_removal_notice(user, state, final=True)

    def publish_notice() -> None:
        queue_mails(notice)

    transaction.on_commit(publish_notice, robust=True)
    return True


def check_inactive_accounts() -> None:
    days = account_expiry_days()
    if not days:
        AccountActivity.objects.filter(removal_at__isnull=False).update(
            removal_at=None, reminded=False
        )
        return

    timestamp = now()
    # A throttled request can be newer than the recorded timestamp by this much.
    cutoff = timestamp - timedelta(days=days, seconds=ACTIVITY_REFRESH_SECONDS)
    candidates = User.objects.filter(
        Q(activity_state__removal_at__isnull=False)
        | (
            Q(is_active=True, is_bot=False, is_superuser=False, email__isnull=False)
            & ~Q(email="")
            & ~Q(username=settings.ANONYMOUS_USER_NAME)
            & (Q(date_expires__isnull=True) | Q(date_expires__gt=timestamp))
            & old_activity(cutoff)
        )
    ).order_by("pk")
    last_pk = 0
    while user_ids := list(
        candidates.filter(pk__gt=last_pk).values_list("pk", flat=True)[:BATCH_SIZE]
    ):
        recent_changes = dict(historical_activity(user_ids, cutoff))
        for user_id in user_ids:
            try:
                if user := check_account(user_id, recent_changes.get(user_id), cutoff):
                    actor = InternalBot.ACCOUNT_CLEANUP.get_user()
                    with acting_user_context(actor):
                        remove_user(
                            user,
                            None,
                            actor=actor,
                            skip_notify=True,
                            can_remove=partial(confirm_inactive_removal, cutoff=cutoff),
                        )
            except Exception:
                report_error(
                    "Error checking account inactivity", extra_log=f"user_id={user_id}"
                )
        last_pk = user_ids[-1]
