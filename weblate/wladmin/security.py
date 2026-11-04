# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Account security checks. Uploaded credentials never enter task payloads."""

from __future__ import annotations

import base64
import csv
import io
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from itertools import batched, islice
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, Q, Value, When
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.translation import gettext, gettext_lazy, gettext_noop
from django.views.decorators.debug import sensitive_variables

from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.accounts.utils import delete_api_tokens
from weblate.auth.models import User
from weblate.utils.email import email_key, email_key_expression
from weblate.wladmin.models import SecurityFinding, SecurityFindingEvent, SecurityScan

if TYPE_CHECKING:
    from uuid import UUID

MAX_UPLOAD = 10 * 1024 * 1024
MAX_ROWS = 50000
INPUT_TTL = 3600
LEAKED_PASSWORD = "leaked-password"  # ruff: ignore[hardcoded-password-string]


@dataclass(frozen=True)
class FindingHandler:
    label: object
    can_reset: bool = False


FINDING_HANDLERS = {
    LEAKED_PASSWORD: FindingHandler(gettext_lazy("Leaked password"), can_reset=True),
}


def fingerprint(encoded: str, *, secret: str | bytes | None = None) -> str:
    return salted_hmac(
        "account-security-password", encoded, secret=secret, algorithm="sha256"
    ).hexdigest()


