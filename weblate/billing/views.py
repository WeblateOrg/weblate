# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from weblate.accounts.views import mail_admins_contact
from weblate.billing.forms import HostingForm
from weblate.billing.models import Billing, Invoice, Plan
from weblate.utils.views import show_form_errors

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest

HOSTING_TEMPLATE = """
%(name)s <%(email)s> wants to host %(project)s

Project:    %(project)s
Website:    %(url)s

Message:

%(message)s

Please review at https://hosted.weblate.org%(billing_url)s
"""


@login_required
def download_invoice(request: AuthenticatedHttpRequest, pk):
    """Download invoice PDF."""
    invoice = get_object_or_404(Invoice, pk=pk)

    if not invoice.ref:
        raise Http404("No reference!")

    if not request.user.has_perm("billing.view", invoice.billing):
        raise PermissionDenied

    if not invoice.filename_valid:
        raise Http404(f"File {invoice.filename} does not exist!")

    return FileResponse(
        open(invoice.full_filename, "rb"),  # noqa: SIM115
        as_attachment=True,
        filename=invoice.filename,
        content_type="application/pdf",
    )


def handle_post(request: AuthenticatedHttpRequest, billing) -> None:
    if "extend" in request.POST and request.user.has_perm("billing.manage"):
        if billing.is_trial:
            billing.state = Billing.STATE_TRIAL
            billing.expiry = timezone.now() + timedelta(days=14)
            billing.removal = None
            billing.save(update_fields=["expiry", "removal", "state"])
        elif billing.removal:
            billing.removal = timezone.now() + timedelta(days=14)
            billing.save(update_fields=["removal"])
    elif "recurring" in request.POST:
        if "recurring" in billing.payment:
            del billing.payment["recurring"]
        billing.save()
    elif "terminate" in request.POST:
        billing.state = Billing.STATE_TERMINATED
        billing.save()
    elif billing.valid_libre:
        if "approve" in request.POST and request.user.has_perm("billing.manage"):
            billing.state = Billing.STATE_ACTIVE
            billing.plan = Plan.objects.get(slug="libre")
            billing.removal = None
            billing.save(update_fields=["state", "plan", "removal"])
        elif "request" in request.POST and billing.is_libre_trial:
            form = HostingForm(request.POST)
            if form.is_valid():
                project = billing.projects.get()
                billing.payment["libre_request"] = True
                billing.save(update_fields=["payment"])
                mail_admins_contact(
                    request,
                    "Hosting request for %(billing)s",
                    HOSTING_TEMPLATE,
                    {
                        "billing": billing,
                        "name": request.user.full_name,
                        "email": request.user.email,
                        "project": project,
                        "url": project.web,
                        "message": form.cleaned_data["message"],
                        "billing_url": billing.get_absolute_url(),
                    },
                    request.user.get_author_name(request.user.email),
                    settings.ADMINS_HOSTING,
                )
            else:
                show_form_errors(request, form)


@login_required
def overview(request: AuthenticatedHttpRequest):
    billings = Billing.objects.for_user(request.user).prefetch_related(
        "plan", "projects", "invoice_set"
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
def detail(request: AuthenticatedHttpRequest, pk):
    billing = get_object_or_404(Billing, pk=pk)

    if not request.user.has_perm("billing.view", billing):
        raise PermissionDenied

    if request.method == "POST":
        handle_post(request, billing)
        return redirect(billing)

    return render(
        request,
        "billing/detail.html",
        {"billing": billing, "hosting_form": HostingForm()},
    )
