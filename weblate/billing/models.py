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

from __future__ import unicode_literals

from datetime import timedelta
import os.path

from django.conf import settings
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from django.utils import timezone

from weblate.auth.models import User
from weblate.trans.models import Project, Component, Change, Unit
from weblate.lang.models import Language
from weblate.utils.fields import JSONField


class PlanQuerySet(models.QuerySet):
    def public(self, user=None):
        """List of public paid plans which are available."""
        base = self.exclude(Q(price=0) & Q(yearly_price=0))
        result = base.filter(
            public=True
        )
        if user:
            result |= base.filter(
                public=False,
                billing__in=Billing.objects.for_user(user)
            )
        return result.distinct().order_by('price')


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
    public = models.BooleanField(default=False)

    objects = PlanQuerySet.as_manager()

    class Meta(object):
        ordering = ['price']

    def __str__(self):
        return self.name

    @property
    def vat_price(self):
        return round(self.price * settings.VAT_RATE, 2)

    @property
    def vat_yearly_price(self):
        return round(self.yearly_price * settings.VAT_RATE, 2)

    @property
    def is_free(self):
        return self.price == 0 and self.yearly_price == 0


class BillingManager(models.Manager):
    def check_limits(self, grace=30):
        for bill in self.all():
            bill.check_limits(grace)


class BillingQuerySet(models.QuerySet):
    def get_out_of_limits(self):
        return self.filter(in_limits=False)

    def get_unpaid(self):
        return self.filter(paid=False, state=Billing.STATE_ACTIVE)

    def get_valid(self):
        return self.filter(
            Q(in_limits=True) &
            (
                (Q(state=Billing.STATE_ACTIVE) & Q(paid=True)) |
                Q(state=Billing.STATE_TRIAL)
            )
        )

    def for_user(self, user):
        if user.is_superuser:
            return self.all().order_by('state')
        return self.filter(
            Q(projects__in=user.projects_with_perm('billing.view')) |
            Q(owners=user)
        ).distinct().order_by('state')


