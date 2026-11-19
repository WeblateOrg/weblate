# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep
from typing import TYPE_CHECKING, cast
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import responses
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.core import mail
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from social_core.backends.email import EmailAuth
from social_core.exceptions import AuthSessionError
from social_django.models import Code, DjangoStorage, Partial

from weblate.accounts.forms import UniqueEmailMixin
from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.accounts.pipeline import store_email, validate_password_reset
from weblate.accounts.strategy import WeblateStrategy
from weblate.accounts.tests.test_registration import GH_BACKENDS, BaseRegistrationTest
from weblate.accounts.views import send_password_reset_email
from weblate.auth.models import Group, Invitation, User
from weblate.trans.tests.utils import social_core_override_settings

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

    from weblate.auth.models import AuthenticatedHttpRequest


class OAuthEmailRefreshTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("refresh", "old@example.org")
        self.social = self.user.social_auth.create(
            provider="github", uid="refresh", id_key="id"
        )
        VerifiedEmail.objects.create(social=self.social, email=self.user.email)
        self.strategy = WeblateStrategy(DjangoStorage)

    def refresh(self, details: dict[str, object]) -> None:
        store_email(self.strategy, None, self.user, self.social, details)
        stored = User.objects.get(pk=self.user.pk)
        self.assertEqual(self.user.email, stored.email)

    def test_replace_primary_and_invalidate_codes(self) -> None:
        old_code = Code.objects.create(email="OLD@example.org", code="old")
        other_code = Code.objects.create(email="other@example.org", code="other")
        with patch("weblate.accounts.models.notify_auditlog.delay_on_commit") as notify:
            self.refresh({"email": "new@example.org"})
        self.assertEqual(self.user.email, "new@example.org")
        self.assertIsNone(UniqueEmailMixin.get_email_owner("old@example.org"))
        self.assertFalse(Code.objects.filter(pk=old_code.pk).exists())
        self.assertTrue(Code.objects.filter(pk=other_code.pk).exists())
        audit = AuditLog.objects.get(user=self.user, activity="email")
        self.assertEqual(
            audit.params, {"old": "old@example.org", "new": "new@example.org"}
        )
        notify.assert_called_once_with(audit.pk, "new@example.org")

    def test_empty_verified_addresses_clear_primary(self) -> None:
        with patch("weblate.accounts.models.notify_auditlog.delay_on_commit") as notify:
            self.refresh({"verified_emails": []})
        self.assertIsNone(self.user.email)
        self.assertIsNone(UniqueEmailMixin.get_email_owner("old@example.org"))
        self.assertTrue(self.user.social_auth.filter(pk=self.social.pk).exists())
        notify.assert_not_called()

    def test_independent_verification_preserves_primary(self) -> None:
        other = self.user.social_auth.create(
            provider="email", uid="old@example.org", id_key="email"
        )
        VerifiedEmail.objects.create(social=other, email="OLD@example.org")
        code = Code.objects.create(email="old@example.org", code="retained")
        self.refresh({"email": "new@example.org"})
        self.assertEqual(self.user.email, "old@example.org")
        self.assertTrue(Code.objects.filter(pk=code.pk).exists())
        self.assertEqual(UniqueEmailMixin.get_email_user("old@example.org"), self.user)
        self.assertFalse(
            AuditLog.objects.filter(user=self.user, activity="email").exists()
        )

    def test_secondary_revocation_invalidates_codes(self) -> None:
        VerifiedEmail.objects.create(social=self.social, email="secondary@example.org")
        code = Code.objects.create(email="secondary@example.org", code="secondary")
        self.refresh({"email": "old@example.org"})
        self.assertEqual(self.user.email, "old@example.org")
        self.assertFalse(Code.objects.filter(pk=code.pk).exists())

    def test_missing_claims_preserve_primary(self) -> None:
        self.refresh({})
        self.assertEqual(self.user.email, "old@example.org")
        self.assertTrue(
            self.social.verifiedemail_set.filter(email=self.user.email).exists()
        )

    def test_case_change_preserves_primary_and_codes(self) -> None:
        code = Code.objects.create(email="old@example.org", code="case")
        self.refresh({"email": "OLD@example.org"})
        self.assertEqual(self.user.email, "old@example.org")
        self.assertTrue(Code.objects.filter(pk=code.pk).exists())

    def test_unicode_lookalike_is_not_remaining_verification(self) -> None:
        self.user.email = "user@staff.example.org"
        self.user.save(update_fields=["email"])
        self.social.verifiedemail_set.update(email=self.user.email)
        self.refresh({"email": "user@ſtaff.example.org"})
        self.assertEqual(self.user.email, "user@ſtaff.example.org")
        self.assertIsNone(UniqueEmailMixin.get_email_owner("user@staff.example.org"))

    def test_provider_preference_does_not_change_verified_primary(self) -> None:
        self.refresh(
            {
                "email": "new@example.org",
                "verified_emails": [
                    ("old@example.org", True),
                    ("new@example.org", True),
                ],
            }
        )
        self.assertEqual(self.user.email, "old@example.org")

    def test_replacement_prefers_reported_address(self) -> None:
        self.refresh(
            {
                "email": "preferred@example.org",
                "verified_emails": [
                    ("first@example.org", True),
                    ("preferred@example.org", True),
                ],
            }
        )
        self.assertEqual(self.user.email, "preferred@example.org")

    def test_replacement_uses_remaining_record_order(self) -> None:
        other = self.user.social_auth.create(provider="other", uid="other")
        VerifiedEmail.objects.create(social=other, email="z-first@example.org")
        VerifiedEmail.objects.create(social=other, email="a-second@example.org")
        self.refresh({"verified_emails": []})
        self.assertEqual(self.user.email, "z-first@example.org")

    def test_invalid_nondeliverable_and_conflicting_candidates_are_skipped(
        self,
    ) -> None:
        User.objects.create_user("other-owner", "conflict@example.org")
        self.refresh(
            {
                "email": "CONFLICT@example.org",
                "verified_emails": [
                    ("invalid", True),
                    ("noreply@users.noreply.github.com", False),
                    ("CONFLICT@example.org", True),
                    ("available@example.org", True),
                ],
            }
        )
        self.assertEqual(self.user.email, "available@example.org")

    def test_no_eligible_replacement_clears_primary(self) -> None:
        User.objects.create_user("other-owner", "conflict@example.org")
        self.refresh({"email": "conflict@example.org"})
        self.assertIsNone(self.user.email)

    def test_replacement_conflict_during_save(self) -> None:
        save = User.save

        def conflicting_save(user: User, *args: object, **kwargs: object) -> None:
            if user.email == "conflict@example.org":
                msg = "Concurrent primary address claim"
                raise IntegrityError(msg)
            return save(user, *args, **kwargs)

        with patch.object(User, "save", conflicting_save):
            self.refresh({"email": "conflict@example.org"})
        self.assertIsNone(self.user.email)

    def test_reconciliation_rolls_back_together(self) -> None:
        code = Code.objects.create(email="old@example.org", code="rollback")
        with (
            patch.object(
                AuditLog.objects, "create", side_effect=RuntimeError("audit failure")
            ),
            self.assertRaisesMessage(RuntimeError, "audit failure"),
        ):
            self.refresh({"email": "new@example.org"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.org")
        self.assertEqual(
            list(self.social.verifiedemail_set.values_list("email", flat=True)),
            ["old@example.org"],
        )
        self.assertTrue(Code.objects.filter(pk=code.pk).exists())

    def test_revoked_binding_is_rejected_before_association(self) -> None:
        self.refresh({"email": "new@example.org"})
        backend = EmailAuth(self.strategy)
        with self.assertRaises(AuthSessionError):
            validate_password_reset(backend, {"email": "old@example.org"}, self.user.pk)
        self.assertFalse(self.user.social_auth.filter(provider="email").exists())

    def test_resumed_reset_cannot_restore_revoked_verification(self) -> None:
        email_social = self.user.social_auth.create(
            provider="email", uid="old@example.org", id_key="email"
        )
        # An association paused for a second factor has not stored its verified
        # address yet. Provider revocation must still apply when it resumes.
        self.refresh({"email": "new@example.org"})
        with self.assertRaises(AuthSessionError):
            store_email(
                self.strategy,
                EmailAuth(self.strategy),
                self.user,
                email_social,
                {"email": "old@example.org"},
                weblate_action="reset",
                weblate_reset_user=self.user.pk,
            )
        self.assertFalse(email_social.verifiedemail_set.exists())


@override_settings(REGISTRATION_CAPTCHA=False)
class OAuthEmailRecoveryTest(BaseRegistrationTest):
    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("refresh", "old@example.org")
        self.social = self.user.social_auth.create(
            provider="github", uid="refresh", id_key="id"
        )
        VerifiedEmail.objects.create(social=self.social, email=self.user.email)

    def request_recovery(self) -> str:
        response = self.client.post(
            reverse("password_reset"), {"email": "old@example.org"}
        )
        self.assertRedirects(response, reverse("email-sent"))
        return self.assert_registration_mailbox("[Weblate] Password reset on Weblate")

    def test_pending_recovery_is_invalidated_by_refresh(self) -> None:
        url = self.request_recovery()
        store_email(
            WeblateStrategy(DjangoStorage),
            None,
            self.user,
            self.social,
            {"email": "new@example.org"},
        )
        response = self.confirm_registration_url(url, follow=True)
        self.assertContains(response, "confirmation link probably expired")
        self.assertNotIn("perform_reset", self.client.session)
        self.assertFalse(self.user.social_auth.filter(provider="email").exists())

    def test_legacy_pending_recovery_requires_restart(self) -> None:
        url = self.request_recovery()
        token = parse_qs(urlparse(url).query)["partial_token"][0]
        partial = cast("Partial", Partial.objects.get(token=token))
        del partial.data["kwargs"]["weblate_reset_user"]
        partial.save(update_fields=["data"])
        response = self.confirm_registration_url(url, follow=True)
        self.assertContains(response, "confirmation link probably expired")
        self.assertNotIn("perform_reset", self.client.session)

    def test_recovery_without_pipeline_snapshot_requires_restart(self) -> None:
        url = self.request_recovery()
        token = parse_qs(urlparse(url).query)["partial_token"][0]
        partial = cast("Partial", Partial.objects.get(token=token))
        del partial.data["kwargs"]["weblate_auth_pipeline"]
        partial.save(update_fields=["data"])
        response = self.confirm_registration_url(url, follow=True)
        self.assertContains(response, "confirmation link probably expired")
        self.assertNotIn("perform_reset", self.client.session)
        self.assertFalse(Partial.objects.filter(token=token).exists())
        self.assertFalse(self.user.social_auth.filter(provider="email").exists())

    def test_old_second_factor_pipeline_position_is_rejected(self) -> None:
        url = self.request_recovery()
        token = parse_qs(urlparse(url).query)["partial_token"][0]
        partial = cast("Partial", Partial.objects.get(token=token))
        old_pipeline = partial.data["kwargs"]["weblate_auth_pipeline"]
        old_pipeline.remove("weblate.accounts.pipeline.handle_invite")
        old_pipeline.insert(
            old_pipeline.index("social_core.pipeline.social_auth.associate_user") + 1,
            "weblate.accounts.pipeline.handle_invite",
        )
        partial.next_step = old_pipeline.index(
            "weblate.accounts.pipeline.second_factor"
        )
        partial.save(update_fields=["data", "next_step"])
        response = self.confirm_registration_url(url, follow=True)
        self.assertContains(response, "confirmation link probably expired")
        self.assertNotIn("perform_reset", self.client.session)
        self.assertFalse(Partial.objects.filter(token=token).exists())
        self.assertFalse(self.user.social_auth.filter(provider="email").exists())

    def test_equivalent_list_pipeline_can_resume(self) -> None:
        url = self.request_recovery()
        with override_settings(
            SOCIAL_AUTH_PIPELINE=list(settings.SOCIAL_AUTH_PIPELINE)
        ):
            response = self.confirm_registration_url(url, follow=True)
        self.assertRedirects(response, reverse("password_reset"))
        self.assertEqual(self.client.session["perform_reset"], self.user.pk)

    def test_backend_pipeline_is_used_for_snapshot_validation(self) -> None:
        pipeline = list(settings.SOCIAL_AUTH_PIPELINE)
        with social_core_override_settings(SOCIAL_AUTH_EMAIL_PIPELINE=pipeline):
            url = self.request_recovery()
            with override_settings(SOCIAL_AUTH_PIPELINE=pipeline[:-1]):
                response = self.confirm_registration_url(url, follow=True)
        self.assertRedirects(response, reverse("password_reset"))
        self.assertEqual(self.client.session["perform_reset"], self.user.pk)

    def test_primary_only_legacy_recovery_is_preserved(self) -> None:
        self.social.delete()
        url = self.request_recovery()
        response = self.confirm_registration_url(url, follow=True)
        self.assertRedirects(response, reverse("password_reset"))
        self.assertEqual(self.client.session["perform_reset"], self.user.pk)

    def test_completion_locks_account_before_verifying_code(self) -> None:
        url = self.request_recovery()
        with CaptureQueriesContext(connection) as queries:
            response = self.confirm_registration_url(url, follow=True)
        self.assertRedirects(response, reverse("password_reset"))
        statements = [query["sql"] for query in queries]
        account_lock = next(
            index
            for index, sql in enumerate(statements)
            if '"weblate_auth_user"' in sql and "FOR UPDATE" in sql
        )
        code_verification = next(
            index
            for index, sql in enumerate(statements)
            if sql.startswith('UPDATE "social_auth_code"')
        )
        self.assertLess(account_lock, code_verification)

    def test_recovery_binding_cannot_switch_accounts(self) -> None:
        other = User.objects.create_user("other", "other@example.org")
        url = self.request_recovery()
        token = parse_qs(urlparse(url).query)["partial_token"][0]
        partial = cast("Partial", Partial.objects.get(token=token))
        partial.data["kwargs"]["weblate_reset_user"] = other.pk
        partial.save(update_fields=["data"])
        response = self.confirm_registration_url(url, follow=True)
        self.assertContains(response, "confirmation link probably expired")
        self.assertNotIn("perform_reset", self.client.session)
        self.assertFalse(self.user.social_auth.filter(provider="email").exists())

    def test_retired_address_does_not_send_account_recovery(self) -> None:
        store_email(
            WeblateStrategy(DjangoStorage),
            None,
            self.user,
            self.social,
            {"email": "new@example.org"},
        )
        self.client.post(reverse("password_reset"), {"email": "old@example.org"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("verification_code=", mail.outbox[0].body)

    def mock_github(self, email: str | None = None) -> None:
        responses.add(
            responses.POST,
            "https://github.com/login/oauth/access_token",
            json={"access_token": "123", "token_type": "bearer"},
        )
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"email": "", "login": "refresh", "id": "refresh", "name": "Refresh"},
        )
        emails = (
            [
                {
                    "email": email,
                    "verified": True,
                    "primary": True,
                    "visibility": "public",
                }
            ]
            if email
            else []
        )
        responses.add(responses.GET, "https://api.github.com/user/emails", json=emails)

    def github_login(
        self, invitation: Invitation | None = None, *, authenticated: bool = True
    ) -> _MonkeyPatchedWSGIResponse:
        self.client.logout()
        if invitation is not None:
            self.use_invitation(invitation)
        response = self.client.post(reverse("social:begin", args=("github",)))
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response["Location"]).query)
        return_query = parse_qs(urlparse(query["redirect_uri"][0]).query)
        response = self.client.get(
            reverse("social:complete", args=("github",)),
            {"state": query["state"][0] or return_query["state"][0], "code": "XXX"},
            follow=True,
        )
        if authenticated:
            self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        else:
            self.assertNotIn(SESSION_KEY, self.client.session)
        return response

    def create_invitation(self, *, user_bound: bool = False) -> Invitation:
        author = User.objects.create_user("inviter", "inviter@example.org")
        group = Group.objects.create(name="Refresh invited")
        return Invitation.objects.create(
            author=author,
            group=group,
            user=self.user if user_bound else None,
            email="" if user_bound else "old@example.org",
        )

    @responses.activate
    @social_core_override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_oauth_sign_in_survives_cleared_primary(self) -> None:
        self.mock_github()
        # Cover both the revoking login and a later login without a primary.
        for _attempt in range(2):
            response = self.github_login()
            self.user.refresh_from_db()
            self.assertIsNone(self.user.email)
            self.assertContains(response, "Please provide an e-mail address")

    @responses.activate
    @social_core_override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_revoked_address_does_not_bind_pending_invitation(self) -> None:
        invitation = self.create_invitation()
        self.mock_github("new@example.org")
        self.github_login()
        invitation.refresh_from_db()
        self.assertIsNone(invitation.user_id)
        self.assertEqual(invitation.email, "old@example.org")
        self.assertFalse(self.user.groups.filter(pk=invitation.group_id).exists())

    @responses.activate
    @social_core_override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_revoked_address_cannot_accept_invitation_link(self) -> None:
        invitation = self.create_invitation()
        self.mock_github("new@example.org")
        self.github_login(invitation)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.user_id)
        self.assertEqual(invitation.email, "old@example.org")
        self.assertFalse(self.user.groups.filter(pk=invitation.group_id).exists())
        self.assertNotIn("invitation_link", self.client.session)

    @responses.activate
    @social_core_override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_independent_verification_preserves_invitation_acceptance(self) -> None:
        social = self.user.social_auth.create(
            provider="email", uid="old@example.org", id_key="email"
        )
        VerifiedEmail.objects.create(social=social, email="old@example.org")
        invitation = self.create_invitation()
        self.mock_github("new@example.org")
        self.github_login(invitation)
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())
        self.assertTrue(self.user.groups.filter(pk=invitation.group_id).exists())

    @responses.activate
    @social_core_override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_user_bound_invitation_survives_email_revocation(self) -> None:
        invitation = self.create_invitation(user_bound=True)
        self.mock_github("new@example.org")
        self.github_login(invitation)
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())
        self.assertTrue(self.user.groups.filter(pk=invitation.group_id).exists())

    @responses.activate
    @social_core_override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_second_factor_resume_reconciles_before_handling_invitations(self) -> None:
        device = TOTPDevice.objects.create(user=self.user, name="test", confirmed=True)
        invitation = self.create_invitation(user_bound=True)
        stale = Invitation.objects.create(
            author=invitation.author,
            group=Group.objects.create(name="Retired address"),
            email="old@example.org",
        )
        self.mock_github("new@example.org")

        response = self.github_login(invitation, authenticated=False)

        self.assertEqual(
            response.request["PATH_INFO"],
            reverse("2fa-login", kwargs={"backend": "totp"}),
        )
        self.assertTrue(Invitation.objects.filter(pk=invitation.pk).exists())
        self.assertFalse(self.user.groups.filter(pk=invitation.group_id).exists())
        stale.refresh_from_db()
        self.assertIsNone(stale.user_id)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.org")

        token = f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):06d}"
        self.client.post(
            response.redirect_chain[-1][0], {"otp_token": token}, follow=True
        )

        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.org")
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())
        self.assertTrue(self.user.groups.filter(pk=invitation.group_id).exists())
        stale.refresh_from_db()
        self.assertIsNone(stale.user_id)
        self.assertEqual(stale.email, "old@example.org")


