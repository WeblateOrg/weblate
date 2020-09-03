#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import os.path
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from weblate.auth.models import User
from weblate.trans.models import Component, Project
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.fields import JSONField
from weblate.utils.stats import prefetch_stats


class PlanQuerySet(models.QuerySet):
    def public(self, user=None):
        """List of public paid plans which are available."""
        base = self.exclude(Q(price=0) & Q(yearly_price=0))
        result = base.filter(public=True)
        if user:
            result |= base.filter(
                public=False, billing__in=Billing.objects.for_user(user)
            )
        return result.distinct().order_by("price")


class Plan(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    price = models.IntegerField(default=0)
    yearly_price = models.IntegerField(default=0)
    limit_strings = models.IntegerField(default=0)
    display_limit_strings = models.IntegerField(default=0)
    limit_languages = models.IntegerField(default=0)
    display_limit_languages = models.IntegerField(default=0)
    limit_projects = models.IntegerField(default=0)
    display_limit_projects = models.IntegerField(default=0)
    change_access_control = models.BooleanField(default=True)
    public = models.BooleanField(default=False)

    objects = PlanQuerySet.as_manager()

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
        for bill in self.iterator():
            bill.check_limits(grace)


class BillingQuerySet(models.QuerySet):
    def get_out_of_limits(self):
        return self.filter(in_limits=False)

    def get_unpaid(self):
        return self.filter(paid=False, state=Billing.STATE_ACTIVE)

    def get_valid(self):
        return self.filter(
            Q(in_limits=True)
            & (
                (Q(state=Billing.STATE_ACTIVE) & Q(paid=True))
                | Q(state=Billing.STATE_TRIAL)
            )
        )

    def for_user(self, user):
        if user.is_superuser:
            return self.all().order_by("state")
        return (
            self.filter(
                Q(projects__in=user.projects_with_perm("billing.view")) | Q(owners=user)
            )
            .distinct()
            .order_by("state")
        )


class Billing(models.Model):
    STATE_ACTIVE = 0
    STATE_TRIAL = 1
    STATE_EXPIRED = 2
    STATE_TERMINATED = 3

    EXPIRING_STATES = (STATE_TRIAL,)

    plan = models.ForeignKey(
        Plan, on_delete=models.deletion.CASCADE, verbose_name=_("Billing plan")
    )
    projects = models.ManyToManyField(
        Project, blank=True, verbose_name=_("Billed projects")
    )
    owners = models.ManyToManyField(User, blank=True, verbose_name=_("Billing owners"))
    state = models.IntegerField(
        choices=(
            (STATE_ACTIVE, _("Active")),
            (STATE_TRIAL, _("Trial")),
            (STATE_EXPIRED, _("Expired")),
            (STATE_TERMINATED, _("Terminated")),
        ),
        default=STATE_ACTIVE,
        verbose_name=_("Billing state"),
    )
    expiry = models.DateTimeField(
        blank=True,
        null=True,
        default=None,
        verbose_name=_("Trial expiry date"),
        help_text="After expiry removal with 15 days grace period is scheduled.",
    )
    removal = models.DateTimeField(
        blank=True,
        null=True,
        default=None,
        verbose_name=_("Scheduled removal"),
        help_text="This is automatically set after trial expiry.",
    )
    paid = models.BooleanField(default=True, verbose_name=_("Paid"), editable=False)
    # Translators: Whether the package is inside actual (hard) limits
    in_limits = models.BooleanField(
        default=True, verbose_name=_("In limits"), editable=False
    )
    grace_period = models.IntegerField(
        default=0, verbose_name=_("Grace period for payments")
    )
    # Payment detailed information, used for integration
    # with payment processor
    payment = JSONField(editable=False, default={})

    objects = BillingManager.from_queryset(BillingQuerySet)()

    def __str__(self):
        projects = self.projects.order()
        owners = self.owners.order()
        if projects:
            base = ", ".join(str(x) for x in projects)
        elif owners:
            base = ", ".join(x.get_author_name(False) for x in owners)
        else:
            base = "Unassigned"
        return "{0} ({1})".format(base, self.plan)

    def save(
        self,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
        skip_limits=False,
    ):
        if not skip_limits and self.pk:
            self.check_limits(save=False)
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def get_absolute_url(self):
        return "{}#billing-{}".format(reverse("billing"), self.pk)

    @cached_property
    def all_projects(self):
        return prefetch_stats(self.projects.all())

    @property
    def is_trial(self):
        return self.state == Billing.STATE_TRIAL

    @cached_property
    def can_be_paid(self):
        if self.state in (Billing.STATE_ACTIVE, Billing.STATE_TRIAL):
            return True
        return self.count_projects > 0

    @cached_property
    def monthly_changes(self):
        return sum(project.stats.monthly_changes for project in self.all_projects)

    monthly_changes.short_description = _("Changes in last month")

    @cached_property
    def total_changes(self):
        return sum(project.stats.total_changes for project in self.all_projects)

    total_changes.short_description = _("Number of changes")

    @cached_property
    def count_projects(self):
        return len(self.all_projects)

    def display_projects(self):
        return "{0} / {1}".format(self.count_projects, self.plan.display_limit_projects)

    display_projects.short_description = _("Projects")

    @cached_property
    def count_strings(self):
        return sum(p.stats.source_strings for p in self.all_projects)

    def display_strings(self):
        return "{0} / {1}".format(self.count_strings, self.plan.display_limit_strings)

    display_strings.short_description = _("Source strings")

    @cached_property
    def count_words(self):
        return sum(p.stats.source_words for p in self.all_projects)

    def display_words(self):
        return "{0}".format(self.count_words)

    display_words.short_description = _("Source words")

    @cached_property
    def count_languages(self):
        if not self.all_projects:
            return 0
        return max(p.stats.languages for p in self.all_projects)

    def display_languages(self):
        return "{0} / {1}".format(
            self.count_languages, self.plan.display_limit_languages
        )

    display_languages.short_description = _("Languages")

    def flush_cache(self):
        keys = list(self.__dict__.keys())
        for key in keys:
            if key.startswith("count_"):
                del self.__dict__[key]

    def check_in_limits(self, plan=None):
        if plan is None:
            plan = self.plan
        return (
            (plan.limit_projects == 0 or self.count_projects <= plan.limit_projects)
            and (plan.limit_strings == 0 or self.count_strings <= plan.limit_strings)
            and (
                plan.limit_languages == 0
                or self.count_languages <= plan.limit_languages
            )
        )

    def check_expiry(self):
        return (
            self.state in Billing.EXPIRING_STATES
            and self.expiry
            and self.expiry < timezone.now()
        )

    def unit_count(self):
        return sum(p.stats.all for p in self.all_projects)

    unit_count.short_description = _("Number of strings")

    def last_invoice(self):
        try:
            invoice = self.invoice_set.order_by("-start")[0]
            return "{0} - {1}".format(invoice.start, invoice.end)
        except IndexError:
            return _("N/A")

    last_invoice.short_description = _("Last invoice")

    def in_display_limits(self, plan=None):
        if plan is None:
            plan = self.plan
        return (
            (
                plan.display_limit_projects == 0
                or self.count_projects <= plan.display_limit_projects
            )
            and (
                plan.display_limit_strings == 0
                or self.count_strings <= plan.display_limit_strings
            )
            and (
                plan.display_limit_languages == 0
                or self.count_languages <= plan.display_limit_languages
            )
        )

    in_display_limits.boolean = True
    # Translators: Whether the package is inside displayed (soft) limits
    in_display_limits.short_description = _("In display limits")

    def check_payment_status(self, grace=None):
        """Check current payment status.

        Compared to paid attribute, this does not include grace period.
        """
        end = timezone.now() - timedelta(days=grace or self.grace_period)
        return (
            self.plan.is_free
            or self.invoice_set.filter(end__gte=end).exists()
            or self.state == Billing.STATE_TRIAL
        )

    def check_limits(self, grace=30, save=True):
        self.flush_cache()
        in_limits = self.check_in_limits()
        paid = self.check_payment_status(grace)
        modified = False

        if self.check_expiry():
            self.state = Billing.STATE_EXPIRED
            self.expiry = None
            self.removal = timezone.now() + timedelta(days=30)
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

    def is_active(self):
        return self.state in (Billing.STATE_ACTIVE, Billing.STATE_TRIAL)

    def get_notify_users(self):
        users = self.owners.distinct()
        for project in self.projects.iterator():
            users |= User.objects.having_perm("billing.view", project)
        return users


class InvoiceQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("-start")


class Invoice(models.Model):
    CURRENCY_EUR = 0
    CURRENCY_BTC = 1
    CURRENCY_USD = 2
    CURRENCY_CZK = 3

    billing = models.ForeignKey(Billing, on_delete=models.deletion.CASCADE)
    start = models.DateField()
    end = models.DateField()
    amount = models.FloatField()
    currency = models.IntegerField(
        choices=(
            (CURRENCY_EUR, "EUR"),
            (CURRENCY_BTC, "mBTC"),
            (CURRENCY_USD, "USD"),
            (CURRENCY_CZK, "CZK"),
        ),
        default=CURRENCY_EUR,
    )
    ref = models.CharField(blank=True, max_length=50)
    note = models.TextField(blank=True)
    # Payment detailed information, used for integration
    # with payment processor
    payment = JSONField(editable=False, default={})

    objects = InvoiceQuerySet.as_manager()

    def __str__(self):
        return "{0} - {1}: {2}".format(
            self.start, self.end, self.billing if self.billing_id else None
        )

    @cached_property
    def filename(self):
        if self.ref:
            return "{0}.pdf".format(self.ref)
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
            raise ValidationError("Start has be to before end!")

        if not self.billing_id:
            return

        overlapping = Invoice.objects.filter(
            (Q(start__lte=self.end) & Q(end__gte=self.end))
            | (Q(start__lte=self.start) & Q(end__gte=self.start))
        ).filter(billing=self.billing)

        if self.pk:
            overlapping = overlapping.exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError(
                "Overlapping invoices exist: {0}".format(
                    ", ".join(str(x) for x in overlapping)
                )
            )


@receiver(post_save, sender=Component)
@receiver(post_save, sender=Project)
@receiver(post_save, sender=Plan)
@disable_for_loaddata
def update_project_bill(sender, instance, **kwargs):
    if isinstance(instance, Component):
        instance = instance.project
    for billing in instance.billing_set.iterator():
        billing.check_limits()


@receiver(post_save, sender=Invoice)
@disable_for_loaddata
def update_invoice_bill(sender, instance, **kwargs):
    instance.billing.check_limits()


@receiver(m2m_changed, sender=Billing.projects.through)
@disable_for_loaddata
def change_billing_projects(sender, instance, action, **kwargs):
    if not action.startswith("post_"):
        return
    instance.check_limits()
