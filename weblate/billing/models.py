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

from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import python_2_unicode_compatible
from django.utils import timezone

from weblate.trans.models import Project, Component, Change, Unit
from weblate.lang.models import Language


@python_2_unicode_compatible
class Plan(models.Model):
    name = models.CharField(max_length=100, unique=True)
    price = models.IntegerField(default=0)
    yearly_price = models.IntegerField(default=0)
    limit_strings = models.IntegerField(default=0)
    display_limit_strings = models.IntegerField(default=0)
    limit_languages = models.IntegerField(default=0)
    display_limit_languages = models.IntegerField(default=0)
    limit_repositories = models.IntegerField(default=0)
    display_limit_repositories = models.IntegerField(default=0)
    limit_projects = models.IntegerField(default=0)
    display_limit_projects = models.IntegerField(default=0)
    change_access_control = models.BooleanField(default=True)

    class Meta(object):
        ordering = ['price']

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class Billing(models.Model):
    STATE_ACTIVE = 0
    STATE_TRIAL = 1
    STATE_EXPIRED = 2

    plan = models.ForeignKey(
        Plan,
        on_delete=models.deletion.CASCADE
    )
    projects = models.ManyToManyField(Project, blank=True)
    state = models.IntegerField(
        choices=(
            (STATE_ACTIVE, _('Active')),
            (STATE_TRIAL, _('Trial')),
            (STATE_EXPIRED, _('Expired')),
        ),
        default=STATE_ACTIVE,
    )

    def __str__(self):
        return '{0} ({1})'.format(
            ', '.join([str(x) for x in self.projects.all()]),
            self.plan
        )

    def count_changes(self, interval):
        return Change.objects.filter(
            component__project__in=self.projects.all(),
            timestamp__gt=timezone.now() - interval,
        ).count()

    def count_changes_1m(self):
        return self.count_changes(timedelta(days=31))
    count_changes_1m.short_description = _('Changes in last month')

    def count_changes_1q(self):
        return self.count_changes(timedelta(days=93))
    count_changes_1q.short_description = _('Changes in last quarter')

    def count_changes_1y(self):
        return self.count_changes(timedelta(days=365))
    count_changes_1y.short_description = _('Changes in last year')

    def count_repositories(self):
        return Component.objects.filter(
            project__in=self.projects.all(),
        ).exclude(
            repo__startswith='weblate:/'
        ).count()

    def display_repositories(self):
        return '{0} / {1}'.format(
            self.count_repositories(),
            self.plan.display_limit_repositories
        )
    display_repositories.short_description = _('VCS repositories')

    def count_projects(self):
        return self.projects.count()

    def display_projects(self):
        return '{0} / {1}'.format(
            self.count_projects(),
            self.plan.display_limit_projects
        )
    display_projects.short_description = _('Projects')

    def count_strings(self):
        return sum(
            (p.stats.source_strings for p in self.projects.all())
        )

    def display_strings(self):
        return '{0} / {1}'.format(
            self.count_strings(),
            self.plan.display_limit_strings
        )
    display_strings.short_description = _('Source strings')

    def count_words(self):
        return sum(
            (p.stats.source_words for p in self.projects.all())
        )

    def display_words(self):
        return '{0}'.format(
            self.count_words(),
        )
    display_words.short_description = _('Source words')

    def count_languages(self):
        return Language.objects.filter(
            translation__component__project__in=self.projects.all()
        ).distinct().count()

    def display_languages(self):
        return '{0} / {1}'.format(
            self.count_languages(),
            self.plan.display_limit_languages
        )
    display_languages.short_description = _('Languages')

    def in_limits(self):
        return (
            (
                self.plan.limit_repositories == 0 or
                self.count_repositories() <= self.plan.limit_repositories
            ) and
            (
                self.plan.limit_projects == 0 or
                self.count_projects() <= self.plan.limit_projects
            ) and
            (
                self.plan.limit_strings == 0 or
                self.count_strings() <= self.plan.limit_strings
            ) and
            (
                self.plan.limit_languages == 0 or
                self.count_languages() <= self.plan.limit_languages
            )
        )
    in_limits.boolean = True
    # Translators: Whether the package is inside actual (hard) limits
    in_limits.short_description = _('In limits')

    def unit_count(self):
        return Unit.objects.filter(
            translation__component__project__in=self.projects.all()
        ).count()
    unit_count.short_description = _('Number of strings')

    def last_invoice(self):
        try:
            invoice = self.invoice_set.order_by('-start')[0]
            return '{0} - {1}'.format(invoice.start, invoice.end)
        except IndexError:
            return _('N/A')
    last_invoice.short_description = _('Last invoice')

    def in_display_limits(self):
        return (
            (
                self.plan.display_limit_repositories == 0 or
                self.count_repositories() <=
                self.plan.display_limit_repositories
            ) and
            (
                self.plan.display_limit_projects == 0 or
                self.count_projects() <= self.plan.display_limit_projects
            ) and
            (
                self.plan.display_limit_strings == 0 or
                self.count_strings() <= self.plan.display_limit_strings
            ) and
            (
                self.plan.display_limit_languages == 0 or
                self.count_languages() <= self.plan.display_limit_languages
            )
        )
    in_display_limits.boolean = True
    # Translators: Whether the package is inside displayed (soft) limits
    in_display_limits.short_description = _('In display limits')


@python_2_unicode_compatible
class Invoice(models.Model):
    CURRENCY_EUR = 0
    CURRENCY_BTC = 1
    CURRENCY_USD = 2
    CURRENCY_CZK = 3

    billing = models.ForeignKey(
        Billing,
        on_delete=models.deletion.CASCADE
    )
    start = models.DateField()
    end = models.DateField()
    payment = models.FloatField()
    currency = models.IntegerField(
        choices=(
            (CURRENCY_EUR, 'EUR'),
            (CURRENCY_BTC, 'mBTC'),
            (CURRENCY_USD, 'USD'),
            (CURRENCY_CZK, 'CZK'),
        ),
        default=CURRENCY_EUR,
    )
    ref = models.CharField(blank=True, max_length=50)
    note = models.TextField(blank=True)

    class Meta(object):
        ordering = ['billing', '-start']

    def __str__(self):
        return '{0} - {1}: {2}'.format(
            self.start, self.end,
            self.billing if self.billing_id else None
        )

    @property
    def filename(self):
        if self.ref:
            return '{0}.pdf'.format(self.ref)
        return None

    def clean(self):
        if self.end is None or self.start is None:
            return

        if self.end <= self.start:
            raise ValidationError('Start has be to before end!')

        if not self.billing_id:
            return

        overlapping = Invoice.objects.filter(
            (Q(start__lte=self.end) & Q(end__gte=self.end)) |
            (Q(start__lte=self.start) & Q(end__gte=self.start))
        ).filter(
            billing=self.billing
        )

        if self.pk:
            overlapping = overlapping.exclude(
                pk=self.pk
            )

        if overlapping.exists():
            raise ValidationError(
                'Overlapping invoices exist: {0}'.format(
                    ', '.join([str(x) for x in overlapping])
                )
            )