class AuthenticationPipelineSnapshotTest(TestCase):
    @social_core_override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_oauth_partial_from_old_pipeline_is_rejected(self) -> None:
        request = RequestFactory().get(reverse("social:complete", args=("github",)))
        request.session = self.client.session
        strategy = WeblateStrategy(DjangoStorage, request)
        pipeline = list(strategy.get_pipeline(strategy.get_backend("github")))
        old_pipeline = pipeline.copy()
        old_pipeline.remove("weblate.accounts.pipeline.handle_invite")
        old_pipeline.insert(
            old_pipeline.index("social_core.pipeline.social_auth.associate_user") + 1,
            "weblate.accounts.pipeline.handle_invite",
        )
        partial = DjangoStorage.partial.prepare(
            "github",
            old_pipeline.index("weblate.accounts.pipeline.second_factor"),
            {
                "pipeline_type": "authentication",
                "kwargs": {"weblate_auth_pipeline": old_pipeline},
            },
        )
        DjangoStorage.partial.store(partial)
        with self.assertRaises(AuthSessionError):
            strategy.partial_load(partial.token)
        self.assertFalse(Partial.objects.filter(token=partial.token).exists())
        self.assertEqual(strategy.invalid_partial_token, partial.token)

    def test_disconnect_partial_does_not_require_authentication_snapshot(self) -> None:
        strategy = WeblateStrategy(DjangoStorage)
        partial = DjangoStorage.partial.prepare(
            "email", 0, {"pipeline_type": "disconnect", "kwargs": {}}
        )
        DjangoStorage.partial.store(partial)
        loaded = strategy.partial_load(partial.token)
        if loaded is None:
            self.fail("Disconnect partial was rejected")
        self.assertEqual(loaded.pipeline_type, "disconnect")


