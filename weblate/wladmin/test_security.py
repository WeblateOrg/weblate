# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import time
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from asgiref.sync import async_to_sync
from django.apps import apps
from django.conf import settings
from django.contrib.auth.hashers import PBKDF2PasswordHasher, verify_password
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.paginator import Paginator
from django.db import connection
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django_otp.plugins.otp_totp.models import TOTPDevice
from lxml import html
from social_django.models import UserSocialAuth

from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.accounts.password_validation import PastPasswordsValidator
from weblate.accounts.tasks import notify_auditlog
from weblate.accounts.utils import (
    SESSION_SECOND_FACTOR_TIMESTAMP,
    SESSION_SENSITIVE_FACTOR_GRANT,
    reset_api_token,
)
from weblate.auth.models import User
from weblate.wladmin.apps import check_account_security
from weblate.wladmin.models import SecurityFinding, SecurityFindingEvent, SecurityScan
from weblate.wladmin.security import (
    MAX_UPLOAD,
    fingerprint,
    handle_finding,
    input_key,
    is_legacy_email_alias,
    parse_report,
    record_detection,
    run_security_scan,
    store_input,
)
from weblate.wladmin.security_views import filtered_findings, validation_reports
from weblate.wladmin.tasks import cleanup_security_scans


class SecurityCSVTest(SimpleTestCase):
    def test_detection_and_preservation(self) -> None:
        rows = parse_report(
            b'\xef\xbb\xbfURL,USERNAME,PASSWORD,ADDED_AT\nhttps://example.invalid/,alice," secret, value ",today\n',
            {},
        )
        self.assertEqual(rows, [(2, "alice", " secret, value ")])

    def test_manual_headerless(self) -> None:
        self.assertEqual(
            parse_report(
                b"wrong|alice\n",
                {
                    "delimiter": "|",
                    "header": False,
                    "identifier_column": 2,
                    "password_column": 1,
                },
            ),
            [(1, "alice", "wrong")],
        )

    def test_detection_fails_without_headers(self) -> None:
        with self.assertRaises(ValidationError):
            parse_report(b"alice,synthetic-secret\n", {})

    def test_invalid_input(self) -> None:
        cases: list[tuple[bytes, dict]] = [
            (b"\xff", {}),
            (b"", {}),
            (
                b"a,b\n",
                {"delimiter": ",", "identifier_column": 1, "password_column": 1},
            ),
            (b'"unterminated', {"delimiter": ","}),
            (b"x" * (MAX_UPLOAD + 1), {}),
        ]
        for content, config in cases:
            with (
                self.subTest(config=config, length=len(content)),
                self.assertRaises(ValidationError),
            ):
                parse_report(content, config)

    def test_malformed_rows(self) -> None:
        self.assertEqual(
            parse_report(b"username,password\nalice\nbob,\n", {"delimiter": ","}),
            [(2, "", ""), (3, "", "")],
        )


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    ]
)
class AccountSecurityTest(TestCase):
    admin: User
    user: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.admin = User.objects.create_superuser(
            "security-admin", "security-admin@example.net", "admin-pass"
        )
        cls.user = User.objects.create_user(
            "security-target", "security-target@example.net", "synthetic-secret"
        )

    def setUp(self) -> None:
        self.client.force_login(self.admin)
        self.verification = patch(
            "weblate.wladmin.security_views.has_recent_sensitive_verification",
            return_value=True,
        )
        self.verification.start()
        self.addCleanup(self.verification.stop)

    def scan(self, data: bytes | None = None) -> SecurityScan:
        scan = SecurityScan.objects.create(actor=self.admin)
        store_input(
            scan, data or b"USERNAME,PASSWORD\nsecurity-target,synthetic-secret\n"
        )
        run_security_scan(str(scan.pk))
        scan.refresh_from_db()
        self.assertEqual(scan.state, "completed", scan.error)
        return scan

    def test_legacy_email_upgrade_finding_and_cleanup(self) -> None:
        victim = User.objects.create_user(
            "legacy-victim", "victim@github.com", "secret"
        )
        social = UserSocialAuth.objects.create(
            user=victim, provider="email", uid="victim@gıthub.com", id_key="email"
        )
        entry = VerifiedEmail.objects.create(social=social, email="victim@gıthub.com")
        self.assertTrue(is_legacy_email_alias(entry))
        migration = import_module(
            "weblate.wladmin.migrations.0010_detect_legacy_email_aliases"
        )
        migration.detect_legacy_email_aliases(
            apps, SimpleNamespace(connection=connection)
        )

        finding = SecurityFinding.objects.get(user=victim)
        self.assertEqual(finding.finding_type, "legacy-email-alias")
        self.assertEqual(finding.evidence["email"], "victim@gıthub.com")
        self.assertEqual(
            finding.events.get(action="detected").actor_id,
            User.objects.get(username="weblate:alerts").pk,
        )
        self.assertTrue(VerifiedEmail.objects.filter(pk=entry.pk).exists())

        confirmation = self.client.post(
            reverse("manage-security"),
            {"selected": [finding.pk], "action": "cleanup"},
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(confirmation.context["action"], "cleanup")

        token = reset_api_token(victim)
        original_hash = victim.get_session_auth_hash()
        scan = SecurityScan.objects.create(actor=self.admin, operation="cleanup")
        with patch("weblate.accounts.models.notify_auditlog.delay_on_commit") as notify:
            self.assertEqual(handle_finding(scan, finding.pk), "email-cleanup")
        victim.refresh_from_db()
        self.assertFalse(victim.has_usable_password())
        self.assertNotEqual(victim.get_session_auth_hash(), original_hash)
        self.assertFalse(type(token).objects.filter(pk=token.pk).exists())
        self.assertFalse(VerifiedEmail.objects.filter(pk=entry.pk).exists())
        self.assertFalse(UserSocialAuth.objects.filter(pk=social.pk).exists())
        audit = AuditLog.objects.get(user=victim, activity="email-cleanup")
        self.assertEqual(audit.params["username"], self.admin.username)
        notify.assert_called_once_with(audit.pk, victim.email)

    def test_legacy_cleanup_after_primary_change(self) -> None:
        for provider in ("email", "github"):
            with self.subTest(provider=provider):
                social = UserSocialAuth.objects.create(
                    user=self.user, provider=provider, uid=f"suspect-{provider}"
                )
                entry = VerifiedEmail.objects.create(
                    social=social, email="victim@gıthub.com"
                )
                finding = SecurityFinding.objects.create(
                    user=self.user,
                    finding_type="legacy-email-alias",
                    key=str(entry.pk),
                    evidence={
                        "verified_email_id": entry.pk,
                        "social_id": social.pk,
                        "email": entry.email,
                        "primary_email": "victim@github.com",
                    },
                )
                self.user.email = "new@example.net"
                self.user.set_password("secret")
                self.user.save()
                token = reset_api_token(self.user)
                scan = SecurityScan.objects.create(
                    actor=self.admin, operation="cleanup"
                )
                with patch("weblate.accounts.models.notify_auditlog.delay_on_commit"):
                    self.assertEqual(handle_finding(scan, finding.pk), "email-cleanup")
                self.user.refresh_from_db()
                finding.refresh_from_db()
                self.assertFalse(self.user.has_usable_password())
                self.assertEqual(finding.status, "resolved")
                self.assertFalse(VerifiedEmail.objects.filter(pk=entry.pk).exists())
                self.assertFalse(UserSocialAuth.objects.filter(pk=social.pk).exists())
                self.assertFalse(type(token).objects.filter(pk=token.pk).exists())

    def test_detection_rechecks_concurrent_password_changes(self) -> None:
        for changed in (False, True):
            with self.subTest(password_changed=changed):
                self.user.set_password("synthetic-secret")
                self.user.save(update_fields=["password"])

                def record_after_change(
                    scan: SecurityScan,
                    user: User,
                    evidence: dict,
                    passwords: list[str],
                    *,
                    changed: bool = changed,
                ) -> None:
                    self.user.set_password(
                        "changed-secret" if changed else "synthetic-secret"
                    )
                    self.user.save(update_fields=["password"])
                    record_detection(scan, user, evidence, passwords)

                with patch(
                    "weblate.wladmin.security.record_detection",
                    side_effect=record_after_change,
                ):
                    scan = self.scan()
                findings = SecurityFinding.objects.filter(events__scan=scan)
                if not changed:
                    finding = findings.get()
                    self.assertEqual(finding.key, fingerprint(self.user.password))
                    serialized = json.dumps(
                        [
                            finding.evidence,
                            list(finding.events.values("evidence")),
                            scan.summary,
                        ]
                    )
                    self.assertNotIn("synthetic-secret", serialized)
                    self.assertNotIn(self.user.password, serialized)
                else:
                    self.assertFalse(findings.exists())
                self.assertEqual(scan.summary["matched"], 1)

    def test_legacy_email_cleanup_skips_changed_association(self) -> None:
        victim = User.objects.create_user("legacy-stale", "victim@github.com", "secret")
        social = UserSocialAuth.objects.create(
            user=victim, provider="email", uid="victim@gıthub.com"
        )
        entry = VerifiedEmail.objects.create(social=social, email="victim@gıthub.com")
        finding = SecurityFinding.objects.create(
            user=victim,
            finding_type="legacy-email-alias",
            key=str(entry.pk),
            evidence={
                "verified_email_id": entry.pk,
                "social_id": social.pk,
                "email": entry.email,
            },
        )
        entry.email = "other@example.net"
        entry.save(update_fields=["email"])
        scan = SecurityScan.objects.create(actor=self.admin, operation="cleanup")

        self.assertEqual(handle_finding(scan, finding.pk), "email-already-changed")
        victim.refresh_from_db()
        self.assertTrue(victim.check_password("secret"))
        self.assertTrue(VerifiedEmail.objects.filter(pk=entry.pk).exists())

    def test_validation_and_secret_storage(self) -> None:
        original = self.user.password
        scan = SecurityScan.objects.create(actor=self.admin)
        data = b"USERNAME,PASSWORD\nsecurity-target,synthetic-secret\nsecurity-target,synthetic-secret\nunknown,synthetic-secret\nsecurity-target,incorrect\n"
        store_input(scan, data)
        self.assertNotIn(b"synthetic-secret", cache.get(input_key(scan.pk)))
        run_security_scan(str(scan.pk))
        scan.refresh_from_db()
        self.assertEqual(
            scan.summary,
            {
                "checked": 2,
                "matched": 1,
                "duplicate": 1,
                "unknown": 1,
                "mismatch": 1,
                "accounts": 1,
            },
        )
        self.assertIsNone(cache.get(input_key(scan.pk)))
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, original)
        finding = SecurityFinding.objects.get(user=self.user)
        serialized = json.dumps(
            [finding.evidence, scan.summary, list(finding.events.values("evidence"))]
        )
        self.assertNotIn("synthetic-secret", serialized)
        self.assertNotIn(original, serialized)
        self.assertEqual(finding.key, fingerprint(original))
        run_security_scan(str(scan.pk))
        self.assertEqual(finding.events.count(), 1)

    def test_primary_secondary_and_ambiguous_matching(self) -> None:
        social = UserSocialAuth.objects.create(
            user=self.user, provider="email", uid="secondary@example.net"
        )
        VerifiedEmail.objects.create(social=social, email="secondary@example.net")
        other = User.objects.create_user(
            "security-target@example.net", "other@example.net", "synthetic-secret"
        )
        scan = self.scan(
            b"username,password\nSECONDARY@EXAMPLE.NET,synthetic-secret\nsecurity-target@example.net,synthetic-secret\n"
        )
        self.assertEqual(scan.summary["matched"], 1)
        self.assertEqual(scan.summary["ambiguous"], 1)
        self.assertFalse(SecurityFinding.objects.filter(user=other).exists())

    def test_inactive_bot_and_unusable(self) -> None:
        self.user.is_active = False
        self.user.is_bot = True
        self.user.save()
        self.scan()
        self.assertTrue(SecurityFinding.objects.filter(user=self.user).exists())
        self.user.set_unusable_password()
        self.user.save()
        scan = self.scan()
        self.assertEqual(scan.summary["unusable"], 1)

    def test_dismiss_reopen_and_old_scan(self) -> None:
        scan = self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        action = SecurityScan.objects.create(actor=self.admin, operation="dismiss")
        self.assertEqual(handle_finding(action, finding.pk), "dismissed")
        self.assertEqual(handle_finding(action, finding.pk), "skipped")
        record_detection(scan, self.user, {"matches": []})
        finding.refresh_from_db()
        self.assertEqual(finding.status, "dismissed")
        old_scan = SecurityScan.objects.create(
            actor=self.admin, created=timezone.now() - timedelta(days=1)
        )
        record_detection(old_scan, self.user, {"matches": []})
        finding.refresh_from_db()
        self.assertEqual(finding.status, "dismissed")
        self.scan()
        finding.refresh_from_db()
        self.assertEqual(finding.status, "open")
        self.assertEqual(
            finding.events.filter(action="dismissed", actor=self.admin).count(), 1
        )

    @patch("weblate.accounts.models.notify_auditlog.delay_on_commit")
    def test_reset_tokens_sessions_and_notification(self, notify: Mock) -> None:
        self.scan()
        token = reset_api_token(self.user)
        target_client = Client()
        target_client.force_login(self.user)
        original_hash = self.user.get_session_auth_hash()
        finding = SecurityFinding.objects.get(user=self.user)
        action = SecurityScan.objects.create(actor=self.admin, operation="reset")
        self.assertEqual(handle_finding(action, finding.pk), "password-reset")
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertNotEqual(original_hash, self.user.get_session_auth_hash())
        self.assertFalse(type(token).objects.filter(pk=token.pk).exists())
        audit = AuditLog.objects.get(user=self.user, activity="password-leak")
        self.assertEqual(audit.params["username"], self.admin.username)
        notify.assert_called_once_with(audit.pk, self.user.email)
        self.assertEqual(handle_finding(action, finding.pk), "skipped")
        with patch("weblate.accounts.notifications.send_notification_email") as send:
            notify_auditlog(audit.pk, self.user.email)
        self.assertIn(
            "reported leaked credential",
            str(send.call_args.kwargs["context"]["message"]()),
        )
        self.assertIsNotNone(send.call_args.kwargs["context"]["password_reset_url"])

    def test_stale_password(self) -> None:
        self.scan()
        token = reset_api_token(self.user)
        self.user.set_password("changed-password")
        self.user.save()
        finding = SecurityFinding.objects.get(user=self.user)
        action = SecurityScan.objects.create(actor=self.admin, operation="reset")
        self.assertEqual(handle_finding(action, finding.pk), "password-changed")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("changed-password"))
        self.assertTrue(type(token).objects.filter(pk=token.pk).exists())

    def test_expired_input_failure(self) -> None:
        scan = SecurityScan.objects.create(actor=self.admin)
        run_security_scan(str(scan.pk))
        scan.refresh_from_db()
        self.assertEqual(scan.state, "failed")
        self.assertIsNotNone(scan.completed)

    def test_worker_checks_authority(self) -> None:
        scan = SecurityScan.objects.create(actor=self.user)
        store_input(scan, b"username,password\nsecurity-target,synthetic-secret\n")
        run_security_scan(str(scan.pk))
        scan.refresh_from_db()
        self.assertEqual(scan.state, "failed")
        self.assertFalse(SecurityFinding.objects.exists())
        self.assertIsNone(cache.get(input_key(scan.pk)))

    def test_upload_progress_and_report(self) -> None:
        report = SimpleUploadedFile(
            "local/synthetic.csv",
            b"username,password\nsecurity-target,synthetic-secret\n",
        )
        response = self.client.post(
            reverse("manage-security-upload"), {"report": report, "header": "on"}
        )
        scan = SecurityScan.objects.get(operation="validate")
        self.assertEqual(scan.filename, "synthetic.csv")
        self.assertEqual(scan.actor_id, self.admin.pk)
        self.assertRedirects(
            response,
            reverse("manage-security-progress", kwargs={"pk": scan.pk}),
            fetch_redirect_response=False,
        )
        response = self.client.get(response["Location"], follow=True)
        self.assertContains(response, "security-target")
        self.assertNotContains(response, "synthetic-secret")
        self.assertContains(response, "Passwords checked")
        self.assertContains(response, 'name="selected"')
        self.assertContains(response, "synthetic.csv")
        tree = html.fromstring(response.content)
        submitter = tree.xpath(
            '//dt[normalize-space()="Submitted by"]/following-sibling::dd[1]'
        )
        self.assertEqual(submitter[0].text_content().strip(), self.admin.username)
        history = self.client.get(reverse("manage-security-reports"))
        tree = html.fromstring(history.content)
        row = tree.xpath("//a[@href=$url]/ancestor::tr", url=scan.get_absolute_url())[0]
        self.assertEqual(row.xpath("td")[1].text_content().strip(), "synthetic.csv")
        self.assertEqual(row.xpath("td")[2].text_content().strip(), self.admin.username)

    def test_manual_retry(self) -> None:
        report = SimpleUploadedFile("synthetic.csv", b"wrong|security-target\n")
        response = self.client.post(
            reverse("manage-security-upload"), {"report": report}
        )
        self.assertContains(response, "Configure")
        scan = SecurityScan.objects.get()
        response = self.client.post(
            reverse("manage-security-upload"),
            {
                "scan": str(scan.pk),
                "delimiter": "|",
                "identifier_column": 2,
                "password_column": 1,
            },
        )
        self.assertEqual(response.status_code, 302)
        scan.refresh_from_db()
        self.assertEqual(scan.state, "completed")
        self.assertEqual(scan.filename, "synthetic.csv")

    def test_report_query_count_and_pagination_selection(self) -> None:
        SecurityFinding.objects.bulk_create(
            [
                SecurityFinding(
                    user=self.user, finding_type="future-type", key=str(index)
                )
                for index in range(52)
            ]
        )
        with self.assertNumQueries(2):
            findings, *_ = filtered_findings(RequestFactory().get("/"))
            for finding in findings[:50]:
                str(finding.user.username)
                list(finding.events.all())
        response = self.client.get(reverse("manage-security"))
        self.assertEqual(len(response.context["page"]), 50)
        self.assertContains(response, 'name="selected"', count=50)
        response = self.client.get(reverse("manage-security"), {"page": 2})
        page = response.context["page"]
        self.assertEqual(len(page), 2)
        self.assertContains(response, 'name="selected"', count=2)
        response = self.client.post(
            reverse("manage-security") + "?page=2",
            {
                "action": "dismiss",
                "selected": [str(finding.pk) for finding in page],
            },
        )
        self.assertEqual(response.context["count"], 2)
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(
                reverse("manage-security-confirm"), {"token": response.context["token"]}
            )
        self.assertEqual(result.status_code, 302)
        self.assertEqual(SecurityFinding.objects.filter(status="dismissed").count(), 2)
        self.assertEqual(
            self.client.post(
                reverse("manage-security-confirm"), {"token": response.context["token"]}
            ).status_code,
            404,
        )

    def test_action_buttons_match_open_findings_on_page(self) -> None:
        self.scan()
        url = reverse("manage-security")
        response = self.client.get(url)
        self.assertContains(response, 'value="reset"')
        self.assertNotContains(response, 'value="cleanup"')
        self.assertContains(response, 'value="dismiss"')

        SecurityFinding.objects.create(
            user=self.user, finding_type="legacy-email-alias", key="alias"
        )
        response = self.client.get(url)
        self.assertContains(response, 'value="reset"')
        self.assertContains(response, 'value="cleanup"')

        response = self.client.get(url, {"type": "legacy-email-alias"})
        self.assertNotContains(response, 'value="reset"')
        self.assertContains(response, 'value="cleanup"')
        self.assertContains(response, 'value="dismiss"')

        response = self.client.get(url, {"type": "leaked-password"})
        self.assertContains(response, 'value="reset"')
        self.assertNotContains(response, 'value="cleanup"')

        SecurityFinding.objects.bulk_create(
            [
                SecurityFinding(
                    user=self.user,
                    finding_type="future-type",
                    key=str(index),
                    last_seen=timezone.now() + timedelta(days=1),
                )
                for index in range(50)
            ]
        )
        response = self.client.get(url)
        self.assertNotContains(response, 'value="reset"')
        self.assertNotContains(response, 'value="cleanup"')
        self.assertContains(response, 'value="dismiss"')
        response = self.client.get(url, {"page": 2})
        self.assertContains(response, 'value="reset"')
        self.assertContains(response, 'value="cleanup"')

        SecurityFinding.objects.filter(finding_type="leaked-password").update(
            status="resolved"
        )
        response = self.client.get(url, {"type": "leaked-password", "status": "all"})
        self.assertNotContains(response, 'value="reset"')
        self.assertNotContains(response, 'value="cleanup"')
        self.assertNotContains(response, 'value="dismiss"')

    def test_permissions_verification_and_csrf(self) -> None:
        self.verification.stop()
        response = self.client.get(reverse("manage-security-upload"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        for route in [
            "manage-security",
            "manage-security-upload",
            "manage-security-confirm",
        ]:
            self.assertEqual(self.client.get(reverse(route)).status_code, 403)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(
            csrf_client.post(
                reverse("manage-security-upload"), {"header": "on"}
            ).status_code,
            403,
        )

    def test_deployment_warning_and_handled_history(self) -> None:
        self.assertEqual(list(check_account_security()), [])
        self.scan()
        self.assertEqual(next(iter(check_account_security())).id, "weblate.W052")
        SecurityFinding.objects.update(status="dismissed")
        self.assertEqual(list(check_account_security()), [])
        response = self.client.get(reverse("manage-security") + "?status=dismissed")
        self.assertContains(response, "security-target")

    def test_separate_upload_and_empty_report_controls(self) -> None:
        session = self.client.session
        session[SESSION_SENSITIVE_FACTOR_GRANT] = {
            "user": self.admin.pk,
            "hash": self.admin.get_session_auth_hash(),
            "time": int(time.time()),
        }
        session.save()
        response = self.client.get(reverse("manage-users"))
        self.assertContains(response, 'id="account-security"')
        self.assertNotContains(response, 'enctype="multipart/form-data"')
        self.assertNotContains(response, 'name="report"')
        self.assertContains(response, reverse("manage-security-upload"))
        response = self.client.get(reverse("manage-security"))
        self.assertNotContains(response, "Save selection")
        self.assertNotContains(response, "Dismiss selected findings")
        self.assertNotContains(response, "Reset passwords for selected accounts")
        self.assertNotContains(response, "Validate leaked passwords")

    def test_expired_upload_requires_new_file_without_storage(self) -> None:
        self.verification.stop()
        session = self.client.session
        session[SESSION_SENSITIVE_FACTOR_GRANT] = {
            "user": self.admin.pk,
            "hash": self.admin.get_session_auth_hash(),
            "time": int(time.time()),
        }
        session.save()
        self.assertContains(
            self.client.get(reverse("manage-security-upload")), 'name="report"'
        )
        session = self.client.session
        session[SESSION_SENSITIVE_FACTOR_GRANT]["time"] -= 601
        session.save()
        report = SimpleUploadedFile(
            "synthetic.csv", b"username,password\nsecurity-target,synthetic-secret\n"
        )
        with patch("weblate.wladmin.security_views.store_input") as store:
            response = self.client.post(
                reverse("manage-security-upload"), {"report": report, "header": "on"}
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            parse_qs(urlparse(response["Location"]).query)["next"],
            [reverse("manage-security-upload")],
        )
        store.assert_not_called()
        self.assertFalse(SecurityScan.objects.exists())
        self.assertTrue(
            any(
                "upload the CSV report again" in str(message)
                for message in get_messages(response.wsgi_request)
            )
        )

    def test_upload_page_verifies_before_showing_file_input(self) -> None:
        self.verification.stop()
        response = self.client.get(reverse("manage-security-upload"))
        self.assertEqual(response.status_code, 302)
        self.assertNotContains(response, 'name="report"', status_code=302)
        session = self.client.session
        session[SESSION_SENSITIVE_FACTOR_GRANT] = {
            "user": self.admin.pk,
            "hash": self.admin.get_session_auth_hash(),
            "time": int(time.time()),
        }
        session.save()
        self.assertContains(
            self.client.get(reverse("manage-security-upload")), 'name="report"'
        )

    def test_report_and_details_require_recent_verification(self) -> None:
        self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        self.verification.stop()
        for url in (
            f"{reverse('manage-security')}?status=all&page=1&type=leaked-password",
            f"{reverse('manage-security-detail', kwargs={'pk': finding.pk})}?page=1",
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    parse_qs(urlparse(response["Location"]).query)["next"], [url]
                )
                self.assertNotContains(response, self.user.username, status_code=302)

    def test_report_uses_second_factor_verification_for_enrolled_users(self) -> None:
        self.verification.stop()
        TOTPDevice.objects.create(user=self.admin, name="security-test", confirmed=True)
        response = self.client.get(reverse("manage-security"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response["Location"]).path,
            reverse("2fa-login", kwargs={"backend": "totp"}),
        )
        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.admin.pk,
            "time": int(time.time()),
        }
        session.save()
        self.assertContains(
            self.client.get(reverse("manage-security")), "Account security findings"
        )

    def test_report_explicit_processing_status(self) -> None:
        scan = SecurityScan.objects.create(actor=self.admin, total=25)
        url = reverse("manage-security") + f"?scan={scan.pk}"
        self.assertContains(self.client.get(url), "Processing is not complete")
        scan.state = "failed"
        scan.error = "Synthetic failure"
        scan.save()
        self.assertContains(self.client.get(url), "Processing failed")
        scan.state = "completed"
        scan.save()
        self.assertContains(self.client.get(url), "Password validation completed")

    def test_actions_only_use_checked_findings_on_current_page(self) -> None:
        findings = SecurityFinding.objects.bulk_create(
            [
                SecurityFinding(
                    user=self.user, finding_type="future-type", key=str(index)
                )
                for index in range(52)
            ]
        )
        response = self.client.get(reverse("manage-security"))
        visible = list(response.context["page"])
        off_page = next(
            finding
            for finding in findings
            if finding.pk not in {item.pk for item in visible}
        )
        response = self.client.post(
            reverse("manage-security"),
            {"action": "dismiss", "selected": [visible[0].pk, off_page.pk]},
        )
        self.assertEqual(response.context["count"], 1)
        self.assertNotIn("security-selections", self.client.session)
        response = self.client.post(reverse("manage-security"), {"action": "dismiss"})
        self.assertEqual(response.context["count"], 0)
        response = self.client.get(reverse("manage-security"))
        self.assertContains(response, 'type="button"')
        self.assertContains(response, 'data-security-select="all"')
        self.assertNotContains(response, 'name="selection"')
        self.assertNotContains(response, "Save selection")

    def test_progress_json_and_detail_pagination(self) -> None:
        scan = self.scan()
        response = self.client.get(
            reverse("manage-security-progress", kwargs={"pk": scan.pk}),
            {"format": "json"},
        )
        self.assertEqual(response.json()["state"], "completed")
        self.assertEqual(response.json()["progress"], 100)
        finding = SecurityFinding.objects.get(user=self.user)
        finding.evidence = {
            "matches": [
                {"row": index, "identifier": self.user.username, "method": "username"}
                for index in range(120)
            ]
        }
        finding.save()
        response = self.client.get(
            reverse("manage-security-detail", kwargs={"pk": finding.pk})
        )
        self.assertEqual(len(response.context["page"]), 100)
        response = self.client.get(
            reverse("manage-security-detail", kwargs={"pk": finding.pk}), {"page": 2}
        )
        self.assertEqual(len(response.context["page"]), 20)

    def test_expired_jobs_and_pre_migration_check(self) -> None:
        scan = SecurityScan.objects.create(
            actor=self.admin,
            state="running",
            created=timezone.now() - timedelta(hours=2),
        )
        store_input(scan, b"synthetic secret content")
        cleanup_security_scans()
        scan.refresh_from_db()
        self.assertEqual(scan.state, "failed")
        self.assertIsNone(cache.get(input_key(scan.pk)))
        with patch("django.db.connection.introspection.table_names", return_value=[]):
            self.assertEqual(list(check_account_security()), [])

    def test_notification_for_inactive_bot_and_missing_email(self) -> None:
        self.scan()
        self.user.is_active = False
        self.user.is_bot = True
        self.user.save()
        finding = SecurityFinding.objects.get(user=self.user)
        action = SecurityScan.objects.create(actor=self.admin, operation="reset")
        with patch("weblate.accounts.models.notify_auditlog.delay_on_commit") as notify:
            handle_finding(action, finding.pk)
        notify.assert_called_once()
        self.user.email = None
        audit = AuditLog(user=self.user, activity="password-leak")
        self.assertFalse(audit.should_notify())

    def test_input_configuration_ownership_and_invalid_ids(self) -> None:
        scan = SecurityScan.objects.create(actor=self.user, state="configuring")
        response = self.client.post(
            reverse("manage-security-upload"), {"scan": str(scan.pk)}
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse("manage-security"), {"scan": "invalid"})
        self.assertEqual(response.status_code, 404)

    def test_worker_failure_does_not_expose_credentials(self) -> None:
        scan = SecurityScan.objects.create(actor=self.admin)
        store_input(scan, b"username,password\nsecurity-target,synthetic-secret\n")
        with patch(
            "weblate.wladmin.security.check_password",
            side_effect=ValueError("synthetic-secret"),
        ):
            run_security_scan(str(scan.pk))
        scan.refresh_from_db()
        self.assertEqual(scan.state, "failed")
        self.assertNotIn("synthetic-secret", scan.error)
        self.assertIsNone(cache.get(input_key(scan.pk)))

    def test_validation_report_history_is_paginated_and_excludes_other_operations(
        self,
    ) -> None:
        reports = SecurityScan.objects.bulk_create(
            [
                SecurityScan(
                    actor=self.admin,
                    total=1,
                    processed=1,
                    state="completed",
                    summary={"accounts": 0},
                )
                for _ in range(52)
            ]
        )
        pending = SecurityScan.objects.create(
            actor=self.admin, total=2, state="pending"
        )
        failed = SecurityScan.objects.create(actor=self.admin, total=3, state="failed")
        reset = SecurityScan.objects.create(
            actor=self.admin, operation="reset", total=1, state="completed"
        )
        dismissed = SecurityScan.objects.create(
            actor=self.admin, operation="dismiss", total=1, state="completed"
        )
        configuring = SecurityScan.objects.create(
            actor=self.admin, state="configuring", total=1
        )
        unsubmitted = SecurityScan.objects.create(
            actor=self.admin, state="failed", total=0
        )
        url = reverse("manage-security-reports")
        response = self.client.get(url)
        self.assertContains(response, "Validation reports")
        self.assertEqual(response.context["page"].paginator.count, 54)
        self.assertEqual(len(response.context["page"]), 50)
        self.assertContains(response, pending.get_absolute_url())
        self.assertContains(response, failed.get_absolute_url())
        for excluded in [reset, dismissed, configuring, unsubmitted]:
            self.assertNotContains(response, excluded.get_absolute_url())
        response = self.client.get(url, {"page": 2})
        self.assertEqual(len(response.context["page"]), 4)
        self.assertContains(response, reports[0].get_absolute_url())
        with self.assertNumQueries(2):
            page = Paginator(validation_reports(), 50).get_page(1)
            for report in page:
                self.assertEqual(
                    report.actor.username if report.actor else None, self.admin.username
                )
                report.get_state_display()
                self.assertIn(report.matching_rows, [None, 0])
                self.assertIn(report.affected_accounts, [None, 0])
                report.get_absolute_url()

    def test_report_history_permissions_and_verification(self) -> None:
        self.verification.stop()
        url = reverse("manage-security-reports")
        response = self.client.get(url, {"page": 2})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            parse_qs(urlparse(response["Location"]).query)["next"], [f"{url}?page=2"]
        )
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_empty_and_handled_reports_remain_accessible(self) -> None:
        empty = self.scan(b"username,password\nunknown,synthetic-value\n")
        with patch(
            "weblate.wladmin.views.has_recent_sensitive_verification", return_value=True
        ):
            users = self.client.get(reverse("manage-users"))
        self.assertContains(users, "Security report (0 open findings)")
        self.assertContains(
            self.client.get(reverse("manage-security-reports")),
            empty.get_absolute_url(),
        )
        response = self.client.get(empty.get_absolute_url())
        self.assertContains(response, "Password validation completed")
        self.assertContains(response, "No security findings match")
        scan = self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        finding.status = "resolved"
        finding.save()
        response = self.client.get(scan.get_absolute_url())
        self.assertEqual(response.context["status"], "all")
        self.assertContains(response, self.user.username)
        self.assertContains(response, "Resolved")
        response = self.client.get(reverse("manage-security"))
        self.assertEqual(response.context["status"], "open")
        self.assertNotContains(response, "View details (1 match)")

    def test_finding_links_to_all_detecting_reports_and_uses_report_evidence(
        self,
    ) -> None:
        first = self.scan()
        second = self.scan(
            b"username,password\nSECURITY-TARGET@EXAMPLE.NET,synthetic-secret\n"
        )
        finding = SecurityFinding.objects.get(user=self.user)
        detail_url = reverse("manage-security-detail", kwargs={"pk": finding.pk})
        response = self.client.get(detail_url)
        self.assertContains(response, "Detected in reports")
        self.assertContains(response, first.get_absolute_url())
        self.assertContains(response, second.get_absolute_url())
        self.assertContains(response, "SECURITY-TARGET@EXAMPLE.NET")
        response = self.client.get(detail_url, {"scan": str(first.pk)})
        self.assertEqual(response.context["source_report"].pk, first.pk)
        self.assertEqual(response.context["page"][0]["identifier"], self.user.username)
        with self.assertNumQueries(2):
            findings, *_ = filtered_findings(RequestFactory().get("/"))
            for item in findings[:50]:
                for event in item.events.all():
                    event.scan.get_absolute_url()
                    self.assertEqual(
                        event.actor.username if event.actor else None,
                        self.admin.username,
                    )
        response = self.client.get(reverse("manage-security"))
        self.assertContains(response, first.get_absolute_url())
        self.assertContains(response, second.get_absolute_url())

    def test_security_breadcrumb_hierarchy_and_confirmation_return(self) -> None:
        scan = self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        root = reverse("manage-security")
        cases = [
            (root, ["Manage", "Users", "Security report"]),
            (
                reverse("manage-security-reports"),
                ["Manage", "Users", "Security report", "Validation reports"],
            ),
            (
                reverse("manage-security-upload"),
                ["Manage", "Users", "Security report", "Validate leaked passwords"],
            ),
        ]
        for url, expected in cases:
            response = self.client.get(url)
            tree = html.fromstring(response.content)
            crumbs = tree.xpath(
                '//ol[@class="breadcrumb"]/li[contains(@class,"breadcrumb-item")]'
            )
            self.assertEqual([item.text_content().strip() for item in crumbs], expected)
            self.assertEqual(crumbs[-1].get("aria-current"), "page")
        detail = self.client.get(
            reverse("manage-security-detail", kwargs={"pk": finding.pk}),
            {"scan": str(scan.pk)},
        )
        crumbs = detail.context["security_breadcrumbs"]
        self.assertEqual(
            [label for label, _url in crumbs[:4]],
            ["Manage", "Users", "Security report", "Validation reports"],
        )
        self.assertEqual(crumbs[-2][1], scan.get_absolute_url())
        self.assertIn("Finding for", crumbs[-1][0])
        report_url = scan.get_absolute_url() + "&status=open&page=1"
        response = self.client.post(
            report_url, {"action": "dismiss", "selected": [finding.pk]}
        )
        self.assertEqual(response.context["cancel_url"], report_url)
        self.assertEqual(response.context["source_report"].pk, scan.pk)
        self.assertContains(response, "Confirm security action")
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(
                reverse("manage-security-confirm"), {"token": response.context["token"]}
            )
        self.assertEqual(
            parse_qs(urlparse(result["Location"]).query)["scan"], [str(scan.pk)]
        )
        result = self.client.get(result["Location"], follow=True)
        self.assertEqual(result.context["source_report"].pk, scan.pk)
        self.assertContains(result, "Security action completed")

    def test_progress_breadcrumbs_keep_source_report(self) -> None:
        scan = SecurityScan.objects.create(actor=self.admin, total=2, state="running")
        response = self.client.get(
            reverse("manage-security-progress", kwargs={"pk": scan.pk})
        )
        self.assertEqual(response.context["source_report"].pk, scan.pk)
        self.assertEqual(
            response.context["security_breadcrumbs"][-1], ("Progress", None)
        )
        self.assertEqual(
            response.context["security_breadcrumbs"][-2][1], scan.get_absolute_url()
        )
        operation = SecurityScan.objects.create(
            actor=self.admin, total=1, operation="dismiss", state="running"
        )
        url = reverse("manage-security-progress", kwargs={"pk": operation.pk})
        response = self.client.get(url, {"scan": str(scan.pk)})
        self.assertIn(f"scan={scan.pk}", response.context["progress_url"])
        self.assertEqual(response.context["source_report"].pk, scan.pk)
        response = self.client.get(url, {"scan": str(scan.pk), "format": "json"})
        self.assertEqual(
            parse_qs(urlparse(response.json()["url"]).query)["scan"], [str(scan.pk)]
        )

    def test_report_origins_are_paginated(self) -> None:
        scan = self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        reports = SecurityScan.objects.bulk_create(
            [
                SecurityScan(actor=self.admin, total=1, state="completed")
                for _ in range(51)
            ]
        )
        SecurityFindingEvent.objects.bulk_create(
            [
                SecurityFindingEvent(
                    finding=finding, scan=report, actor=self.admin, action="detected"
                )
                for report in reports
            ]
        )
        url = reverse("manage-security-detail", kwargs={"pk": finding.pk})
        response = self.client.get(url)
        self.assertEqual(len(response.context["reports_page"]), 50)
        response = self.client.get(url, {"reports_page": "2", "scan": str(scan.pk)})
        self.assertEqual(len(response.context["reports_page"]), 2)
        self.assertEqual(response.context["source_report"].pk, scan.pk)

    def test_report_metadata_escapes_filename_and_uses_original_submitter(self) -> None:
        scan = SecurityScan.objects.create(
            actor=self.user,
            filename="notes <tag>.csv",
            total=1,
            state="completed",
        )
        response = self.client.get(scan.get_absolute_url())
        self.assertContains(response, "notes &lt;tag&gt;.csv")
        self.assertNotContains(response, "notes <tag>.csv")
        tree = html.fromstring(response.content)
        submitter = tree.xpath(
            '//dt[normalize-space()="Submitted by"]/following-sibling::dd[1]'
        )
        self.assertEqual(submitter[0].text_content().strip(), self.user.username)
        history = self.client.get(reverse("manage-security-reports"))
        self.assertContains(history, "notes &lt;tag&gt;.csv")
        tree = html.fromstring(history.content)
        row = tree.xpath("//a[@href=$url]/ancestor::tr", url=scan.get_absolute_url())[0]
        self.assertEqual(row.xpath("td")[2].text_content().strip(), self.user.username)
        scan.filename = ""
        scan.save(update_fields=["filename"])
        self.assertContains(self.client.get(scan.get_absolute_url()), "Not recorded")
        self.assertContains(
            self.client.get(reverse("manage-security-reports")), "Not recorded"
        )

    def test_leak_reset_preserves_history_and_rejects_password_reuse(self) -> None:
        self.assertFalse(AuditLog.objects.get_past_passwords(self.user).exists())
        self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        old_hash = self.user.password
        operation = SecurityScan.objects.create(actor=self.admin, operation="reset")
        self.assertEqual(handle_finding(operation, finding.pk), "password-reset")
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        with self.assertRaises(ValidationError) as caught:
            PastPasswordsValidator().validate("synthetic-secret", self.user)
        self.assertEqual(caught.exception.code, "password-past")
        PastPasswordsValidator().validate("new-unique-password", self.user)
        audit = AuditLog.objects.get(user=self.user, activity="password-leak")
        self.assertEqual(audit.params["password"], old_hash)
        self.assertNotIn(old_hash, str(audit.get_message()))
        self.assertEqual(audit.params["username"], self.admin.username)

    def test_rotated_secret_with_fallback_still_remediates_original_finding(
        self,
    ) -> None:
        self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        token = reset_api_token(self.user)
        original_key = settings.SECRET_KEY
        operation = SecurityScan.objects.create(actor=self.admin, operation="reset")
        with override_settings(
            SECRET_KEY=get_random_string(50),
            SECRET_KEY_FALLBACKS=["unrelated-key", original_key],
        ):
            self.assertEqual(handle_finding(operation, finding.pk), "password-reset")
        self.user.refresh_from_db()
        finding.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(finding.status, "resolved")
        self.assertFalse(type(token).objects.filter(pk=token.pk).exists())
        self.assertEqual(
            AuditLog.objects.filter(user=self.user, activity="password-leak").count(), 1
        )

    def test_rotated_secret_reuses_existing_finding_and_reopens_dismissal(self) -> None:
        first = self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        operation = SecurityScan.objects.create(actor=self.admin, operation="dismiss")
        handle_finding(operation, finding.pk)
        original_key = settings.SECRET_KEY
        with override_settings(
            SECRET_KEY=get_random_string(50), SECRET_KEY_FALLBACKS=[original_key]
        ):
            second = self.scan()
        self.assertEqual(SecurityFinding.objects.filter(user=self.user).count(), 1)
        finding.refresh_from_db()
        self.assertEqual(finding.status, "open")
        self.assertEqual(
            set(
                finding.events.filter(action="detected").values_list(
                    "scan_id", flat=True
                )
            ),
            {first.pk, second.pk},
        )

    def test_rotated_secret_does_not_reset_a_changed_password(self) -> None:
        self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        token = reset_api_token(self.user)
        original_key = settings.SECRET_KEY
        self.user.set_password("new-unique-password")
        self.user.save(update_fields=["password"])
        operation = SecurityScan.objects.create(actor=self.admin, operation="reset")
        with override_settings(
            SECRET_KEY=get_random_string(50), SECRET_KEY_FALLBACKS=[original_key]
        ):
            self.assertEqual(handle_finding(operation, finding.pk), "password-changed")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-unique-password"))
        self.assertTrue(type(token).objects.filter(pk=token.pk).exists())
        self.assertFalse(
            AuditLog.objects.filter(user=self.user, activity="password-leak").exists()
        )

    def test_rendered_security_lists_have_valid_html_structure(self) -> None:
        scan = self.scan()
        finding = SecurityFinding.objects.get(user=self.user)
        urls = [
            reverse("manage-security"),
            scan.get_absolute_url(),
            reverse("manage-security-reports"),
            reverse("manage-security-upload"),
            reverse("manage-security-detail", kwargs={"pk": finding.pk}),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                tree = html.fromstring(response.content)
                breadcrumbs = tree.xpath(
                    '//ol[@class="breadcrumb"]/li[contains(@class,"breadcrumb-item")]'
                )
                self.assertGreaterEqual(len(breadcrumbs), 3)
                for item in breadcrumbs:
                    self.assertEqual(item.getparent().tag, "ol")
                for listing in tree.xpath(
                    '//ol[@class="breadcrumb"] | //dl | //details/ul'
                ):
                    allowed = (
                        {"dt", "dd", "div", "script", "template", "style"}
                        if listing.tag == "dl"
                        else {"li", "script", "template", "style"}
                    )
                    self.assertFalse((listing.text or "").strip())
                    for child in listing:
                        self.assertIn(child.tag, allowed)
                        self.assertFalse((child.tail or "").strip())

    def prepare_legacy_password_finding(self) -> str:
        encoded = PBKDF2PasswordHasher().encode(
            "synthetic-secret", "security-salt", iterations=1
        )
        self.user.password = encoded
        self.user.save(update_fields=["password"])
        self.scan()
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, encoded)
        return encoded

    def test_login_hash_upgrade_keeps_leak_finding_actionable(self) -> None:
        original = self.prepare_legacy_password_finding()
        finding = SecurityFinding.objects.get(user=self.user)
        token = reset_api_token(self.user)
        self.assertTrue(
            self.client.login(
                username=self.user.username,
                password="synthetic-secret",  # ruff: ignore[hardcoded-password-func-arg]
            )
        )
        self.user.refresh_from_db()
        finding.refresh_from_db()
        self.assertNotEqual(self.user.password, original)
        self.assertEqual(finding.status, "open")
        self.assertEqual(finding.events.filter(action="detected").count(), 1)
        operation = SecurityScan.objects.create(actor=self.admin, operation="reset")
        self.assertEqual(handle_finding(operation, finding.pk), "password-reset")
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertFalse(type(token).objects.filter(pk=token.pk).exists())
        with self.assertRaises(ValidationError):
            PastPasswordsValidator().validate("synthetic-secret", self.user)

    @override_settings(
        PASSWORD_HASHERS=[
            "django.contrib.auth.hashers.PBKDF2PasswordHasher",
            "django.contrib.auth.hashers.MD5PasswordHasher",
        ]
    )
    def test_work_factor_upgrade_preserves_fallback_key_finding(self) -> None:
        original = self.prepare_legacy_password_finding()
        finding = SecurityFinding.objects.get(user=self.user)
        original_key = settings.SECRET_KEY
        with override_settings(
            SECRET_KEY=get_random_string(50), SECRET_KEY_FALLBACKS=[original_key]
        ):
            self.assertTrue(self.user.check_password("synthetic-secret"))
            self.user.refresh_from_db()
            self.assertTrue(self.user.password.startswith("pbkdf2_sha256$"))
            self.assertNotEqual(self.user.password, original)
            operation = SecurityScan.objects.create(actor=self.admin, operation="reset")
            self.assertEqual(handle_finding(operation, finding.pk), "password-reset")
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_async_hash_upgrade_keeps_leak_finding_actionable(self) -> None:
        original = self.prepare_legacy_password_finding()
        finding = SecurityFinding.objects.get(user=self.user)
        self.assertTrue(async_to_sync(self.user.acheck_password)("synthetic-secret"))
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.password, original)
        operation = SecurityScan.objects.create(actor=self.admin, operation="reset")
        self.assertEqual(handle_finding(operation, finding.pk), "password-reset")

    def test_incorrect_password_does_not_upgrade_finding(self) -> None:
        original = self.prepare_legacy_password_finding()
        finding = SecurityFinding.objects.get(user=self.user)
        original_fingerprint = finding.key
        self.assertFalse(self.user.check_password("incorrect-secret"))
        self.user.refresh_from_db()
        finding.refresh_from_db()
        self.assertEqual(self.user.password, original)
        self.assertEqual(finding.key, original_fingerprint)
        self.assertEqual(finding.status, "open")

    def test_hash_upgrade_does_not_reopen_dismissed_finding(self) -> None:
        self.prepare_legacy_password_finding()
        finding = SecurityFinding.objects.get(user=self.user)
        operation = SecurityScan.objects.create(actor=self.admin, operation="dismiss")
        handle_finding(operation, finding.pk)
        self.assertTrue(self.user.check_password("synthetic-secret"))
        finding.refresh_from_db()
        self.assertEqual(finding.status, "dismissed")
        self.assertEqual(finding.events.filter(action="detected").count(), 1)
        self.scan()
        finding.refresh_from_db()
        self.assertEqual(finding.status, "open")
        self.assertEqual(SecurityFinding.objects.filter(user=self.user).count(), 1)

    def test_actual_password_change_after_upgrade_is_still_skipped(self) -> None:
        self.prepare_legacy_password_finding()
        finding = SecurityFinding.objects.get(user=self.user)
        self.assertTrue(self.user.check_password("synthetic-secret"))
        self.user.set_password("new-unique-password")
        self.user.save(update_fields=["password"])
        token = reset_api_token(self.user)
        operation = SecurityScan.objects.create(actor=self.admin, operation="reset")
        self.assertEqual(handle_finding(operation, finding.pk), "password-changed")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-unique-password"))
        self.assertTrue(type(token).objects.filter(pk=token.pk).exists())

    def test_hash_upgrade_does_not_restore_concurrently_reset_password(self) -> None:
        original = self.prepare_legacy_password_finding()
        finding = SecurityFinding.objects.get(user=self.user)
        operation = SecurityScan.objects.create(actor=self.admin, operation="reset")

        def verify_then_reset(
            raw_password: str | None, encoded: str
        ) -> tuple[bool, bool]:
            result = verify_password(raw_password, encoded)
            if encoded == original and result[0]:
                self.assertEqual(
                    handle_finding(operation, finding.pk), "password-reset"
                )
                self.user.refresh_from_db()
            return result

        with patch(
            "weblate.auth.models.verify_password", side_effect=verify_then_reset
        ):
            self.assertFalse(self.user.check_password("synthetic-secret"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        finding.refresh_from_db()
        self.assertEqual(finding.status, "resolved")
