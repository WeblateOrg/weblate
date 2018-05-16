# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
from __future__ import unicode_literals

from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView
from django.utils.translation import ugettext_lazy as _

from weblate.auth.models import User
from weblate.legal.forms import TOSForm
from weblate.legal.models import Agreement
from weblate.trans.util import redirect_next


MENU = (
    (
        'index',
        'legal:index',
        _('Overview'),
    ),
    (
        'terms',
        'legal:terms',
        _('Terms of Service'),
    ),
    (
        'cookies',
        'legal:cookies',
        _('Cookies'),
    ),
    (
        'security',
        'legal:security',
        _('Security'),
    ),
    (
        'privacy',
        'legal:privacy',
        _('Privacy'),
    ),
)


class LegalView(TemplateView):
    page = 'index'

    def get_context_data(self, **kwargs):
        context = super(LegalView, self).get_context_data(**kwargs)

        context['legal_menu'] = MENU
        context['legal_page'] = self.page

        return context

    def get_template_names(self):
        return ['legal/{0}.html'.format(self.page)]


class TermsView(LegalView):
    page = 'terms'


class CookiesView(LegalView):
    page = 'cookies'


class SecurityView(LegalView):
    page = 'security'


class PrivacyView(LegalView):
    page = 'privacy'


@never_cache
def tos_confirm(request):
    user = None
    if request.user.is_authenticated:
        user = request.user
    elif 'tos_user' in request.session:
        user = User.objects.get(pk=request.session['tos_user'])

    if user is None:
        return redirect('home')

    agreement = Agreement.objects.get_or_create(user=user)[0]
    if agreement.is_current():
        return redirect_next(request.GET.get('next'), 'home')

    if request.method == 'POST':
        form = TOSForm(request.POST)
        if form.is_valid():
            agreement.make_current(request)
            return redirect_next(form.cleaned_data['next'], 'home')
    else:
        form = TOSForm(initial={'next': request.GET.get('next')})

    return render(
        request,
        'legal/confirm.html',
        {
            'form': form,
        }
    )
