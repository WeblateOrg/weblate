# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import requests
from django.core.cache import cache
from django.db.models import Sum
from django.utils.translation import gettext, gettext_lazy
from django.views.generic import TemplateView

from weblate.accounts.models import Profile
from weblate.metrics.models import Metric
from weblate.utils.requests import request
from weblate.utils.requirements import get_versions_list
from weblate.utils.stats import GlobalStats
from weblate.vcs.gpg import get_gpg_public_key, get_gpg_sign_key
from weblate.vcs.ssh import get_all_key_data

MENU = (
    ("index", "about", gettext_lazy("About Weblate")),
    ("stats", "stats", gettext_lazy("Statistics")),
    ("keys", "keys", gettext_lazy("Keys")),
    ("donate", "donate", gettext_lazy("Support Weblate")),
)

REPO_URL = "https://api.github.com/repos/WeblateOrg/weblate"
ACTIVITY_URL = "https://api.github.com/repos/WeblateOrg/weblate/stats/commit_activity"
FALLBACK_STATS = {
    "stars": 4082,
    "issues": 447,
    "commits": 663,
}


class AboutView(TemplateView):
    page = "index"

    def page_context(self, context) -> None:
        context.update(
            {
                "title": gettext("About Weblate"),
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

    def page_context(self, context) -> None:
        context["title"] = gettext("Weblate statistics")

        stats = GlobalStats()

        totals = Profile.objects.aggregate(Sum("translated"))
        metrics = Metric.objects.get_current_metric(None, Metric.SCOPE_GLOBAL, 0)

        context["total_translations"] = totals["translated__sum"]
        context["stats"] = stats
        context["metrics"] = metrics

        context["top_users"] = top_users = (
            Profile.objects.order_by("-translated")
            .filter(user__is_bot=False, user__is_active=True)[:10]
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

    def page_context(self, context) -> None:
        context.update(
            {
                "title": gettext("Weblate keys"),
                "gpg_key_id": get_gpg_sign_key(),
                "gpg_key": get_gpg_public_key(),
                "public_ssh_keys": get_all_key_data(),
                "allow_index": True,
            }
        )


class DonateView(AboutView):
    page = "donate"
    cache_key = "weblate-repo-stats"

    def fetch_url(self, url: str):
        response = request("get", url)
        return response.json()

    def get_stats(self) -> dict[str, int]:
        result = cache.get(self.cache_key)
        if result is None:
            try:
                repo = self.fetch_url(REPO_URL)
                activity = self.fetch_url(ACTIVITY_URL)
            except requests.exceptions.RequestException:
                return FALLBACK_STATS
            activity = sorted(activity, key=lambda item: -item["week"])
            result = {
                "stars": repo["stargazers_count"],
                "issues": repo["open_issues_count"],
                "commits": sum(item["total"] for item in activity[:8]),
            }
            cache.set(self.cache_key, result, 24 * 3600)
        return result

    def page_context(self, context) -> None:
        context["title"] = gettext("Support Weblate")
        context.update(self.get_stats())
