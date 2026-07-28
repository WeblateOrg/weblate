# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext

from weblate.accounts.views import mail_admins_contact
from weblate.auth.models import TeamMembership
from weblate.trans.backups import PROJECTBACKUP_PREFIX
from weblate.utils import messages
from weblate.utils.data import data_path
from weblate.utils.views import show_form_errors

from .defines import REMOVAL_EXTENSION_DAYS, TRIAL_DAYS
from .forms import (
    BillingMergeConfirmForm,
    BillingMergeForm,
    BillingPlanChangeForm,
    HostingForm,
)
from .models import Billing, BillingEvent, Invoice, Plan

if TYPE_CHECKING:
    from django.http import HttpResponse

    from weblate.auth.models import AuthenticatedHttpRequest

HOSTING_TEMPLATE = """
%(name)s <%(email)s> wants to host %(project)s

Project:    %(project)s
Website:    %(url)s

Message:

%(message)s

Please review at https://hosted.weblate.org%(billing_url)s
"""


def merge_workspace_access(billing: Billing, other: Billing) -> None:
    target_groups = other.workspace.setup_groups()
    billing.workspace.setup_groups()
    for source_group in billing.workspace.defined_groups.prefetch_related("roles"):
        target_group = target_groups.get(source_group.name)
        if target_group is None:
            target_group, _created = other.workspace.defined_groups.get_or_create(
                name=source_group.name,
                defaults={
                    "internal": source_group.internal,
                    "project_selection": source_group.project_selection,
                    "language_selection": source_group.language_selection,
                    "enforced_2fa": source_group.enforced_2fa,
                },
            )
            target_groups[source_group.name] = target_group
        if not target_group.roles.exists():
            target_group.roles.set(source_group.roles.all())
        existing_user_ids = set(
            target_group.memberships.values_list("user_id", flat=True)
        )
        for membership in (
            source_group.memberships.select_related("user")
            .prefetch_related("limit_languages")
            .exclude(user_id__in=existing_user_ids)
        ):
            target_membership = TeamMembership.objects.create(
                user=membership.user, group=target_group
            )
            target_membership.limit_languages.set(membership.limit_languages.all())


@login_required
def download_invoice(request: AuthenticatedHttpRequest, pk) -> HttpResponse:
    """Download invoice PDF."""
    invoice = get_object_or_404(Invoice, pk=pk)

    filename = invoice.full_filename

    if not filename:
        msg = "No reference!"
        raise Http404(msg)

    if not request.user.has_perm("meta:billing.view", invoice.billing):
        raise PermissionDenied

    if not invoice.filename_valid:
        msg = f"File {invoice.filename} does not exist!"
        raise Http404(msg)

    return FileResponse(
        open(filename, "rb"),
        as_attachment=True,
        filename=invoice.filename,
        content_type="application/pdf",
    )


BACKUP_RE = re.compile(r"^[0-9]+/[0-9]+.zip$")


@login_required
def restore_backup(request: AuthenticatedHttpRequest) -> HttpResponse:
    if not request.user.is_superuser:
        raise PermissionDenied
    path = request.GET.get("path")
    if not path or not BACKUP_RE.match(path):
        msg = "Invalid backup path!"
        raise Http404(msg)
    backup_path = data_path(PROJECTBACKUP_PREFIX) / path
    if not backup_path.exists():
        msg = "File not found!"
        raise Http404(msg)
    return FileResponse(
        backup_path.open("rb"),
        as_attachment=True,
        filename=backup_path.name,
        content_type="application/zip",
    )


def handle_termination(request: AuthenticatedHttpRequest, billing: Billing) -> None:
    if not billing.can_terminate:
        messages.error(
            request,
            gettext("To terminate billing you have to remove all projects first."),
        )
        return
    billing.state = Billing.STATE_TERMINATED
    billing.expiry = None
    billing.removal = None
    billing.save()
    billing.billinglog_set.create(event=BillingEvent.TERMINATED, user=request.user)