@python_2_unicode_compatible
class Billing(models.Model):
    STATE_ACTIVE = 0
    STATE_TRIAL = 1
    STATE_EXPIRED = 2
    STATE_TERMINATED = 3

    EXPIRING_STATES = (STATE_TRIAL,)

    plan = models.ForeignKey(
        Plan,
        on_delete=models.deletion.CASCADE,
        verbose_name=_('Billing plan'),
    )
    projects = models.ManyToManyField(
        Project, blank=True,
        verbose_name=_('Billed projects'),
    )
    owners = models.ManyToManyField(
        User, blank=True,
        verbose_name=_('Billing owners'),
    )
    state = models.IntegerField(
        choices=(
            (STATE_ACTIVE, _('Active')),
            (STATE_TRIAL, _('Trial')),
            (STATE_EXPIRED, _('Expired')),
            (STATE_TERMINATED, _('Terminated')),
        ),
        default=STATE_ACTIVE,
        verbose_name=_('Billing state'),
    )
    expiry = models.DateTimeField(
        blank=True, null=True, default=None,
        verbose_name=_('Trial expiry date'),
    )
    paid = models.BooleanField(
        default=False,
        verbose_name=_('Paid'),
        editable=False,
    )
    # Translators: Whether the package is inside actual (hard) limits
    in_limits = models.BooleanField(
        default=True,
        verbose_name=_('In limits'),
        editable=False,
    )
    grace_period = models.IntegerField(
        default=0,
        verbose_name=_('Grace period for payments'),
    )
    # Payment detailed information, used for integration
    # with payment processor
    payment = JSONField(editable=False, default={})

    objects = BillingManager.from_queryset(BillingQuerySet)()

    def __str__(self):
        projects = self.projects.all()
        owners = self.owners.all()
        if projects:
            base = ', '.join([str(x) for x in projects])
        elif owners:
            base = ', '.join([x.get_author_name(False) for x in owners])
        else:
            base = 'Unassigned'
        return '{0} ({1})'.format(base, self.plan)

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

    def check_in_limits(self, plan=None):
        if plan is None:
            plan = self.plan
        return (
            (
                plan.limit_repositories == 0 or
                self.count_repositories() <= plan.limit_repositories
            ) and
            (
                plan.limit_projects == 0 or
                self.count_projects() <= plan.limit_projects
            ) and
            (
                plan.limit_strings == 0 or
                self.count_strings() <= plan.limit_strings
            ) and
            (
                plan.limit_languages == 0 or
                self.count_languages() <= plan.limit_languages
            )
        )

    def check_expiry(self):
        return (
            self.state in Billing.EXPIRING_STATES and
            self.expiry and
            self.expiry < timezone.now()
        )

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

    def in_display_limits(self, plan=None):
        if plan is None:
            plan = self.plan
        return (
            (
                plan.display_limit_repositories == 0 or
                self.count_repositories() <=
                plan.display_limit_repositories
            ) and
            (
                plan.display_limit_projects == 0 or
                self.count_projects() <= plan.display_limit_projects
            ) and
            (
                plan.display_limit_strings == 0 or
                self.count_strings() <= plan.display_limit_strings
            ) and
            (
                plan.display_limit_languages == 0 or
                self.count_languages() <= plan.display_limit_languages
            )
        )
    in_display_limits.boolean = True
    # Translators: Whether the package is inside displayed (soft) limits
    in_display_limits.short_description = _('In display limits')

    def check_payment_status(self):
        """Check current payment status.

        Compared to paid attribute, this does not include grace period.
        """
        end = timezone.now() - timedelta(days=self.grace_period)
        return (
            self.plan.is_free or
            self.invoice_set.filter(end__gte=end).exists() or
            self.state == Billing.STATE_TRIAL
        )

    def check_limits(self, grace=30, save=True):
        due_date = timezone.now() - timedelta(days=grace)
        in_limits = self.check_in_limits()
        paid = (
            self.plan.is_free or
            self.invoice_set.filter(end__gt=due_date).exists() or
            self.state == Billing.STATE_TRIAL
        )
        modified = False

        if self.check_expiry():
            self.state = Billing.STATE_EXPIRED
            self.expiry = None
            modified = True

        if self.state not in Billing.EXPIRING_STATES and self.expiry:
            self.expiry = None
            modified = True

        if self.in_limits != in_limits or self.paid != paid:
            self.in_limits = in_limits
            self.paid = paid
            modified = True

        if save and modified:
            self.save(skip_limits=True)

    def save(self, *args, **kwargs):
        if not kwargs.pop('skip_limits', False) and self.pk:
            self.check_limits(save=False)
        super(Billing, self).save(*args, **kwargs)

    def is_active(self):
        return self.state in (Billing.STATE_ACTIVE, Billing.STATE_TRIAL)


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
    amount = models.FloatField()
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
    # Payment detailed information, used for integration
    # with payment processor
    payment = JSONField(editable=False, default={})

    class Meta(object):
        ordering = ['billing', '-start']

    def __str__(self):
        return '{0} - {1}: {2}'.format(
            self.start, self.end,
            self.billing if self.billing_id else None
        )

    @cached_property
    def filename(self):
        if self.ref:
            return '{0}.pdf'.format(self.ref)
        return None

    @cached_property
    def full_filename(self):
        return os.path.join(settings.INVOICE_PATH, self.filename)

    @cached_property
    def filename_valid(self):
        return os.path.exists(self.full_filename)

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


@receiver(post_save, sender=Component)
@receiver(post_save, sender=Project)
@receiver(post_save, sender=Plan)
def update_project_bill(sender, instance, **kwargs):
    if isinstance(instance, Component):
        instance = instance.project
    for billing in instance.billing_set.iterator():
        billing.check_limits()


@receiver(post_save, sender=Invoice)
def update_invoice_bill(sender, instance, **kwargs):
    instance.billing.check_limits()


@receiver(m2m_changed, sender=Billing.projects.through)
def change_componentlist(sender, instance, **kwargs):
    instance.check_limits()
