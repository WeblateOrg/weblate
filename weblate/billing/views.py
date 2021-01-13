#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from weblate.accounts.views import mail_admins_contact
from weblate.billing.forms import HostingForm
from weblate.billing.models import Billing, Invoice, Plan
from weblate.utils.views import show_form_errors

HOSTING_TEMPLATE = """
%(name)s <%(email)s> wants to host %(project)s

Project:    %(project)s
Website:    %(url)s

Message:

%(message)s

Please review at https://hosted.weblate.org%(billing_url)s
"""


@login_required
def download_invoice(request, pk):
    """Download invoice PDF."""
    invoice = get_object_or_404(Invoice, pk=pk)

    if not invoice.ref:
        raise Http404("No reference!")

    if not request.user.has_perm("billing.view", invoice.billing):
        raise PermissionDenied()

    if not invoice.filename_valid:
        raise Http404(f"File {invoice.filename} does not exist!")

    with open(invoice.full_filename, "rb") as handle:
        data = handle.read()

    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename={invoice.filename}"
    response["Content-Length"] = len(data)

    return response


def handle_post(request, billing):
    if "extend" in request.POST and request.user.is_superuser:
        billing.state = Billing.STATE_TRIAL
        billing.expiry = timezone.now() + timedelta(days=14)
        billing.removal = None
        billing.save(update_fields=["expiry", "removal", "state"])
    elif "recurring" in request.POST:
        if "recurring" in billing.payment:
            del billing.payment["recurring"]
        billing.save()
    elif "terminate" in request.POST:
        billing.state = Billing.STATE_TERMINATED
        billing.save()
    elif billing.valid_libre:
        if "approve" in request.POST and request.user.is_superuser:
            billing.state = Billing.STATE_ACTIVE
            billing.plan = Plan.objects.get(slug="libre")
            billing.removal = None
            billing.save(update_fields=["state", "plan", "removal"])
        elif "request" in request.POST:
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
                    request.user.get_author_name(),
                    settings.ADMINS_HOSTING,
                )
            else:
                show_form_errors(request, form)


@login_required
def overview(request):
    billings = Billing.objects.for_user(request.user).prefetch_related(
        "plan", "projects", "invoice_set"
    )
    if not request.user.is_superuser and len(billings) == 1:
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
def detail(request, pk):
    billing = get_object_or_404(Billing, pk=pk)

    if not request.user.has_perm("billing.view", billing):
        raise PermissionDenied()

    if request.method == "POST":
        handle_post(request, billing)
        return redirect(billing)

    return render(
        request,
        "billing/detail.html",
        {"billing": billing, "hosting_form": HostingForm()},
    )
