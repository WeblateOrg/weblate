# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from functools import update_wrapper

from django.conf import settings
from django.conf.urls import url
from django.contrib.admin import AdminSite
from django.contrib.auth.models import User, Group
from django.contrib.auth.views import logout
from django.contrib.sites.admin import SiteAdmin
from django.contrib.sites.models import Site
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.cache import never_cache


from rest_framework.authtoken.admin import TokenAdmin
from rest_framework.authtoken.models import Token

from social_django.admin import (
    UserSocialAuthOption, NonceOption, AssociationOption,
)
from social_django.models import UserSocialAuth, Nonce, Association

from weblate.accounts.admin import (
    WeblateUserAdmin, WeblateGroupAdmin, ProfileAdmin, VerifiedEmailAdmin,
    AuditLogAdmin,
)
from weblate.accounts.forms import LoginForm
from weblate.accounts.models import Profile, VerifiedEmail, AuditLog
from weblate.lang.admin import LanguageAdmin
from weblate.lang.models import Language
from weblate.permissions.admin import AutoGroupAdmin, GroupACLAdmin
from weblate.permissions.models import AutoGroup, GroupACL
from weblate.screenshots.admin import ScreenshotAdmin
from weblate.screenshots.models import Screenshot
from weblate.trans.admin import (
    ProjectAdmin, SubProjectAdmin, TranslationAdmin, AdvertisementAdmin,
    UnitAdmin, SuggestionAdmin, CommentAdmin, CheckAdmin, DictionaryAdmin,
    ChangeAdmin, SourceAdmin, WhiteboardMessageAdmin, ComponentListAdmin,
)
from weblate.trans.models import (
    Project, SubProject, Translation, Advertisement,
    Unit, Suggestion, Comment, Check, Dictionary, Change,
    Source, WhiteboardMessage, ComponentList,
)
from weblate.utils import messages
import weblate.wladmin.views


class WeblateAdminSite(AdminSite):
    login_form = LoginForm
    site_header = _('Weblate administration')
    site_title = _('Weblate administration')

    def discover(self):
        """Manual discovery."""
        # Accounts
        self.register(User, WeblateUserAdmin)
        self.register(Group, WeblateGroupAdmin)
        self.register(AuditLog, AuditLogAdmin)
        self.register(Profile, ProfileAdmin)
        self.register(VerifiedEmail, VerifiedEmailAdmin)

        # Languages
        self.register(Language, LanguageAdmin)

        # Permissions
        self.register(GroupACL, GroupACLAdmin)
        self.register(AutoGroup, AutoGroupAdmin)

        # Screenshots
        self.register(Screenshot, ScreenshotAdmin)

        # Transaltions
        self.register(Project, ProjectAdmin)
        self.register(SubProject, SubProjectAdmin)
        self.register(Advertisement, AdvertisementAdmin)
        self.register(WhiteboardMessage, WhiteboardMessageAdmin)
        self.register(ComponentList, ComponentListAdmin)

        # Show some controls only in debug mode
        if settings.DEBUG and False:
            self.register(Translation, TranslationAdmin)
            self.register(Unit, UnitAdmin)
            self.register(Suggestion, SuggestionAdmin)
            self.register(Comment, CommentAdmin)
            self.register(Check, CheckAdmin)
            self.register(Dictionary, DictionaryAdmin)
            self.register(Change, ChangeAdmin)
            self.register(Source, SourceAdmin)

        # Billing
        if 'weblate.billing' in settings.INSTALLED_APPS:
            # pylint: disable=C0413
            from weblate.billing.admin import (
                PlanAdmin, BillingAdmin, InvoiceAdmin,
            )
            from weblate.billing.models import Plan, Billing, Invoice
            self.register(Plan, PlanAdmin)
            self.register(Billing, BillingAdmin)
            self.register(Invoice, InvoiceAdmin)

        # Legal
        if 'weblate.legal' in settings.INSTALLED_APPS:
            # pylint: disable=C0413
            from weblate.legal.admin import AgreementAdmin
            from weblate.legal.models import Agreement
            self.register(Agreement, AgreementAdmin)

        # Python Social Auth
        self.register(UserSocialAuth, UserSocialAuthOption)
        self.register(Nonce, NonceOption)
        self.register(Association, AssociationOption)

        # Django REST Framework
        self.register(Token, TokenAdmin)

        # Django core
        self.register(Site, SiteAdmin)

    @never_cache
    def logout(self, request, extra_context=None):
        if request.method == 'POST':
            messages.info(request, _('Thanks for using Weblate!'))
            return logout(request, next_page=reverse('admin:login'))
        context = self.each_context(request)
        context['title'] = _('Logout')
        return render(request, 'admin/logout-confirm.html', context)

    def each_context(self, request):
        result = super(WeblateAdminSite, self).each_context(request)
        empty = [_('Object listing disabled')]
        result['empty_selectable_objects_list'] = [empty]
        result['empty_objects_list'] = empty
        return result

    def get_urls(self):
        def wrap(view, cacheable=False):
            def wrapper(*args, **kwargs):
                return self.admin_view(view, cacheable)(
                    *args, admin_site=self, **kwargs
                )
            return update_wrapper(wrapper, view)

        urls = super(WeblateAdminSite, self).get_urls()
        urls += [
            url(
                r'^report/$',
                wrap(weblate.wladmin.views.report),
                name='report'
            ),
            url(
                r'^ssh/$',
                wrap(weblate.wladmin.views.ssh),
                name='ssh'
            ),
            url(
                r'^performance/$',
                wrap(weblate.wladmin.views.performance),
                name='performance'
            ),
        ]
        return urls


SITE = WeblateAdminSite()
SITE.discover()
