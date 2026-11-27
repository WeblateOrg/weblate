# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.contrib.auth import SESSION_KEY, login
from django.core import mail
from django.core.cache import cache
from django.db import connection, connections, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.request import Request

from weblate.accounts.inactivity import (
    check_account,
    historical_activity,
    record_account_activity,
)
from weblate.accounts.models import AccountActivity, TeamAuditLog
from weblate.accounts.tasks import cleanup_auditlog, cleanup_inactive_accounts
from weblate.accounts.utils import SESSION_EXPIRY_SCOPE_2FA, remove_user
from weblate.api.authentication import WeblateTokenAuthentication
from weblate.auth.bots import InternalBot
from weblate.auth.models import Group, Invitation, User
from weblate.gitexport.views import authenticate as authenticate_git
from weblate.trans.models import Change
from weblate.utils.change_origin import acting_user_context, change_origin_context

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from weblate.accounts.tasks import OutgoingEmail
    from weblate.auth.models import AuthenticatedHttpRequest


@override_settings(INACTIVE_ACCOUNT_EXPIRY=365, AUDITLOG_EXPIRY=1)
class InactiveAccountTest(TestCase):
    timestamp: datetime
    old: datetime
    user: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.timestamp = timezone.now()
        cls.old = cls.timestamp - timedelta(days=400)
        cls.user = cls.create_user("stale")

    @classmethod
    def create_user(cls, username: str, **kwargs: object) -> User:
        return User.objects.create_user(
            username,
            kwargs.pop("email", f"{username}@example.org"),
            "password",
            date_joined=cls.old,
            **kwargs,
        )

    def run_check(self, days: int = 0) -> None:
        with (
            patch(
                "weblate.accounts.inactivity.now",
                return_value=self.timestamp + timedelta(days=days),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            cleanup_inactive_accounts()

    def add_change(
        self, user: User, days: int, *, author: User | None = None
    ) -> Change:
        change = Change.objects.create(user=user, author=author)
        Change.objects.filter(pk=change.pk).update(
            timestamp=self.timestamp - timedelta(days=days)
        )
        return change

    def test_removal(self) -> None:
        original_email = self.user.email
        team = Group.objects.create(name="Account removal team")
        self.user.add_team(None, team)
        change = self.add_change(self.user, 399)
        self.run_check()
        self.run_check()
        state = AccountActivity.objects.get(user=self.user)
        self.assertEqual(state.removal_at, self.timestamp + timedelta(days=30))
        self.assertFalse(state.reminded)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [original_email])
        self.assertIn("sign in or use your Weblate API token", mail.outbox[0].body)

        with patch(
            "weblate.accounts.tasks.now",
            return_value=self.timestamp + timedelta(days=25),
        ):
            cleanup_auditlog()
        self.run_check(25)
        self.run_check(25)
        state.refresh_from_db()
        self.assertTrue(state.reminded)
        self.assertIn("Reminder", mail.outbox[1].subject)

        self.run_check(29)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.run_check(30)
        self.run_check(31)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.username, f"deleted-{self.user.pk}")
        self.assertFalse(self.user.has_usable_password())
        self.assertFalse(AccountActivity.objects.filter(user=self.user).exists())
        change.refresh_from_db()
        self.assertEqual(change.user, self.user)
        self.assertFalse(
            User.objects.filter(pk=self.user.pk, auth_token__isnull=False).exists()
        )
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(mail.outbox[2].to, [original_email])
        self.assertIn("removed due to inactivity", mail.outbox[2].body)
        audit = self.user.auditlog_set.get(activity="removed")
        self.assertEqual(audit.params["email"], original_email)
        actor = InternalBot.ACCOUNT_CLEANUP.get_user()
        self.assertEqual(audit.params["username"], actor.username)
        membership_audit = self.user.auditlog_set.get(
            activity="sitewide-team-remove", params__team=team.name
        )
        self.assertEqual(membership_audit.params["username"], actor.username)
        self.assertEqual(
            TeamAuditLog.objects.get(
                team=team, event=TeamAuditLog.Event.MEMBER_REMOVED
            ).actor,
            actor,
        )

    def test_late_reminder_postpones_removal(self) -> None:
        self.run_check()
        self.run_check(32)
        state = AccountActivity.objects.get(user=self.user)
        self.assertEqual(state.removal_at, self.timestamp + timedelta(days=37))
        self.assertEqual(len(mail.outbox), 2)
        self.run_check(36)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.run_check(37)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_exempt_accounts_and_recent_login(self) -> None:
        excluded = [
            self.create_user("disabled", is_active=False),
            self.create_user("expired", date_expires=self.old),
            self.create_user("robot", is_bot=True),
            self.create_user("administrator", is_superuser=True),
            self.create_user("no-address", email=None),
            self.create_user("recent-login", last_login=self.timestamp),
        ]
        self.run_check()
        self.assertFalse(AccountActivity.objects.filter(user__in=excluded).exists())
        self.assertTrue(AccountActivity.objects.filter(user=self.user).exists())

    def test_policy_change_clears_pending_removal(self) -> None:
        self.run_check()
        with override_settings(INACTIVE_ACCOUNT_EXPIRY=450):
            self.run_check(30)
        state = AccountActivity.objects.get(user=self.user)
        self.assertIsNone(state.removal_at)
        self.run_check(30)
        with override_settings(INACTIVE_ACCOUNT_EXPIRY=0):
            self.run_check(100)
        state.refresh_from_db()
        self.assertIsNone(state.removal_at)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_manual_removal_clears_pending_state(self) -> None:
        self.run_check()
        remove_user(self.user, None, skip_notify=True)
        self.run_check(30)
        self.assertFalse(AccountActivity.objects.filter(user=self.user).exists())
        self.assertEqual(self.user.auditlog_set.filter(activity="removed").count(), 1)

    def test_primary_email_change_restarts_inactivity_period(self) -> None:
        self.run_check()
        self.run_check(25)
        timestamp = self.timestamp + timedelta(days=26)
        with (
            override_settings(INACTIVE_ACCOUNT_EXPIRY=0),
            patch("weblate.auth.models.timezone.now", return_value=timestamp),
        ):
            self.user.full_name = "Renamed account"
            self.user.save(update_fields=["full_name"])
            self.assertTrue(AccountActivity.objects.get(user=self.user).reminded)
            self.user.email = "new-address@example.org"
            self.user.save(update_fields=["email"])
        state = AccountActivity.objects.get(user=self.user)
        self.assertEqual(state.last_activity, timestamp)
        self.assertIsNone(state.removal_at)
        self.assertFalse(state.reminded)
        self.run_check(30)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(len(mail.outbox), 2)
        self.run_check(392)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(mail.outbox[2].to, ["new-address@example.org"])
        self.assertIn("scheduled for removal", mail.outbox[2].subject)

    def test_api_admin_email_change_cancels_removal(self) -> None:
        admin = self.create_user("administrator", is_superuser=True)
        self.run_check()
        self.run_check(25)
        url = reverse("api:user-detail", kwargs={"username": self.user.username})
        response = self.client.patch(
            url,
            {"email": "updated@example.org"},
            content_type="application/json",
            headers={"authorization": f"Token {admin.auth_token.key}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(AccountActivity.objects.get(user=self.user).removal_at)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "updated@example.org")

    def test_api_admin_can_edit_inactive_user_but_cannot_edit_anonymized_user(
        self,
    ) -> None:
        admin = self.create_user("administrator", is_superuser=True)
        inactive = self.create_user("ordinary-inactive", is_active=False)
        self.run_check()
        self.run_check(25)
        self.run_check(30)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_anonymized)
        headers = {"authorization": f"Token {admin.auth_token.key}"}
        with override_settings(INACTIVE_ACCOUNT_EXPIRY=0):
            for user, expected_status in ((self.user, 403), (inactive, 200)):
                with self.subTest(user=user):
                    url = reverse("api:user-detail", kwargs={"username": user.username})
                    self.assertEqual(
                        self.client.get(url, headers=headers).status_code, 200
                    )
                    response = self.client.patch(
                        url,
                        {"full_name": "Edited account"},
                        content_type="application/json",
                        headers=headers,
                    )
                    self.assertEqual(response.status_code, expected_status)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_anonymized)
        inactive.refresh_from_db()
        self.assertEqual(inactive.full_name, "Edited account")

    def test_reminder_is_retried_after_mail_queue_failure(self) -> None:
        self.run_check()
        with patch("weblate.accounts.inactivity.queue_mails", side_effect=OSError):
            self.run_check(25)
        self.assertFalse(AccountActivity.objects.get(user=self.user).reminded)
        self.run_check(30)
        self.assertEqual(
            AccountActivity.objects.get(user=self.user).removal_at,
            self.timestamp + timedelta(days=35),
        )

    def test_rollback_does_not_queue_final_notice(self) -> None:
        self.run_check()
        self.run_check(25)
        with patch(
            "weblate.accounts.utils.user_pre_delete.send", side_effect=RuntimeError
        ):
            self.run_check(30)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(len(mail.outbox), 2)
        self.assertFalse(self.user.auditlog_set.filter(activity="removed").exists())
        self.run_check(31)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(len(mail.outbox), 3)

    def test_looks_up_history_for_otherwise_stale_accounts_in_batches(self) -> None:
        recent = self.create_user("recent-change")
        old = self.create_user("old-change")
        tracked_recent = self.create_user("tracked-recent")
        tracked_old = self.create_user("tracked-old")
        AccountActivity.objects.create(
            user=tracked_recent, last_activity=self.timestamp
        )
        AccountActivity.objects.create(user=tracked_old, last_activity=self.old)
        self.add_change(recent, 40)
        self.add_change(recent, 1, author=self.user)
        self.add_change(old, 390)
        with override_settings(INACTIVE_ACCOUNT_EXPIRY=0):
            self.add_change(tracked_old, 5)
            self.add_change(tracked_recent, 10)
        with self.assertNumQueries(1):
            changes = dict(
                historical_activity(
                    [
                        recent.pk,
                        old.pk,
                        tracked_old.pk,
                        tracked_recent.pk,
                        self.user.pk,
                    ],
                    self.timestamp - timedelta(days=365),
                )
            )
        self.assertEqual(
            changes,
            {
                recent.pk: self.timestamp - timedelta(days=1),
                old.pk: self.timestamp - timedelta(days=390),
                tracked_old.pk: self.timestamp - timedelta(days=5),
                self.user.pk: None,
            },
        )
        with patch("weblate.accounts.inactivity.BATCH_SIZE", 2):
            self.run_check()
        self.assertDictEqual(
            dict(AccountActivity.objects.values_list("user_id", "last_activity")),
            {**changes, tracked_recent.pk: self.timestamp},
        )
        self.assertIsNone(AccountActivity.objects.get(user=recent).removal_at)
        self.assertEqual(
            set(
                AccountActivity.objects.exclude(removal_at=None).values_list(
                    "user_id", flat=True
                )
            ),
            {old.pk, self.user.pk},
        )

    def test_change_during_repository_flush_cancels_removal(self) -> None:
        self.run_check()
        self.run_check(25)
        with patch(
            "weblate.accounts.utils.commit_pending_for_user",
            side_effect=lambda user, _actor: self.add_change(user, 0),
        ):
            self.run_check(30)
        state = AccountActivity.objects.get(user=self.user)
        self.assertEqual(state.last_activity, self.timestamp)
        self.assertIsNone(state.removal_at)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(len(mail.outbox), 2)

    def test_fresh_activity_wins_over_stale_cleanup_snapshot(self) -> None:
        self.run_check()
        self.run_check(25)
        timestamp = self.timestamp + timedelta(days=30)
        with patch("weblate.accounts.inactivity.now", return_value=timestamp):
            record_account_activity(self.user)
            self.assertIsNone(
                check_account(self.user.pk, self.old, timestamp - timedelta(days=365))
            )
        state = AccountActivity.objects.get(user=self.user)
        self.assertEqual(state.last_activity, timestamp)
        self.assertIsNone(state.removal_at)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_change_after_batch_lookup_cancels_warning_and_reminder(self) -> None:
        pending = self.create_user("pending-reminder")
        AccountActivity.objects.create(user=pending, removal_at=self.timestamp)
        cutoff = self.timestamp - timedelta(days=365)
        batch = dict(historical_activity([self.user.pk, pending.pk], cutoff))
        for user in (self.user, pending):
            with self.subTest(user=user):
                self.assertIsNone(batch[user.pk])
                self.add_change(user, 0)
                self.assertIsNone(check_account(user.pk, batch[user.pk], cutoff))
                state = AccountActivity.objects.get(user=user)
                self.assertIsNone(state.removal_at)
                self.assertEqual(state.last_activity, self.timestamp)
        self.assertEqual(len(mail.outbox), 0)

    def test_partial_2fa_session_does_not_record_activity(self) -> None:
        with override_settings(INACTIVE_ACCOUNT_EXPIRY=0):
            self.client.force_login(self.user)
        User.objects.filter(pk=self.user.pk).update(last_login=self.old)
        self.run_check()
        state = AccountActivity.objects.get(user=self.user)
        with patch(
            "weblate.accounts.middleware.get_session_expiry_scope",
            return_value=SESSION_EXPIRY_SCOPE_2FA,
        ):
            response = self.client.get(reverse("home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        state.refresh_from_db()
        self.assertIsNone(state.last_activity)
        self.assertIsNotNone(state.removal_at)

    def test_browser_session_cancels_removal(self) -> None:
        with override_settings(INACTIVE_ACCOUNT_EXPIRY=0):
            self.client.force_login(self.user)
        User.objects.filter(pk=self.user.pk).update(last_login=self.old)
        self.run_check()
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(AccountActivity.objects.get(user=self.user).removal_at)
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_login, self.old)

    def test_post_login_rejects_an_account_removed_after_password_verification(
        self,
    ) -> None:
        self.run_check()
        self.run_check(25)

        def finish_login(request: AuthenticatedHttpRequest, user: User) -> None:
            self.run_check(30)
            login(request, user)

        with patch("weblate.accounts.views.auth_login", side_effect=finish_login):
            response = self.client.post(
                reverse("login"),
                {"username": self.user.username, "password": "password"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertFalse(self.user.social_auth.exists())
        self.assertFalse(self.user.auditlog_set.filter(activity="enabled").exists())
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_token_authentication_cancels_removal(self) -> None:
        users = {scheme: self.create_user(scheme) for scheme in ("Token", "Bearer")}
        self.run_check()
        url = reverse("api:api-root")
        response = self.client.get(url, headers={"authorization": "Bearer invalid"})
        self.assertEqual(response.status_code, 401)
        self.assertIsNotNone(AccountActivity.objects.get(user=self.user).removal_at)
        for scheme, user in users.items():
            with self.subTest(scheme=scheme):
                response = self.client.get(
                    url, headers={"authorization": f"{scheme} {user.auth_token.key}"}
                )
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(AccountActivity.objects.get(user=user).removal_at)

    def test_recent_activity_avoids_a_database_write(self) -> None:
        self.addCleanup(cache.delete, f"account-activity:{self.user.pk}")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.force_login(self.user)
        state = AccountActivity.objects.get(user=self.user)
        self.assertIsNotNone(state.last_activity)
        with self.assertNumQueries(0):
            record_account_activity(self.user)

    def test_git_activity_cancels_removal_and_warm_token_auth_uses_one_query(
        self,
    ) -> None:
        self.run_check()
        self.addCleanup(cache.delete, f"account-activity:{self.user.pk}")
        factory = RequestFactory()
        token = self.user.auth_token.key
        git_header = "Basic " + b64encode(
            f"{self.user.username}:{token}".encode()
        ).decode("ascii")
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(authenticate_git(factory.get("/"), git_header))
        self.assertIsNone(AccountActivity.objects.get(user=self.user).removal_at)

        with self.assertNumQueries(1):
            self.assertTrue(authenticate_git(factory.get("/"), git_header))
        request = Request(factory.get("/", headers={"authorization": f"Token {token}"}))
        with (
            acting_user_context(None),
            change_origin_context({"scope": "system"}),
            self.assertNumQueries(1),
        ):
            self.assertIsNotNone(WeblateTokenAuthentication().authenticate(request))


@override_settings(INACTIVE_ACCOUNT_EXPIRY=365)
class InactiveAccountConcurrencyTest(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.timestamp = timezone.now()
        old = self.timestamp - timedelta(days=400)
        self.user = User.objects.create_user(
            "stale", "stale@example.org", date_joined=old
        )
        AccountActivity.objects.create(
            user=self.user, last_activity=old, removal_at=self.timestamp, reminded=True
        )
        self.addCleanup(cache.delete, f"account-activity:{self.user.pk}")

    def assert_authentication_loses_cleanup_race(self, channel: str) -> None:
        entered = Event()
        token = self.user.auth_token.key
        if channel in {"session", "2fa"}:
            with override_settings(INACTIVE_ACCOUNT_EXPIRY=0):
                self.client.force_login(self.user)
            User.objects.filter(pk=self.user.pk).update(
                last_login=self.user.date_joined
            )

        def record(user: User, *, record: bool = True) -> bool:
            entered.set()
            return record_account_activity(user, record=record)

        def request() -> bool | int:
            try:
                if channel == "session":
                    response = self.client.get(reverse("home"))
                    return response.wsgi_request.user.is_authenticated
                if channel == "2fa":
                    with patch(
                        "weblate.accounts.middleware.get_session_expiry_scope",
                        return_value=SESSION_EXPIRY_SCOPE_2FA,
                    ):
                        response = self.client.get(reverse("home"))
                    return response.wsgi_request.user.is_authenticated
                if channel == "git":
                    header = "Basic " + b64encode(
                        f"{self.user.username}:{token}".encode()
                    ).decode("ascii")
                    return authenticate_git(RequestFactory().get("/"), header)
                return self.client.get(
                    reverse("api:api-root"),
                    headers={"authorization": f"Token {token}"},
                ).status_code
            finally:
                connections.close_all()

        target = {
            "session": "weblate.accounts.middleware",
            "2fa": "weblate.accounts.middleware",
            "git": "weblate.gitexport.views",
            "api": "weblate.accounts.inactivity",
        }[channel]
        with (
            patch(f"{target}.record_account_activity", side_effect=record),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            with transaction.atomic():
                User.objects.select_for_update().get(pk=self.user.pk)
                result = executor.submit(request)
                self.assertTrue(entered.wait(timeout=5))
                cleanup_inactive_accounts()
            self.assertEqual(
                result.result(timeout=5), 401 if channel == "api" else False
            )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_rest_rejects_token_when_cleanup_wins(self) -> None:
        self.assert_authentication_loses_cleanup_race("api")

    def test_git_rejects_token_when_cleanup_wins(self) -> None:
        self.assert_authentication_loses_cleanup_race("git")

    def test_session_becomes_anonymous_when_cleanup_wins(self) -> None:
        self.assert_authentication_loses_cleanup_race("session")

    def test_partial_2fa_session_becomes_anonymous_when_cleanup_wins(self) -> None:
        self.assert_authentication_loses_cleanup_race("2fa")

    def test_activity_during_repository_flush_cancels_removal(self) -> None:
        def record_activity_in_separate_connection() -> None:
            try:
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '2s'")
                    record_account_activity(self.user)
            finally:
                connections.close_all()

        def flush_pending(_user: User, _actor: User) -> None:
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(record_activity_in_separate_connection).result(
                    timeout=5
                )

        with (
            patch("weblate.accounts.inactivity.now", return_value=self.timestamp),
            patch(
                "weblate.accounts.utils.commit_pending_for_user",
                side_effect=flush_pending,
            ) as flush,
        ):
            cleanup_inactive_accounts()

        flush.assert_called_once_with(self.user, InternalBot.ACCOUNT_CLEANUP.get_user())
        state = AccountActivity.objects.get(user=self.user)
        self.assertEqual(state.last_activity, self.timestamp)
        self.assertIsNone(state.removal_at)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def assert_account_update_loses_cleanup_race(self, view_name: str) -> None:
        admin = User.objects.create_superuser("admin", "admin@example.org", None)
        if view_name == "api:user-detail":
            url = reverse(view_name, kwargs={"username": self.user.username})
            authorization = f"Token {admin.auth_token.key}"
        else:
            url = reverse(view_name, args=[self.user.pk])
            self.client.force_login(admin)
        lookup_started = Event()

        def report_locked_lookup(
            execute: Callable[..., object],
            sql: str,
            params: object,
            many: bool,
            context: object,
        ) -> object:
            if "FOR NO KEY UPDATE OF" in sql and "weblate_auth_user" in sql:
                lookup_started.set()
            return execute(sql, params, many, context)

        def update() -> int:
            try:
                with connection.execute_wrapper(report_locked_lookup):
                    if view_name == "api:user-detail":
                        return self.client.patch(
                            url,
                            {"email": "replacement@example.org"},
                            content_type="application/json",
                            headers={"authorization": authorization},
                        ).status_code
                    return self.client.post(
                        url,
                        {
                            "username": self.user.username,
                            "email": "replacement@example.org",
                            "is_active": "on",
                            "password1": "approved replacement password",
                            "password2": "approved replacement password",
                        },
                    ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=self.user.pk)
                result = executor.submit(update)
                self.assertTrue(lookup_started.wait(timeout=5))
                cleanup_inactive_accounts()
            self.assertEqual(
                result.result(timeout=5), 404 if view_name == "api:user-detail" else 403
            )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(self.user.username, f"deleted-{self.user.pk}")
        self.assertEqual(self.user.email, f"noreply+{self.user.pk}@weblate.org")

    def test_api_update_rejects_the_old_username_after_cleanup(self) -> None:
        self.assert_account_update_loses_cleanup_race("api:user-detail")

    def test_admin_change_form_rejects_anonymized_account(self) -> None:
        self.assert_account_update_loses_cleanup_race("admin:weblate_auth_user_change")

    def test_admin_password_change_rejects_anonymized_account(self) -> None:
        self.assert_account_update_loses_cleanup_race("admin:auth_user_password_change")

    def test_cleanup_defers_for_invitation_with_email_ownership_lock(self) -> None:
        team = Group.objects.create(name="Invitation team")
        self.user.add_team(None, team)
        inviter = User.objects.create_user("inviter", "inviter@example.org")
        invitation = Invitation.objects.create(
            author=inviter, user=self.user, group=team
        )
        flushing = Event()
        resume = Event()

        def flush_pending(_user: User, _actor: User) -> None:
            flushing.set()
            self.assertTrue(resume.wait(timeout=5))

        def cleanup() -> None:
            try:
                cleanup_inactive_accounts()
            finally:
                connections.close_all()

        with (
            patch(
                "weblate.accounts.utils.commit_pending_for_user",
                side_effect=flush_pending,
            ),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            result = executor.submit(cleanup)
            try:
                self.assertTrue(flushing.wait(timeout=5))
                with transaction.atomic():
                    owner = User.objects.select_for_update().get(pk=self.user.pk)
                    resume.set()
                    result.result(timeout=5)
                    invitation.accept(None, owner)
            finally:
                resume.set()
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(AccountActivity.objects.get(user=self.user).reminded)
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())

    def test_final_notice_is_published_after_commit_and_failure_keeps_removal(
        self,
    ) -> None:
        original_email = self.user.email
        attempts = []

        def fail_publish(mails: list[OutgoingEmail]) -> None:
            self.user.refresh_from_db()
            attempts.append(
                (connection.in_atomic_block, self.user.is_active, mails[0]["address"])
            )
            raise OSError

        with (
            patch("weblate.accounts.inactivity.queue_mails", side_effect=fail_publish),
            self.assertLogs("django.db.backends.base", level="ERROR"),
        ):
            cleanup_inactive_accounts()
        self.assertEqual(attempts, [(False, False, original_email)])
        self.assertTrue(self.user.auditlog_set.filter(activity="removed").exists())
