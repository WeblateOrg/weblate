# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadhandler import MemoryFileUploadHandler, StopUpload
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

from weblate.accounts.utils import (
    has_recent_sensitive_verification,
    sensitive_verification_redirect,
)
from weblate.auth.decorators import management_permission_required
from weblate.utils import messages
from weblate.utils.lock import WeblateLock
from weblate.wladmin.forms import SecurityUploadForm
from weblate.wladmin.models import SecurityFinding, SecurityFindingEvent, SecurityScan
from weblate.wladmin.security import (
    FINDING_HANDLERS,
    MAX_UPLOAD,
    input_key,
    load_input,
    parse_report,
    store_input,
)
from weblate.wladmin.tasks import security_scan_task
from weblate.wladmin.views import MENU

if TYPE_CHECKING:
    from typing import IO

    from django.db.models import QuerySet

    from weblate.auth.models import AuthenticatedHttpRequest


class SecurityUploadHandler(MemoryFileUploadHandler):
    """Prevent sensitive uploads from spilling to unencrypted temporary files."""

    def handle_raw_input(
        self,
        input_data: IO[bytes],
        META: dict[str, str],  # ruff: ignore[invalid-argument-name]
        content_length: int,
        boundary: str,
        encoding: str | None = None,
    ) -> None:
        self.activated = True
        self.received = 0

    def receive_data_chunk(self, raw_data: bytes, start: int) -> bytes | None:
        self.received += len(raw_data)
        if self.received > MAX_UPLOAD:
            raise StopUpload(connection_reset=False)
        return super().receive_data_chunk(raw_data, start)


def parse_scan_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise Http404 from None


def context(
    *,
    section: str | None = None,
    source_report: SecurityScan | None = None,
    **kwargs: object,
) -> dict[str, Any]:
    breadcrumbs: list[tuple[str, str | None]] = [
        (gettext("Manage"), reverse("manage")),
        (gettext("Users"), reverse("manage-users")),
        (gettext("Security report"), reverse("manage-security")),
    ]
    title = None
    if source_report:
        title = gettext("Report from %(date)s") % {
            "date": date_format(
                timezone.localtime(source_report.created), "DATETIME_FORMAT"
            ),
        }
        if source_report.filename:
            title = gettext("%(filename)s — %(report)s") % {
                "filename": source_report.filename,
                "report": title,
            }
        breadcrumbs.extend(
            [
                (gettext("Validation reports"), reverse("manage-security-reports")),
                (title, source_report.get_absolute_url()),
            ]
        )
    if section:
        breadcrumbs.append((section, None))
    breadcrumbs[-1] = (breadcrumbs[-1][0], None)
    return {
        "menu_items": MENU,
        "menu_page": "users",
        "security_breadcrumbs": breadcrumbs,
        "report_title": title,
        "source_report": source_report,
        **kwargs,
    }


def upload_context(
    form: SecurityUploadForm,
    scan: SecurityScan | None = None,
) -> dict[str, Any]:
    return context(section=gettext("Validate leaked passwords"), form=form, scan=scan)


@csrf_exempt
@management_permission_required("user.edit")
def security_upload(request: AuthenticatedHttpRequest) -> HttpResponse:
    # CSRF middleware must defer multipart parsing until this handler is installed.
    request.upload_handlers = [SecurityUploadHandler(request)]
    return protected_security_upload(request)


