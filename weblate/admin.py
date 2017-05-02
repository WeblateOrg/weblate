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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.conf import settings
from django.contrib.admin import AdminSite
from django.contrib.auth.models import User, Group
from django.utils.translation import ugettext_lazy as _

from weblate.accounts.admin import (
    WeblateUserAdmin, WeblateGroupAdmin, ProfileAdmin, VerifiedEmailAdmin,
)
from weblate.accounts.forms import LoginForm
from weblate.accounts.models import Profile, VerifiedEmail
from weblate.billing.admin import PlanAdmin, BillingAdmin, InvoiceAdmin
from weblate.billing.models import Plan, Billing, Invoice
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
    AutoComponentListAdmin,
)
from weblate.trans.models import (
    Project, SubProject, Translation, Advertisement,
    Unit, Suggestion, Comment, Check, Dictionary, Change,
    Source, WhiteboardMessage, ComponentList, AutoComponentList,
)


class WeblateAdminSite(AdminSite):
    login_form = LoginForm
    site_header = _('Weblate administration')
    site_title = _('Weblate administration')
    index_template = 'admin/custom-index.html'

    def discover(self):
        """Manual discovery."""
        # Accounts
        self.register(User, WeblateUserAdmin)
        self.register(Group, WeblateGroupAdmin)
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
            self.register(Plan, PlanAdmin)
            self.register(Billing, BillingAdmin)
            self.register(Invoice, InvoiceAdmin)


SITE = WeblateAdminSite()
SITE.discover()
