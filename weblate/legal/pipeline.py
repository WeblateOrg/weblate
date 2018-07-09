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

from django.urls import reverse
from django.shortcuts import redirect
from django.utils.http import urlencode

from social_core.pipeline.partial import partial

from weblate.legal.models import Agreement


@partial
def tos_confirm(strategy, backend, user, current_partial, **kwargs):
    """Force authentication when adding new association."""
    agreement = Agreement.objects.get_or_create(user=user)[0]
    if not agreement.is_current():
        if user:
            strategy.request.session['tos_user'] = user.pk
        url = '{0}?partial_token={1}'.format(
            reverse('social:complete', args=(backend.name,)),
            current_partial.token,
        )
        return redirect(
            '{0}?{1}'.format(
                reverse('legal:confirm'),
                urlencode({'next': url})
            )
        )
    strategy.request.session.pop('tos_user', None)
    return None