@csrf_protect
@sensitive_post_parameters()
@sensitive_variables()
def protected_security_upload(request: AuthenticatedHttpRequest) -> HttpResponse:
    if not has_recent_sensitive_verification(request):
        if request.method == "POST":
            messages.info(
                request,
                gettext(
                    "Your identity verification has expired. Confirm your identity, "
                    "then select and upload the CSV report again."
                ),
            )
        return sensitive_verification_redirect(request, request.get_full_path())
    form = SecurityUploadForm(request.POST or None, request.FILES or None)
    scan = None
    if request.method == "POST" and form.is_valid():
        if request.POST.get("scan"):
            scan = get_object_or_404(
                SecurityScan,
                pk=parse_scan_id(request.POST["scan"]),
                actor=request.user,
                state="configuring",
            )
        if form.cleaned_data["report"]:
            if scan:
                cache.delete(input_key(scan.pk))
            scan = SecurityScan.objects.create(
                actor=request.user,
                state="configuring",
                filename=form.cleaned_data["report"].name,
            )
            try:
                store_input(scan, form.cleaned_data["report"].read(MAX_UPLOAD + 1))
            except Exception:
                form.add_error(
                    None, gettext("Could not store the encrypted upload. Try again.")
                )
                return render(
                    request, "manage/security-upload.html", upload_context(form=form)
                )
        if scan is None:
            form.add_error("report", gettext("Choose a CSV report of at most 10 MiB."))
        else:
            config = {
                key: value
                for key, value in form.cleaned_data.items()
                if key != "report"
            }
            try:
                total = len(parse_report(load_input(scan), config))
            except ValidationError as error:
                form.add_error(None, error)
            except Exception:
                form.add_error(
                    None,
                    gettext("Could not read the uploaded report. Upload it again."),
                )
            else:
                scan.total = total
                scan.summary = {"config": config}
                scan.state = "pending"
                scan.save(update_fields=["total", "summary", "state"])
                security_scan_task.delay(str(scan.pk))
                return redirect("manage-security-progress", pk=scan.pk)
    return render(
        request, "manage/security-upload.html", upload_context(form=form, scan=scan)
    )


@management_permission_required("user.edit")
def security_progress(request: AuthenticatedHttpRequest, pk: UUID) -> HttpResponse:
    scan = get_object_or_404(SecurityScan, pk=pk)
    source_report = (
        scan if scan.operation in {"validate", "legacy-email-check"} else None
    )
    target = scan.get_absolute_url()
    if scan.operation not in {"validate", "legacy-email-check"} and request.GET.get(
        "scan"
    ):
        source_report = get_object_or_404(
            SecurityScan,
            pk=parse_scan_id(request.GET["scan"]),
            operation__in=("validate", "legacy-email-check"),
        )
        target += f"&scan={source_report.pk}"
    if request.GET.get("format") == "json":
        return JsonResponse(
            {
                "state": scan.state,
                "progress": scan.progress,
                "processed": scan.processed,
                "total": scan.total,
                "error": gettext(scan.error),
                "url": target,
            }
        )
    if scan.state == "completed":
        return redirect(target)
    progress_query = request.GET.copy()
    progress_query["format"] = "json"
    return render(
        request,
        "manage/security-progress.html",
        context(
            section=gettext("Progress"),
            source_report=source_report,
            scan=scan,
            error=gettext(scan.error),
            progress_url=f"{request.path}?{progress_query.urlencode()}",
        ),
    )


def validation_reports() -> QuerySet[SecurityScan]:
    return (
        SecurityScan.objects.filter(
            operation__in=("validate", "legacy-email-check"), total__gt=0
        )
        .exclude(
            state="configuring",
        )
        .select_related("actor")
        .order_by("-created", "pk")
    )


@management_permission_required("user.edit")
def security_reports(request: AuthenticatedHttpRequest) -> HttpResponse:
    if not has_recent_sensitive_verification(request):
        return sensitive_verification_redirect(request, request.get_full_path())
    page = Paginator(validation_reports(), 50).get_page(request.GET.get("page"))
    return render(
        request,
        "manage/security-reports.html",
        context(section=gettext("Validation reports"), page=page),
    )