class OAuthEmailRefreshConcurrencyTest(TransactionTestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("concurrent-refresh", "old@example.org")
        self.social = self.user.social_auth.create(
            provider="github", uid="concurrent-refresh", id_key="id"
        )
        VerifiedEmail.objects.create(social=self.social, email=self.user.email)

    def wait_for_account_lock(self, worker_pid: int, owner_pid: int) -> None:
        deadline = monotonic() + 5
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT %s = ANY(pg_blocking_pids(%s))", [owner_pid, worker_pid]
                )
                if cursor.fetchone()[0]:
                    return
            sleep(0.01)
        self.fail("Recovery did not wait for the account revocation lock")

    def check_recovery_during_revocation(self, *, completing: bool) -> None:
        worker_pid: Queue[int] = Queue()

        def recover() -> None:
            close_old_connections()
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_backend_pid()")
                        worker_pid.put(cursor.fetchone()[0])
                    if completing:
                        with self.assertRaises(AuthSessionError):
                            validate_password_reset(
                                EmailAuth(WeblateStrategy(DjangoStorage)),
                                {"email": "old@example.org"},
                                self.user.pk,
                            )
                    else:
                        request = RequestFactory().post(reverse("password_reset"))
                        self.assertIsNone(
                            send_password_reset_email(
                                cast("AuthenticatedHttpRequest", request),
                                self.user,
                                email="old@example.org",
                            )
                        )
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    owner_pid = cursor.fetchone()[0]
                store_email(
                    WeblateStrategy(DjangoStorage),
                    None,
                    self.user,
                    self.social,
                    {"verified_emails": []},
                )
                future = executor.submit(recover)
                # The other connection must wait for reconciliation to commit
                # before it can decide whether this address still owns the account.
                self.wait_for_account_lock(worker_pid.get(timeout=10), owner_pid)
            future.result(timeout=20)
        self.assertFalse(Code.objects.filter(email="old@example.org").exists())
        self.assertFalse(self.user.social_auth.filter(provider="email").exists())

    def test_issuance_waits_for_revocation(self) -> None:
        self.check_recovery_during_revocation(completing=False)

    def test_completion_waits_for_revocation(self) -> None:
        self.check_recovery_during_revocation(completing=True)
