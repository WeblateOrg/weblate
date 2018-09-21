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

from django.db.models import Sum, Count
from django.views.generic import TemplateView
from django.utils.translation import ugettext_lazy as _

from weblate.accounts.models import Profile
from weblate.checks.models import Check
from weblate.lang.models import Language
from weblate.trans.models import Project, Unit
from weblate.utils.requirements import get_versions, get_optional_versions
from weblate.utils.stats import prefetch_stats, GlobalStats
from weblate.vcs.gpg import get_gpg_public_key, get_gpg_sign_key
from weblate.vcs.ssh import get_key_data


MENU = (
    (
        'index',
        'about',
        _('About'),
    ),
    (
        'stats',
        'stats',
        _('Statistics'),
    ),
    (
        'keys',
        'keys',
        _('Keys'),
    ),
)


class AboutView(TemplateView):
    page = 'index'

    def page_context(self, context):
        context.update({
            'title': _('About Weblate'),
            'versions': get_versions() + get_optional_versions(),
            'allow_index': True,
        })

    def get_context_data(self, **kwargs):
        context = super(AboutView, self).get_context_data(**kwargs)

        context['about_menu'] = MENU
        context['about_page'] = self.page

        self.page_context(context)

        return context

    def get_template_names(self):
        return ['about/{0}.html'.format(self.page)]


class StatsView(AboutView):
    page = 'stats'

    def page_context(self, context):
        context['title'] = _('Weblate statistics')

        stats = GlobalStats()

        totals = Profile.objects.aggregate(
            Sum('translated'), Sum('suggested'), Count('id')
        )

        context['total_translations'] = totals['translated__sum']
        context['total_suggestions'] = totals['suggested__sum']
        context['total_users'] = totals['id__count']
        context['total_strings'] = stats.source_strings
        context['total_units'] = stats.all
        context['total_words'] = stats.source_words
        context['total_languages'] = stats.languages
        context['total_checks'] = Check.objects.count()
        context['ignored_checks'] = Check.objects.filter(ignore=True).count()

        top_translations = Profile.objects.order_by('-translated')[:10]
        top_suggestions = Profile.objects.order_by('-suggested')[:10]
        top_uploads = Profile.objects.order_by('-uploaded')[:10]

        context['top_translations'] = top_translations.select_related('user')
        context['top_suggestions'] = top_suggestions.select_related('user')
        context['top_uploads'] = top_uploads.select_related('user')


class KeysView(AboutView):
    page = 'keys'

    def page_context(self, context):
        context.update({
            'title': _('Weblate keys'),
            'gpg_key_id': get_gpg_sign_key(),
            'gpg_key': get_gpg_public_key(),
            'ssh_key': get_key_data(),
            'allow_index': True,
        })
