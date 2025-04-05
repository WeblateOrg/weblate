# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os.path
from contextlib import suppress
from datetime import timedelta
from functools import partial
from pathlib import Path

from appconf import AppConf
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models import Prefetch, Q
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy, ngettext

from weblate.auth.models import User
from weblate.trans.models import Alert, Component, Project, Translation
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.html import format_html_join_comma, list_to_tuples
from weblate.utils.stats import prefetch_stats


class LibreCheck:
    def __init__(self, result, message, component=None) -> None:
        self.result = result
        self.message = message
        self.component = component

    def __bool__(self) -> bool:
        return self.result

    def __str__(self) -> str:
        return self.message


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
    limit_hosted_strings = models.IntegerField(default=0)
    display_limit_hosted_strings = models.IntegerField(default=0)
    change_access_control = models.BooleanField(default=True)
    public = models.BooleanField(default=False)

    objects = PlanQuerySet.as_manager()

    class Meta:
        verbose_name = "Billing plan"
        verbose_name_plural = "Billing plans"

    def __str__(self) -> str:
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


class BillingManager(models.Manager["Billing"]):
    def check_limits(self) -> None:
        for bill in self.iterator():
            bill.check_limits()


class BillingQuerySet(models.QuerySet["Billing"]):
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

    def for_user(self, user: User):
        if user.has_perm("billing.manage"):
            return self.all().order_by("state")
        return (
            self.filter(
                Q(projects__in=user.projects_with_perm("billing.view")) | Q(owners=user)
            )
            .distinct()
            .order_by("state")
        )

    def prefetch(self):
        return self.prefetch_related(
            "owners",
            "owners__profile",
            "plan",
            Prefetch(
                "projects",
                queryset=Project.objects.order(),
                to_attr="ordered_projects",
            ),
        )

    def active(self):
        return self.filter(state__in=Billing.ACTIVE_STATES)


