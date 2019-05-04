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

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from weblate.billing.models import Billing, Invoice


@login_required
def download_invoice(request, pk):
    """Download invoice PDF"""
    invoice = get_object_or_404(Invoice, pk=pk)

    if not invoice.ref:
        raise Http404('No reference!')

    allowed_billing = Billing.objects.for_user(
        request.user
    ).filter(
        pk=invoice.billing.pk
    )

    if not allowed_billing.exists():
        raise PermissionDenied('Not an owner!')

    if not invoice.filename_valid:
        raise Http404('File {0} does not exist!'.format(invoice.filename))

    with open(invoice.full_filename, 'rb') as handle:
        data = handle.read()

    response = HttpResponse(
        data,
        content_type='application/pdf'
    )
    response['Content-Disposition'] = 'attachment; filename={0}'.format(
        invoice.filename
    )
    response['Content-Length'] = len(data)

    return response


def handle_post(request, billings):
    def get(name):
        try:
            return int(request.POST[name])
        except (KeyError, ValueError):
            return None

    recurring = get('recurring')
    terminate = get('terminate')
    if not recurring and not terminate:
        return
    try:
        billing = billings.get(pk=recurring or terminate)
    except Billing.DoesNotExist:
        return
    if recurring:
        if 'recurring' in billing.payment:
            del billing.payment['recurring']
        billing.save()
    elif terminate:
        billing.state = Billing.STATE_TERMINATED
        billing.save()


@login_required
def overview(request):
    billings = Billing.objects.for_user(
        request.user
    ).prefetch_related(
        'plan', 'projects', 'invoice_set'
    )
    if request.method == 'POST':
        handle_post(request, billings)
        return redirect('billing')
    return render(request, 'billing/overview.html', {'billings': billings})