def password_fingerprints(encoded: str) -> list[str]:
    """Recognize findings created before a configured secret-key rotation."""
    return [
        fingerprint(encoded, secret=secret)
        for secret in [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
    ]


def upgrade_password_finding_fingerprints(
    user: User, old_password: str, *, using: str
) -> None:
    """Carry findings through a hash upgrade while holding the account lock."""
    fingerprints = dict(
        zip(
            password_fingerprints(old_password),
            password_fingerprints(user.password),
            strict=True,
        )
    )
    SecurityFinding.objects.using(using).filter(
        user=user,
        finding_type=LEAKED_PASSWORD,
        key__in=fingerprints,
    ).update(
        key=Case(*[When(key=old, then=Value(new)) for old, new in fingerprints.items()])
    )


def cipher() -> Fernet:
    key = salted_hmac(
        "account-security-upload", "encryption", algorithm="sha256"
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def input_key(scan_id: UUID) -> str:
    return f"account-security-input:{scan_id}"


@sensitive_variables()
def store_input(scan: SecurityScan, data: bytes) -> None:
    cache.set(input_key(scan.pk), cipher().encrypt(data), INPUT_TTL)


@sensitive_variables()
def load_input(scan: SecurityScan) -> bytes:
    encrypted = cache.get(input_key(scan.pk))
    if encrypted is None:
        raise ValidationError(
            gettext("The uploaded report has expired. Upload it again.")
        )
    try:
        return cipher().decrypt(encrypted, ttl=INPUT_TTL)
    except InvalidToken:
        raise ValidationError(
            gettext("The uploaded report has expired. Upload it again.")
        ) from None


@sensitive_variables()
def report_columns(first_row: list[str], config: dict) -> tuple[int, int]:
    manual = config.get("identifier_column") and config.get("password_column")
    header = config.get("header", True)
    if manual:
        identifier = int(config["identifier_column"]) - 1
        password = int(config["password_column"]) - 1
    else:
        names = [name.strip().casefold() for name in first_row]
        identifiers = [
            index
            for index, name in enumerate(names)
            if name in {"username", "user", "email", "e-mail", "login"}
        ]
        passwords = [
            index
            for index, name in enumerate(names)
            if name in {"password", "pass", "passwd"}
        ]
        if not header or len(identifiers) != 1 or len(passwords) != 1:
            raise ValidationError(
                gettext(
                    "Could not detect the credential columns. Configure their column numbers."
                )
            )
        identifier, password = identifiers[0], passwords[0]
    if identifier == password or min(identifier, password) < 0:
        raise ValidationError(
            gettext("Choose different identifier and password columns.")
        )
    return identifier, password


@sensitive_variables()
def parse_report(data: bytes, config: dict) -> list[tuple[int, str, str]]:
    """Extract fields without returning offending values in validation errors."""
    if len(data) > MAX_UPLOAD:
        raise ValidationError(gettext("The report exceeds the 10 MiB limit."))
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        raise ValidationError(gettext("Upload a UTF-8 encoded CSV file.")) from None
    delimiter = config.get("delimiter")
    if delimiter == "\\t":
        delimiter = "\t"
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(text[:16384], delimiters=",;\t|").delimiter
        except csv.Error:
            raise ValidationError(
                gettext(
                    "Could not detect the delimiter. Configure the CSV columns and delimiter."
                )
            ) from None
    if len(delimiter) != 1 or delimiter in '\r\n"':
        raise ValidationError(gettext("Choose a single delimiter character."))
    try:
        rows = list(
            islice(
                csv.reader(
                    io.StringIO(text, newline=""), delimiter=delimiter, strict=True
                ),
                MAX_ROWS + 2,
            )
        )
    except csv.Error:
        raise ValidationError(
            gettext("The file contains malformed CSV quoting.")
        ) from None
    if not rows:
        raise ValidationError(gettext("The report is empty."))
    header = config.get("header", True)
    identifier, password = report_columns(rows[0], config)
    if len(rows) - int(header) > MAX_ROWS:
        raise ValidationError(gettext("The report exceeds the 50,000 row limit."))
    result = []
    for number, row in enumerate(rows, 1):
        if number == 1 and header:
            continue
        if not row:
            continue
        if (
            max(identifier, password) >= len(row)
            or not row[identifier].strip()
            or not row[password]
        ):
            result.append((number, "", ""))
        else:
            result.append((number, row[identifier].strip(), row[password]))
    if not result:
        raise ValidationError(gettext("The report contains no credential rows."))
    return result


@transaction.atomic
def record_detection(scan: SecurityScan, user: User, evidence: dict) -> None:
    # Lock the account first, the same order used by remediation.
    current = User.objects.select_for_update().get(pk=user.pk)
    if current.password != user.password:
        return
    finding = (
        SecurityFinding.objects.filter(
            user=current,
            finding_type=LEAKED_PASSWORD,
            key__in=password_fingerprints(user.password),
        )
        .order_by("first_seen", "pk")
        .first()
    )
    if finding is None:
        finding = SecurityFinding.objects.create(
            user=current,
            finding_type=LEAKED_PASSWORD,
            key=fingerprint(user.password),
        )
    event, created = SecurityFindingEvent.objects.get_or_create(
        finding=finding,
        scan=scan,
        action="detected",
        defaults={"actor_id": scan.actor_id, "evidence": evidence},
    )
    if not created:
        return
    # An older in-flight scan must not undo a later administrative decision.
    if finding.handled_at is None or scan.created > finding.handled_at:
        finding.status = SecurityFinding.Status.OPEN
        finding.handled_at = None
    finding.last_seen = timezone.now()
    finding.evidence = event.evidence
    finding.save(update_fields=["status", "handled_at", "last_seen", "evidence"])


@sensitive_variables()
def match_accounts(
    batch: tuple[tuple[int, str, str], ...],
) -> dict[str, dict[int, tuple[User, str]]]:
    identifiers = {identifier for _, identifier, _ in batch if identifier}
    emails = {email_key(identifier) for identifier in identifiers}
    users = User.objects.alias(normalized_email=email_key_expression("email")).filter(
        Q(username__in=identifiers) | Q(normalized_email__in=emails)
    )
    matches: dict[str, dict[int, tuple[User, str]]] = defaultdict(dict)
    for user in users:
        if user.username in identifiers:
            matches[user.username][user.pk] = (user, "username")
        if user.email and email_key(user.email) in emails:
            for identifier in identifiers:
                if email_key(identifier) == email_key(user.email):
                    matches[identifier].setdefault(user.pk, (user, "email"))
    secondary = (
        VerifiedEmail.objects.alias(normalized_email=email_key_expression("email"))
        .filter(
            normalized_email__in=emails,
        )
        .select_related("social__user")
    )
    for entry in secondary:
        for identifier in identifiers:
            if email_key(identifier) == email_key(entry.email):
                user = entry.social.user
                matches[identifier].setdefault(user.pk, (user, "verified-email"))
    return matches


@sensitive_variables()
def validate_credentials(scan: SecurityScan, rows: list[tuple[int, str, str]]) -> None:
    counts: Counter = Counter()
    seen: set[tuple[str, str]] = set()
    affected: set[int] = set()
    scan.total = len(rows)
    scan.save(update_fields=["total"])
    for batch in batched(rows, 250):
        check_deadline(scan)
        matches = match_accounts(batch)
        evidence: dict[int, tuple[User, list[dict]]] = {}
        for number, identifier, password in batch:
            if not identifier:
                counts["malformed"] += 1
            elif (identifier, password) in seen:
                counts["duplicate"] += 1
            else:
                seen.add((identifier, password))
                candidates = matches.get(identifier, {})
                if not candidates:
                    counts["unknown"] += 1
                elif len(candidates) != 1:
                    counts["ambiguous"] += 1
                else:
                    user, method = next(iter(candidates.values()))
                    if not user.has_usable_password() or user.is_anonymous:
                        counts["unusable"] += 1
                    else:
                        counts["checked"] += 1
                        if check_password(password, user.password):
                            counts["matched"] += 1
                            affected.add(user.pk)
                            evidence.setdefault(user.pk, (user, []))[1].append(
                                {
                                    "row": number,
                                    "identifier": identifier,
                                    "method": method,
                                }
                            )
                        else:
                            counts["mismatch"] += 1
            scan.processed += 1
        for user, details in evidence.values():
            # Merge row details when the same account occurs in multiple batches.
            previous = SecurityFindingEvent.objects.filter(
                scan=scan, finding__user=user, action="detected"
            ).first()
            if previous:
                previous.evidence["matches"].extend(details)
                previous.save(update_fields=["evidence"])
                SecurityFinding.objects.filter(pk=previous.finding_id).update(
                    evidence=previous.evidence
                )
            else:
                record_detection(scan, user, {"matches": details})
        counts["accounts"] = len(affected)
        scan.summary = dict(counts)
        scan.save(update_fields=["processed", "summary"])


@transaction.atomic
def handle_finding(scan: SecurityScan, finding_id: int) -> str:
    candidate = (
        SecurityFinding.objects.filter(pk=finding_id)
        .values_list("user_id", flat=True)
        .first()
    )
    if candidate is None:
        return "skipped"
    user = User.objects.select_for_update().get(pk=candidate)
    finding = SecurityFinding.objects.select_for_update().get(pk=finding_id)
    if finding.status != SecurityFinding.Status.OPEN:
        return "skipped"
    if scan.operation == "dismiss":
        status, reason = SecurityFinding.Status.DISMISSED, "dismissed"
    else:
        handler = FINDING_HANDLERS.get(finding.finding_type)
        if handler is None or not handler.can_reset:
            return "unsupported"
        status = SecurityFinding.Status.RESOLVED
        if not any(
            constant_time_compare(finding.key, candidate)
            for candidate in password_fingerprints(user.password)
        ):
            reason = "password-changed"
        else:
            old_password = user.password
            user.set_unusable_password()
            user.save(update_fields=["password"])
            delete_api_tokens(user)
            AuditLog.objects.create(
                user,
                None,
                "password-leak",
                actor=scan.actor,
                password=old_password,
            )
            reason = "password-reset"
    finding.status = status
    finding.handled_at = timezone.now()
    finding.save(update_fields=["status", "handled_at"])
    SecurityFindingEvent.objects.create(
        finding=finding, scan=scan, actor=scan.actor, action=status, reason=reason
    )
    return reason


def check_deadline(scan: SecurityScan) -> None:
    if timezone.now() > scan.created + timedelta(seconds=INPUT_TTL):
        raise TimeoutError


@sensitive_variables()
def execute_scan(scan: SecurityScan) -> None:
    if (
        scan.actor is None
        or not scan.actor.is_active
        or not scan.actor.has_perm("user.edit")
        or not scan.actor.has_perm("management.use")
    ):
        scan.error = gettext_noop(
            "The initiating administrator no longer has permission to perform this operation."
        )
        scan.state = "failed"
    elif scan.operation == "validate":
        rows = parse_report(load_input(scan), scan.summary.get("config", {}))
        validate_credentials(scan, rows)
        scan.state = "completed"
    else:
        counts: Counter = Counter()
        for finding_id in scan.summary.get("finding_ids", []):
            check_deadline(scan)
            counts[handle_finding(scan, finding_id)] += 1
            scan.processed += 1
            SecurityScan.objects.filter(pk=scan.pk).update(processed=scan.processed)
        scan.summary = dict(counts)
        scan.state = "completed"


@sensitive_variables()
def run_security_scan(scan_id: str) -> None:
    scan = SecurityScan.objects.select_related("actor").get(pk=scan_id)
    if not SecurityScan.objects.filter(pk=scan.pk, state="pending").update(
        state="running"
    ):
        return
    try:
        execute_scan(scan)
    except Exception:
        # Do not send exceptions or their credential-bearing frames to error reporting.
        scan.state = "failed"
        scan.error = gettext_noop(
            "The security operation failed. Review any findings already recorded and start a new operation."
        )
    finally:
        cache.delete(input_key(scan.pk))
        scan.completed = timezone.now()
        scan.save(update_fields=["summary", "state", "error", "completed"])