def filtered_findings(
    request: HttpRequest,
) -> tuple[QuerySet[SecurityFinding], str, str, SecurityScan | None]:
    findings = (
        SecurityFinding.objects.select_related("user")
        .prefetch_related(
            Prefetch(
                "events",
                queryset=SecurityFindingEvent.objects.select_related("actor", "scan")
                .defer("scan__summary", "scan__error")
                .order_by("timestamp", "pk"),
            )
        )
        .order_by("-last_seen", "pk")
    )
    status = request.GET.get("status", "all" if request.GET.get("scan") else "open")
    if status in SecurityFinding.Status.values:
        findings = findings.filter(status=status)
    else:
        status = "all"
    kind = request.GET.get("type", "")
    if kind:
        findings = findings.filter(finding_type=kind)
    scan = None
    if request.GET.get("scan"):
        scan = get_object_or_404(
            SecurityScan.objects.select_related("actor"),
            pk=parse_scan_id(request.GET["scan"]),
            operation__in=("validate", "legacy-email-check"),
        )
        findings = findings.filter(events__scan=scan, events__action="detected")
    return findings, status, kind, scan


@management_permission_required("user.edit")
def security_findings(request: AuthenticatedHttpRequest) -> HttpResponse:
    if not has_recent_sensitive_verification(request):
        return sensitive_verification_redirect(request, request.get_full_path())
    findings, status, kind, scan = filtered_findings(request)
    page = Paginator(findings, 50).get_page(request.GET.get("page"))
    if request.method == "POST":
        action = request.POST.get("action")
        if action not in {"reset", "cleanup", "dismiss"}:
            return HttpResponse(status=400)
        selected = set(request.POST.getlist("selected"))
        visible_ids = [finding.pk for finding in page if str(finding.pk) in selected]
        chosen = findings.filter(status="open", pk__in=visible_ids)
        if action == "reset":
            chosen = chosen.filter(
                finding_type__in=[
                    key
                    for key, handler in FINDING_HANDLERS.items()
                    if handler.can_reset
                ]
            )
        elif action == "cleanup":
            chosen = chosen.filter(
                finding_type__in=[
                    key
                    for key, handler in FINDING_HANDLERS.items()
                    if handler.can_cleanup
                ]
            )
        ids = list(chosen.values_list("pk", flat=True))
        token = str(uuid4())
        cache.set(
            f"security-confirm:{token}",
            {
                "actor": request.user.pk,
                "ids": ids,
                "action": action,
                "return_url": request.get_full_path(),
                "scan": str(scan.pk) if scan else None,
            },
            600,
        )
        return render(
            request,
            "manage/security-confirm.html",
            context(
                section=gettext("Confirm security action"),
                source_report=scan,
                cancel_url=request.get_full_path(),
                token=token,
                action=action,
                count=len(ids),
                accounts=chosen.order_by().values("user_id").distinct().count(),
            ),
        )
    has_open_findings = False
    has_reset_findings = False
    has_cleanup_findings = False
    for finding in page:
        evidence = finding.evidence
        if scan:
            for event in finding.events.all():
                if event.scan_id == scan.pk and event.action == "detected":
                    evidence = event.evidence
                    break
        matches = evidence.get("matches", [])
        finding.match_count = len(matches)
        finding.display_matches = display_matches(matches[:5])
        handler = FINDING_HANDLERS.get(finding.finding_type)
        finding.type_label = handler.label if handler else finding.finding_type
        if finding.status == SecurityFinding.Status.OPEN:
            has_open_findings = True
            if handler is not None:
                has_reset_findings |= handler.can_reset
                has_cleanup_findings |= handler.can_cleanup
    operation = None
    if request.GET.get("operation"):
        operation = get_object_or_404(
            SecurityScan, pk=parse_scan_id(request.GET["operation"])
        )
    report = operation or scan
    query = request.GET.copy()
    query.pop("page", None)
    summary_labels = {
        "checked": gettext("Passwords checked"),
        "matched": gettext("Matching rows"),
        "accounts": gettext("Affected accounts"),
        "duplicate": gettext("Duplicate rows"),
        "unknown": gettext("Unknown accounts"),
        "ambiguous": gettext("Ambiguous accounts"),
        "malformed": gettext("Malformed rows"),
        "unusable": gettext("Unusable passwords"),
        "mismatch": gettext("Passwords that did not match"),
        "password-reset": gettext("Passwords reset"),
        "email-cleanup": gettext("Lookalike e-mail identities removed"),
        "email-already-changed": gettext("E-mail identities already changed"),
        "password-changed": gettext("Passwords already changed"),
        "dismissed": gettext("Dismissed findings"),
        "skipped": gettext("Skipped findings"),
        "unsupported": gettext("Unsupported actions"),
    }
    summary = [
        (label, report.summary.get(key, 0))
        for key, label in summary_labels.items()
        if report and key in report.summary
    ]
    return render(
        request,
        "manage/security-findings.html",
        context(
            source_report=scan,
            page=page,
            summary=summary,
            report=report,
            report_error=gettext(report.error) if report else "",
            has_open_findings=has_open_findings,
            has_reset_findings=has_reset_findings,
            has_cleanup_findings=has_cleanup_findings,
            query=query.urlencode(),
            status=status,
            kind=kind,
            scan=scan,
            operation=operation,
            types=FINDING_HANDLERS,
            statuses=SecurityFinding.Status.choices,
        ),
    )


