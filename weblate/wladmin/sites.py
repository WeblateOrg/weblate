# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import AdminSite, sites
from django.contrib.auth.views import LogoutView
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext, gettext_lazy
from django.views.decorators.cache import never_cache
from django_celery_beat.admin import (
    ClockedSchedule,
    ClockedScheduleAdmin,
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    PeriodicTaskAdmin,
    SolarSchedule,
)
from social_django.admin import AssociationOption, NonceOption, UserSocialAuthOption
from social_django.models import Association, Nonce, UserSocialAuth

from weblate.accounts.admin import AuditLogAdmin, ProfileAdmin, VerifiedEmailAdmin
from weblate.accounts.forms import AdminLoginForm
from weblate.accounts.models import AuditLog, Profile, VerifiedEmail
from weblate.auth.admin import RoleAdmin, WeblateGroupAdmin, WeblateUserAdmin
from weblate.auth.models import Group, Role, User
from weblate.checks.admin import CheckAdmin
from weblate.checks.models import Check
from weblate.configuration.admin import SettingAdmin
from weblate.configuration.models import Setting
from weblate.fonts.admin import FontAdmin, FontGroupAdmin
from weblate.fonts.models import Font, FontGroup
from weblate.lang.admin import LanguageAdmin
from weblate.lang.models import Language
from weblate.memory.admin import MemoryAdmin
from weblate.memory.models import Memory
from weblate.screenshots.admin import ScreenshotAdmin
from weblate.screenshots.models import Screenshot
from weblate.trans.admin import (
    AnnouncementAdmin,
    ChangeAdmin,
    CommentAdmin,
    ComponentAdmin,
    ComponentListAdmin,
    ContributorAgreementAdmin,
    ProjectAdmin,
    SuggestionAdmin,
    TranslationAdmin,
    UnitAdmin,
)
from weblate.trans.models import (
    Announcement,
    Change,
    Comment,
    Component,
    ComponentList,
    ContributorAgreement,
    Project,
    Suggestion,
    Translation,
    Unit,
)
from weblate.utils import messages
from weblate.wladmin.models import ConfigurationError


class WeblateAdminSite(AdminSite):
    login_form = AdminLoginForm
    site_header = gettext_lazy("Weblate administration")
    site_title = gettext_lazy("Weblate administration")
    index_template = "admin/weblate-index.html"
    enable_nav_sidebar = False

    @property
    def site_url(self):
        if settings.URL_PREFIX:
            return settings.URL_PREFIX
        return "/"

    def register(self, model_or_iterable, admin_class=None, **options):
        # Default register interface ignores all models, we handle them manually
        return

    def _register(self, model_or_iterable, admin_class=None, **options):
        super().register(model_or_iterable, admin_class=admin_class, **options)

    def discover(self):
        """Manual discovery."""
        # TODO: Use auto-discovery instead as we're monkey patching site anywany
        # Accounts
        self._register(User, WeblateUserAdmin)
        self._register(Role, RoleAdmin)
        self._register(Group, WeblateGroupAdmin)
        self._register(AuditLog, AuditLogAdmin)
        self._register(Profile, ProfileAdmin)
        self._register(VerifiedEmail, VerifiedEmailAdmin)

        # Languages
        self._register(Language, LanguageAdmin)

        # Memory
        self._register(Memory, MemoryAdmin)

        # Screenshots
        self._register(Screenshot, ScreenshotAdmin)

        # Fonts
        self._register(Font, FontAdmin)
        self._register(FontGroup, FontGroupAdmin)

        # Translations
        self._register(Project, ProjectAdmin)
        self._register(Component, ComponentAdmin)
        self._register(Announcement, AnnouncementAdmin)
        self._register(ComponentList, ComponentListAdmin)
        self._register(ContributorAgreement, ContributorAgreementAdmin)

        # Settings
        self._register(Setting, SettingAdmin)

        # Show some controls only in debug mode
        if settings.DEBUG:
            self._register(Translation, TranslationAdmin)
            self._register(Unit, UnitAdmin)
            self._register(Suggestion, SuggestionAdmin)
            self._register(Comment, CommentAdmin)
            self._register(Check, CheckAdmin)
            self._register(Change, ChangeAdmin)

        # Billing
        if "weblate.billing" in settings.INSTALLED_APPS:
            from weblate.billing.admin import BillingAdmin, InvoiceAdmin, PlanAdmin
            from weblate.billing.models import Billing, Invoice, Plan

            self._register(Plan, PlanAdmin)
            self._register(Billing, BillingAdmin)
            self._register(Invoice, InvoiceAdmin)

        # Hosted
        if "wlhosted.integrations" in settings.INSTALLED_APPS:
            from wlhosted.payments.admin import CustomerAdmin, PaymentAdmin
            from wlhosted.payments.models import Customer, Payment

            self._register(Customer, CustomerAdmin)
            self._register(Payment, PaymentAdmin)

        # Legal
        if "weblate.legal" in settings.INSTALLED_APPS:
            from weblate.legal.admin import AgreementAdmin
            from weblate.legal.models import Agreement

            self._register(Agreement, AgreementAdmin)

        # SAML identity provider
        if "djangosaml2idp" in settings.INSTALLED_APPS:
            from djangosaml2idp.admin import PersistentIdAdmin, ServiceProviderAdmin
            from djangosaml2idp.models import PersistentId, ServiceProvider

            self._register(PersistentId, PersistentIdAdmin)
            self._register(ServiceProvider, ServiceProviderAdmin)

        # Python Social Auth
        self._register(UserSocialAuth, UserSocialAuthOption)
        self._register(Nonce, NonceOption)
        self._register(Association, AssociationOption)

        # Django REST Framework
        from rest_framework.authtoken.admin import TokenAdmin
        from rest_framework.authtoken.models import Token

        self._register(Token, TokenAdmin)

        # Django Celery Beat
        self._register(IntervalSchedule)
        self._register(CrontabSchedule)
        self._register(SolarSchedule)
        self._register(ClockedSchedule, ClockedScheduleAdmin)
        self._register(PeriodicTask, PeriodicTaskAdmin)

        # Simple SSO
        if "simple_sso.sso_server" in settings.INSTALLED_APPS:
            from simple_sso.sso_server.models import Consumer
            from simple_sso.sso_server.server import ConsumerAdmin

            self._register(Consumer, ConsumerAdmin)

    @method_decorator(never_cache)
    def logout(self, request, extra_context=None):
        if request.method == "POST":
            messages.info(request, gettext("Thank you for using Weblate."))
            request.current_app = self.name
            return LogoutView.as_view(next_page=reverse("admin:login"))(request)
        context = self.each_context(request)
        context["title"] = gettext("Sign out")
        return render(request, "admin/logout-confirm.html", context)

    def each_context(self, request):
        result = super().each_context(request)
        empty = [gettext("Object listing turned off")]
        result["empty_selectable_objects_list"] = [empty]
        result["empty_objects_list"] = empty
        result["configuration_errors"] = ConfigurationError.objects.filter(
            ignored=False
        )
        return result

    @property
    def urls(self):
        return self.get_urls(), "admin", self.name


SITE = sites.site = admin.site = WeblateAdminSite()
SITE.discover()
