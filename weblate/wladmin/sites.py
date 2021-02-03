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

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.views import LogoutView
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from rest_framework.authtoken.admin import TokenAdmin
from rest_framework.authtoken.models import Token
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
    site_header = _("Weblate administration")
    site_title = _("Weblate administration")
    index_template = "admin/weblate-index.html"
    enable_nav_sidebar = False

    @property
    def site_url(self):
        if settings.URL_PREFIX:
            return settings.URL_PREFIX
        return "/"

    def discover(self):
        """Manual discovery."""
        # Accounts
        self.register(User, WeblateUserAdmin)
        self.register(Role, RoleAdmin)
        self.register(Group, WeblateGroupAdmin)
        self.register(AuditLog, AuditLogAdmin)
        self.register(Profile, ProfileAdmin)
        self.register(VerifiedEmail, VerifiedEmailAdmin)

        # Languages
        self.register(Language, LanguageAdmin)

        # Memory
        self.register(Memory, MemoryAdmin)

        # Screenshots
        self.register(Screenshot, ScreenshotAdmin)

        # Fonts
        self.register(Font, FontAdmin)
        self.register(FontGroup, FontGroupAdmin)

        # Translations
        self.register(Project, ProjectAdmin)
        self.register(Component, ComponentAdmin)
        self.register(Announcement, AnnouncementAdmin)
        self.register(ComponentList, ComponentListAdmin)
        self.register(ContributorAgreement, ContributorAgreementAdmin)

        # Settings
        self.register(Setting, SettingAdmin)

        # Show some controls only in debug mode
        if settings.DEBUG:
            self.register(Translation, TranslationAdmin)
            self.register(Unit, UnitAdmin)
            self.register(Suggestion, SuggestionAdmin)
            self.register(Comment, CommentAdmin)
            self.register(Check, CheckAdmin)
            self.register(Change, ChangeAdmin)

        # Billing
        if "weblate.billing" in settings.INSTALLED_APPS:
            # pylint: disable=wrong-import-position
            from weblate.billing.admin import BillingAdmin, InvoiceAdmin, PlanAdmin
            from weblate.billing.models import Billing, Invoice, Plan

            self.register(Plan, PlanAdmin)
            self.register(Billing, BillingAdmin)
            self.register(Invoice, InvoiceAdmin)

        # Hosted
        if "wlhosted.integrations" in settings.INSTALLED_APPS:
            # pylint: disable=wrong-import-position
            from wlhosted.payments.admin import CustomerAdmin, PaymentAdmin
            from wlhosted.payments.models import Customer, Payment

            self.register(Customer, CustomerAdmin)
            self.register(Payment, PaymentAdmin)

        # Legal
        if "weblate.legal" in settings.INSTALLED_APPS:
            # pylint: disable=wrong-import-position
            from weblate.legal.admin import AgreementAdmin
            from weblate.legal.models import Agreement

            self.register(Agreement, AgreementAdmin)

        # SAML identity provider
        if "djangosaml2idp" in settings.INSTALLED_APPS:
            # pylint: disable=wrong-import-position
            from djangosaml2idp.admin import PersistentIdAdmin, ServiceProviderAdmin
            from djangosaml2idp.models import PersistentId, ServiceProvider

            self.register(PersistentId, PersistentIdAdmin)
            self.register(ServiceProvider, ServiceProviderAdmin)

        # Python Social Auth
        self.register(UserSocialAuth, UserSocialAuthOption)
        self.register(Nonce, NonceOption)
        self.register(Association, AssociationOption)

        # Django REST Framework
        self.register(Token, TokenAdmin)

        # Simple SSO
        if "simple_sso.sso_server" in settings.INSTALLED_APPS:
            from simple_sso.sso_server.models import Consumer
            from simple_sso.sso_server.server import ConsumerAdmin

            self.register(Consumer, ConsumerAdmin)

    @never_cache
    def logout(self, request, extra_context=None):
        if request.method == "POST":
            messages.info(request, _("Thank you for using Weblate."))
            request.current_app = self.name
            return LogoutView.as_view(next_page=reverse("admin:login"))(request)
        context = self.each_context(request)
        context["title"] = _("Sign out")
        return render(request, "admin/logout-confirm.html", context)

    def each_context(self, request):
        result = super().each_context(request)
        empty = [_("Object listing turned off")]
        result["empty_selectable_objects_list"] = [empty]
        result["empty_objects_list"] = empty
        result["configuration_errors"] = ConfigurationError.objects.filter(
            ignored=False
        )
        return result

    @property
    def urls(self):
        return self.get_urls()


SITE = WeblateAdminSite()
SITE.discover()
admin.site = SITE