@management_permission_required("user.edit")
def security_confirm(request: AuthenticatedHttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)
    token = request.POST.get("token", "")
    # Limit lock names to UUIDs, never arbitrary request data.
    try:
        token = str(UUID(token))
    except ValueError:
        raise Http404 from None
    with WeblateLock(scope="security-confirm", key=token, slug=token):
        snapshot = cache.get(f"security-confirm:{token}")
        if snapshot is None or snapshot["actor"] != request.user.pk:
            raise Http404
        if not has_recent_sensitive_verification(request):
            return sensitive_verification_redirect(request, snapshot["return_url"])
        with transaction.atomic():
            scan = SecurityScan.objects.create(
                actor=request.user,
                operation=snapshot["action"],
                total=len(snapshot["ids"]),
                summary={"finding_ids": snapshot["ids"]},
            )
            security_scan_task.delay_on_commit(str(scan.pk))
        cache.delete(f"security-confirm:{token}")
    target = reverse("manage-security-progress", kwargs={"pk": scan.pk})
    if snapshot["scan"]:
        target += f"?{urlencode({'scan': snapshot['scan']})}"
    return redirect(target)


def display_matches(matches: list[dict]) -> list[dict]:
    labels = {
        "username": gettext("Username"),
        "email": gettext("Primary e-mail address"),
        "verified-email": gettext("Verified e-mail address"),
    }
    return [
        {**match, "method": labels.get(match["method"], match["method"])}
        for match in matches
    ]


@management_permission_required("user.edit")
def security_finding_detail(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    if not has_recent_sensitive_verification(request):
        return sensitive_verification_redirect(request, request.get_full_path())
    finding = get_object_or_404(SecurityFinding.objects.select_related("user"), pk=pk)
    evidence = finding.evidence
    source_report = None
    if request.GET.get("scan"):
        event = get_object_or_404(
            SecurityFindingEvent.objects.select_related("scan"),
            finding=finding,
            action="detected",
            scan_id=parse_scan_id(request.GET["scan"]),
            scan__operation__in=("validate", "legacy-email-check"),
        )
        evidence = event.evidence
        source_report = event.scan
    reports = (
        SecurityFindingEvent.objects.filter(
            finding=finding,
            action="detected",
            scan__operation__in=("validate", "legacy-email-check"),
        )
        .select_related("scan", "actor")
        .defer("scan__summary", "scan__error")
        .order_by("-timestamp", "pk")
    )
    reports_page = Paginator(reports, 50).get_page(request.GET.get("reports_page"))
    page = Paginator(evidence.get("matches", []), 100).get_page(request.GET.get("page"))
    page.object_list = display_matches(list(page.object_list))
    query = request.GET.copy()
    query.pop("page", None)
    reports_query = request.GET.copy()
    reports_query.pop("reports_page", None)
    return render(
        request,
        "manage/security-detail.html",
        context(
            section=gettext("Finding for %(username)s")
            % {"username": finding.user.username},
            source_report=source_report,
            finding=finding,
            page=page,
            reports_page=reports_page,
            reports_query=reports_query.urlencode(),
            query=query.urlencode(),
        ),
    )