def handle_post(request: AuthenticatedHttpRequest, billing) -> None:
    if "extend" in request.POST and request.user.has_perm("billing.manage"):
        now = timezone.now()
        if billing.is_trial:
            billing.state = Billing.STATE_TRIAL
            if billing.expiry and billing.expiry > now:
                billing.expiry += timedelta(days=TRIAL_DAYS)
            else:
                billing.expiry = now + timedelta(days=TRIAL_DAYS)
            billing.removal = None
            billing.save(update_fields=["expiry", "removal", "state"])
        elif billing.removal:
            billing.removal = now + timedelta(days=REMOVAL_EXTENSION_DAYS)
            billing.save(update_fields=["removal"])
        billing.billinglog_set.create(
            event=BillingEvent.EXTENDED_TRIAL, user=request.user
        )
    elif "change_plan" in request.POST:
        if not request.user.has_perm("billing.manage"):
            raise PermissionDenied
        old_plan = billing.plan
        form = BillingPlanChangeForm(request.POST)
        if not form.is_valid():
            show_form_errors(request, form)
            return
        new_plan = form.cleaned_data["plan"]
        billing.plan = new_plan
        update_fields = ["plan"]
        if form.cleaned_data["trial"]:
            billing.state = Billing.STATE_TRIAL
            billing.expiry = timezone.now() + timedelta(days=TRIAL_DAYS)
            billing.removal = None
            update_fields.extend(("state", "expiry", "removal"))
        billing.save(update_fields=update_fields)
        billing.billinglog_set.create(
            event=BillingEvent.PLAN_CHANGED,
            summary=f"Changed to {new_plan}",
            details={
                "old_plan": {"id": old_plan.pk, "name": old_plan.name},
                "new_plan": {"id": new_plan.pk, "name": new_plan.name},
            },
            user=request.user,
        )
    elif "recurring" in request.POST:
        if "recurring" in billing.payment:
            del billing.payment["recurring"]
        billing.clear_inactive_recurring_status(save=False, log=False)
        billing.save(
            update_fields=[
                "payment",
                *Billing.INACTIVE_RECURRING_FIELDS,
            ]
        )
        billing.billinglog_set.create(
            event=BillingEvent.DISABLED_RECURRING, user=request.user
        )
    elif "terminate" in request.POST:
        handle_termination(request, billing)
    elif billing.valid_libre:
        if "approve" in request.POST and request.user.has_perm("billing.manage"):
            billing.state = Billing.STATE_ACTIVE
            billing.plan = Plan.objects.get(slug="libre")
            billing.removal = None
            billing.save(update_fields=["state", "plan", "removal"])
            billing.billinglog_set.create(
                event=BillingEvent.LIBRE_APPROVED, user=request.user
            )
        elif "request" in request.POST and billing.is_libre_trial:
            form = HostingForm(request.POST)
            if form.is_valid():
                project = billing.get_projects_queryset().get()
                subject = f"Hosting request for {project}"
                billing.payment["libre_request"] = True
                billing.save(update_fields=["payment"])
                billing.billinglog_set.create(
                    event=BillingEvent.LIBRE_REQUEST, summary=subject, user=request.user
                )
                mail_admins_contact(
                    request,
                    subject=subject,
                    message=HOSTING_TEMPLATE,
                    context={
                        "billing": billing,
                        "name": request.user.full_name,
                        "email": request.user.email,
                        "project": project,
                        "url": project.web,
                        "message": form.cleaned_data["message"],
                        "billing_url": billing.get_absolute_url(),
                    },
                    name=request.user.get_visible_name(),
                    email=request.user.email,
                    to=settings.ADMINS_HOSTING,
                )
            else:
                show_form_errors(request, form)


@login_required
def overview(request: AuthenticatedHttpRequest) -> HttpResponse:
    billings = (
        Billing.objects.for_user(request.user)
        .prefetch()
        .prefetch_related("invoice_set")
    )
    if not request.user.has_perm("billing.manage") and len(billings) == 1:
        return redirect(billings[0])
    return render(
        request,
        "billing/overview.html",
        {
            "billings": billings,
            "active_billing_count": billings.filter(
                state__in=(Billing.STATE_ACTIVE, Billing.STATE_TRIAL)
            ).count(),
        },
    )


@login_required
def merge(request: AuthenticatedHttpRequest, pk) -> HttpResponse:
    if not request.user.has_perm("billing.manage"):
        raise PermissionDenied

    billing = get_object_or_404(Billing, pk=pk)

    if request.method == "GET":
        merge_form = BillingMergeForm(request.GET)
        if (
            not merge_form.is_valid()
            or merge_form.cleaned_data["other"].pk == billing.pk
        ):
            messages.error(request, gettext("Cannot merge such a billing."))
            return redirect(billing)

        confirm_form = BillingMergeConfirmForm(initial=merge_form.cleaned_data)
        return render(
            request,
            "billing/merge.html",
            {
                "billing": billing,
                "other": merge_form.cleaned_data["other"],
                "merge_form": confirm_form,
            },
        )

    confirm_form = BillingMergeConfirmForm(request.POST)
    if (
        not confirm_form.is_valid()
        or confirm_form.cleaned_data["other"].pk == billing.pk
    ):
        messages.error(request, gettext("Cannot merge such a billing."))
        return redirect(billing)

    other = confirm_form.cleaned_data["other"]
    with transaction.atomic():
        if "recurring" in billing.payment:
            other.payment["recurring"] = billing.payment["recurring"]
        if "all" in billing.payment:
            other.payment.setdefault("all", []).extend(billing.payment["all"])
        other.save()
        moved_projects = billing.get_projects_queryset()
        projects_moved = moved_projects.update(workspace=other.workspace)
        if projects_moved:
            # ruff: ignore[import-outside-top-level]
            from weblate.utils.tasks import update_workspace_stats

            update_workspace_stats.delay_on_commit(
                [str(billing.workspace_id), str(other.workspace_id)]
            )
        other.update_workspace_name()
        merge_workspace_access(billing, other)
        billing.invoice_set.update(billing=other)
        billing.billinglog_set.update(billing=other)
        billing.payment = {}
        billing.save()
        billing.check_limits()
        other.check_limits()

    return redirect(confirm_form.cleaned_data["other"])


@login_required
def detail(request: AuthenticatedHttpRequest, pk) -> HttpResponse:
    billing = get_object_or_404(Billing, pk=pk)

    if not request.user.has_perm("meta:billing.view", billing):
        raise PermissionDenied

    if request.method == "POST":
        handle_post(request, billing)
        return redirect(billing)

    return render(
        request,
        "billing/detail.html",
        {
            "billing": billing,
            "hosting_form": HostingForm(),
            "merge_form": BillingMergeForm(),
            "plan_change_form": BillingPlanChangeForm(initial={"plan": billing.plan}),
        },
    )