class Billing(models.Model):
    STATE_ACTIVE = 0
    STATE_TRIAL = 1
    STATE_TERMINATED = 3

    EXPIRING_STATES = {STATE_TRIAL}
    ACTIVE_STATES = {STATE_ACTIVE, STATE_TRIAL}

    plan = models.ForeignKey(
        Plan,
        on_delete=models.deletion.CASCADE,
        verbose_name=gettext_lazy("Billing plan"),
    )
    projects = models.ManyToManyField(
        Project, blank=True, verbose_name=gettext_lazy("Billed projects")
    )
    owners = models.ManyToManyField(
        User, blank=True, verbose_name=gettext_lazy("Billing owners")
    )
    state = models.IntegerField(
        choices=(
            (STATE_ACTIVE, gettext_lazy("Active")),
            (STATE_TRIAL, gettext_lazy("Trial")),
            (STATE_TERMINATED, gettext_lazy("Terminated")),
        ),
        default=STATE_ACTIVE,
        verbose_name=gettext_lazy("Billing state"),
    )
    expiry = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=gettext_lazy("Trial expiry date"),
        help_text="After expiry removal with 15 days grace period is scheduled.",
    )
    removal = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=gettext_lazy("Scheduled removal"),
        help_text="This is automatically set after trial expiry.",
    )
    paid = models.BooleanField(
        default=True, verbose_name=gettext_lazy("Paid"), editable=False
    )
    # Translators: Whether the package is inside actual (hard) limits
    in_limits = models.BooleanField(
        default=True, verbose_name=gettext_lazy("In limits"), editable=False
    )
    # Payment detailed information, used for integration
    # with payment processor
    payment = models.JSONField(editable=False, default=dict, encoder=DjangoJSONEncoder)

    objects = BillingManager.from_queryset(BillingQuerySet)()

    class Meta:
        verbose_name = "Customer billing"
        verbose_name_plural = "Customer billings"

    def __str__(self) -> str:
        projects = self.projects_display
        owners = self.owners.order()
        if projects:
            base = projects
        elif owners:
            base = format_html_join_comma(
                "{}", list_to_tuples(x.get_visible_name() for x in owners)
            )
        else:
            base = "Unassigned"
        trial = ", trial" if self.is_trial else ""
        return f"{base} ({self.plan}{trial})"

    def save(
        self,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
        skip_limits=False,
    ) -> None:
        if (
            not skip_limits
            and self.pk
            and self.check_limits(save=False)
            and update_fields
        ):
            update_fields = set(update_fields)
            update_fields.update(("state", "expiry", "removal", "paid", "in_limits"))

        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def get_absolute_url(self) -> str:
        return reverse("billing-detail", kwargs={"pk": self.pk})

    @cached_property
    def ordered_projects(self):
        return self.projects.order()

    @cached_property
    def all_projects(self):
        return prefetch_stats(self.ordered_projects)

    @cached_property
    def projects_display(self):
        return format_html_join_comma("{}", list_to_tuples(self.all_projects))

    @property
    def is_trial(self):
        return self.state == Billing.STATE_TRIAL

    @property
    def is_terminated(self):
        return self.state == Billing.STATE_TERMINATED

    @property
    def is_libre_trial(self) -> bool:
        return self.is_trial and self.plan.price == 0

    @cached_property
    def can_be_paid(self) -> bool:
        if self.state in Billing.ACTIVE_STATES:
            return True
        return self.count_projects > 0

    @admin.display(description=gettext_lazy("Changes in last month"))
    def monthly_changes(self) -> int:
        return sum(project.stats.monthly_changes for project in self.all_projects)

    @admin.display(description=gettext_lazy("Number of changes"))
    def total_changes(self) -> int:
        return sum(project.stats.total_changes for project in self.all_projects)

    @cached_property
    def count_projects(self) -> int:
        return len(self.all_projects)

    @admin.display(description=gettext_lazy("Projects"))
    def display_projects(self) -> str:
        return f"{self.count_projects} / {self.plan.display_limit_projects}"

    @cached_property
    def count_strings(self) -> int:
        return sum(p.stats.source_strings for p in self.all_projects)

    @admin.display(description=gettext_lazy("Source strings"))
    def display_strings(self) -> str:
        return f"{self.count_strings} / {self.plan.display_limit_strings}"

    @cached_property
    def count_hosted_strings(self) -> int:
        return sum(p.stats.all for p in self.all_projects)

    @admin.display(description=gettext_lazy("Hosted strings"))
    def display_hosted_strings(self) -> str:
        return f"{self.count_hosted_strings} / {self.plan.display_limit_hosted_strings}"

    @cached_property
    def count_words(self):
        return sum(p.stats.source_words for p in self.all_projects)

    @cached_property
    def hosted_words(self):
        return sum(p.stats.all_words for p in self.all_projects)

    @admin.display(description=gettext_lazy("Source words"))
    def display_words(self) -> str:
        return f"{self.count_words}"

    @cached_property
    def count_languages(self):
        return max((p.stats.languages for p in self.all_projects), default=0)

    @admin.display(description=gettext_lazy("Languages"))
    def display_languages(self) -> str:
        return f"{self.count_languages} / {self.plan.display_limit_languages}"

    def flush_cache(self) -> None:
        keys = list(self.__dict__.keys())
        for key in keys:
            if key.startswith("count_"):
                del self.__dict__[key]

    def check_in_limits(self, plan=None):
        if plan is None:
            plan = self.plan
        return (
            (plan.limit_projects == 0 or self.count_projects <= plan.limit_projects)
            and (
                plan.limit_hosted_strings == 0
                or self.count_hosted_strings <= plan.limit_hosted_strings
            )
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

    @admin.display(description=gettext_lazy("Number of strings"))
    def unit_count(self):
        return sum(p.stats.all for p in self.all_projects)

    def get_last_invoice_object(self):
        return self.invoice_set.order_by("-start")[0]

    @admin.display(description=gettext_lazy("Last invoice"))
    def last_invoice(self):
        try:
            invoice = self.get_last_invoice_object()
        except IndexError:
            return gettext("N/A")
        return f"{invoice.start} - {invoice.end}"

    @admin.display(
        description=gettext_lazy("In display limits"),
        boolean=True,
    )
    def in_display_limits(self, plan=None):
        if plan is None:
            plan = self.plan
        return (
            (
                plan.display_limit_projects == 0
                or self.count_projects <= plan.display_limit_projects
            )
            and (
                plan.display_limit_hosted_strings == 0
                or self.count_hosted_strings <= plan.display_limit_hosted_strings
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

    # Translators: Whether the package is inside displayed (soft) limits

    def check_payment_status(self, now: bool = False):
        """
        Check current payment status.

        Compared to paid attribute, this does not include grace period.
        """
        end = timezone.now()
        if not now:
            end -= timedelta(days=settings.BILLING_GRACE_PERIOD)
        return (
            (self.plan.is_free and self.state == Billing.STATE_ACTIVE)
            or self.invoice_set.filter(end__gte=end).exists()
            or self.state == Billing.STATE_TRIAL
        )

    def check_limits(self, save=True):
        self.flush_cache()
        in_limits = self.check_in_limits()
        paid = self.check_payment_status()
        modified = False

        if self.check_expiry():
            self.expiry = None
            self.removal = timezone.now() + timedelta(
                days=settings.BILLING_REMOVAL_PERIOD
            )
            modified = True

        if self.state not in Billing.EXPIRING_STATES and self.expiry:
            self.expiry = None
            modified = True

        if self.in_limits != in_limits or self.paid != paid:
            self.in_limits = in_limits
            self.paid = paid
            modified = True

        if save:
            if modified:
                self.save(skip_limits=True)
            self.update_alerts()

        return modified

    def update_alerts(self) -> None:
        if self.in_limits:
            Alert.objects.filter(
                component__project__in=self.projects.all(), name="BillingLimit"
            ).delete()
        else:
            for project in self.projects.iterator():
                for component in project.component_set.iterator():
                    component.add_alert("BillingLimit")

    def is_active(self):
        return self.state in Billing.ACTIVE_STATES

    def get_notify_users(self):
        users = self.owners.distinct()
        for project in self.projects.iterator():
            users |= User.objects.having_perm("billing.view", project)
        return users.exclude(is_superuser=True)

    def _get_libre_checklist(self):
        message = ngettext(
            "Contains %d project", "Contains %d projects", self.count_projects
        )
        # Ignore when format string is not present
        with suppress(TypeError):
            message %= self.count_projects
        yield LibreCheck(self.count_projects == 1, message)
        for project in self.all_projects:
            yield LibreCheck(
                bool(project.web),
                format_html(
                    '<a href="{0}">{1}</a>, <a href="{2}">{3}</a>',
                    project.get_absolute_url(),
                    project,
                    project.web
                    or reverse("settings", kwargs={"path": project.get_url_path()}),
                    project.web or gettext("Project website missing!"),
                ),
            )
            if project.access_control:
                yield LibreCheck(False, gettext("Only public projects are allowed"))
        components = Component.objects.filter(
            project__in=self.all_projects
        ).prefetch_related("project")
        yield LibreCheck(
            len(components) > 0,
            ngettext("Contains %d component", "Contains %d components", len(components))
            % len(components),
        )
        for component in components:
            license_name = component.get_license_display()
            if not component.libre_license:
                if not license_name:
                    license_name = format_html(
                        "<strong>{0}</strong>", gettext("Missing license")
                    )
                else:
                    license_name = format_html(
                        "{0} (<strong>{1}</strong>)",
                        license_name,
                        gettext("Not a libre license"),
                    )
            if component.license_url:
                license_name = format_html(
                    '<a href="{0}">{1}</a>', component.license_url, license_name
                )
            repo_url = component.repo
            if repo_url.startswith("https://"):
                repo_url = format_html('<a href="{0}">{0}</a>', repo_url)
            yield LibreCheck(
                component.libre_license,
                format_html(
                    """
                    <a href="{0}">{1}</a>,
                    {2},
                    {3},
                    {4}""",
                    component.get_absolute_url(),
                    component.name,
                    license_name,
                    repo_url,
                    component.get_file_format_display(),
                ),
                component=component,
            )

    @cached_property
    def libre_checklist(self):
        return list(self._get_libre_checklist())

    @property
    def valid_libre(self):
        return all(self.libre_checklist)


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
    payment = models.JSONField(editable=False, default=dict)
    created = models.DateTimeField(auto_now_add=True)

    objects = InvoiceQuerySet.as_manager()

    class Meta:
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"

    def __str__(self) -> str:
        return f"{self.start} - {self.end}: {self.billing if self.billing_id else None}"

    @cached_property
    def is_legacy(self):
        return len(self.ref) <= 6

    @cached_property
    def filename(self) -> str | None:
        if not self.ref:
            return None
        if self.is_legacy:
            return f"{self.ref}.pdf"
        return f"Weblate_Invoice_{self.ref}.pdf"

    @cached_property
    def full_filename(self) -> str | None:
        if not self.ref:
            return None
        if self.is_legacy:
            invoice_path = Path(settings.INVOICE_PATH_LEGACY)
        else:
            invoice_path = (
                Path(settings.INVOICE_PATH)
                / f"{self.created.year}"
                / f"{self.created.month:02d}"
            )
        full_path = invoice_path / (self.filename or "")
        return full_path.as_posix()

    @cached_property
    def filename_valid(self) -> bool:
        return self.full_filename and os.path.exists(self.full_filename)

    def clean(self) -> None:
        if self.end is None or self.start is None:
            return

        if self.end <= self.start:
            msg = "Start has be to before end!"
            raise ValidationError(msg)

        if not self.billing_id:
            return

        overlapping = Invoice.objects.filter(
            (Q(start__lte=self.end) & Q(end__gte=self.end))
            | (Q(start__lte=self.start) & Q(end__gte=self.start))
        ).filter(billing=self.billing)

        if self.pk:
            overlapping = overlapping.exclude(pk=self.pk)

        if overlapping.exists():
            msg = "Overlapping invoices exist: {}".format(
                format_html_join_comma("{}", list_to_tuples(overlapping))
            )
            raise ValidationError(msg)


@receiver(post_save, sender=Component)
@receiver(post_save, sender=Project)
@receiver(post_save, sender=Plan)
@disable_for_loaddata
def update_project_bill(sender, instance, **kwargs) -> None:
    if isinstance(instance, Component):
        instance = instance.project
    for billing in instance.billing_set.all():
        billing.check_limits()


@receiver(pre_delete, sender=Project)
@receiver(pre_delete, sender=Component)
@receiver(post_delete, sender=Translation)
@disable_for_loaddata
def record_project_bill(
    sender, instance: Project | Component | Translation, **kwargs
) -> None:
    if isinstance(instance, Translation):
        try:
            instance = instance.component
        except Component.DoesNotExist:
            # Happens during component removal
            return
    if isinstance(instance, Component):
        instance = instance.project
    # Collect billings to update for delete_project_bill
    instance.billings_to_update = list(
        instance.billing_set.values_list("pk", flat=True)
    )


@receiver(post_delete, sender=Project)
@receiver(post_delete, sender=Component)
@receiver(post_delete, sender=Translation)
@disable_for_loaddata
def delete_project_bill(
    sender, instance: Project | Component | Translation, **kwargs
) -> None:
    from weblate.billing.tasks import billing_check

    if isinstance(instance, Translation):
        try:
            instance = instance.component
        except Component.DoesNotExist:
            # Happens during component removal
            return
    if isinstance(instance, Component):
        instance = instance.project
    # This is collected in record_project_bill
    for billing_id in instance.billings_to_update:
        transaction.on_commit(partial(billing_check, billing_id))
    # Clear the list to avoid repeated trigger
    instance.billings_to_update.clear()


@receiver(post_save, sender=Invoice)
@disable_for_loaddata
def update_invoice_bill(sender, instance, **kwargs) -> None:
    instance.billing.check_limits()


@receiver(m2m_changed, sender=Billing.projects.through)
@disable_for_loaddata
def change_billing_projects(sender, instance, action, **kwargs) -> None:
    if not action.startswith("post_"):
        return
    instance.check_limits()


class WeblateConf(AppConf):
    GRACE_PERIOD = 15
    REMOVAL_PERIOD = 15

    class Meta:
        prefix = "BILLING"
