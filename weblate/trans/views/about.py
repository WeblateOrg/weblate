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

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from weblate.accounts.models import Profile
from weblate.metrics.models import Metric
from weblate.utils.requirements import get_versions_list
from weblate.utils.stats import GlobalStats
from weblate.vcs.gpg import get_gpg_public_key, get_gpg_sign_key
from weblate.vcs.ssh import get_key_data

MENU = (
    ("index", "about", _("About Weblate")),
    ("stats", "stats", _("Statistics")),
    ("keys", "keys", _("Keys")),
)


class AboutView(TemplateView):
    page = "index"

    def page_context(self, context):
        context.update(
            {
                "title": _("About Weblate"),
                "versions": get_versions_list(),
                "allow_index": True,
            }
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["menu_items"] = MENU
        context["menu_page"] = self.page

        self.page_context(context)

        return context

    def get_template_names(self):
        return [f"about/{self.page}.html"]


class StatsView(AboutView):
    page = "stats"

    def page_context(self, context):
        context["title"] = _("Weblate statistics")

        stats = GlobalStats()

        totals = Profile.objects.aggregate(Sum("translated"))
        metrics = Metric.objects.get_current(None, Metric.SCOPE_GLOBAL, 0)

        context["total_translations"] = totals["translated__sum"]
        context["stats"] = stats
        context["metrics"] = metrics

        context["top_users"] = top_users = (
            Profile.objects.order_by("-translated")
            .filter(user__is_active=True)[:10]
            .select_related("user")
        )
        translated_max = max(user.translated for user in top_users)
        for user in top_users:
            if translated_max:
                user.translated_width = 100 * user.translated // translated_max
            else:
                user.translated_width = 0


class KeysView(AboutView):
    page = "keys"

    def page_context(self, context):
        context.update(
            {
                "title": _("Weblate keys"),
                "gpg_key_id": get_gpg_sign_key(),
                "gpg_key": get_gpg_public_key(),
                "ssh_key": get_key_data(),
                "allow_index": True,
            }
        )
