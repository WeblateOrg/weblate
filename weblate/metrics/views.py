# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views.generic import ListView

from weblate.accounts.visibility import profile_response
from weblate.metrics.contributors import (
    CONTRIBUTOR_SCOPES,
    can_view_contributor_ranking,
    contributor_ranking,
    load_ranked_contributors,
)
from weblate.metrics.models import ContributorCollection
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from django.core.paginator import _SupportsPagination
    from django.db.models import QuerySet

    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.metrics.contributors import ContributorScope
    from weblate.metrics.models import ContributorCount


@method_decorator(login_required, name="dispatch")
@method_decorator(profile_response, name="dispatch")
class ContributorList(ListView):
    request: AuthenticatedHttpRequest
    template_name = "metrics/contributors.html"
    paginate_by = 50

    @cached_property
    def path_object(self) -> ContributorScope:
        return parse_path(self.request, self.kwargs["path"], CONTRIBUTOR_SCOPES)

    def get_queryset(self) -> QuerySet[ContributorCount, tuple[int, int]]:
        if not can_view_contributor_ranking(self.request.user, self.path_object):
            raise Http404
        self.rankings_ready = ContributorCollection.is_ready()
        ranking = contributor_ranking(self.request.user, self.path_object)
        return ranking if self.rankings_ready else ranking.none()

    def get_context_data(
        self,
        *,
        object_list: _SupportsPagination[tuple[int, int]] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["contributors"] = load_ranked_contributors(context["object_list"])
        context["scope"] = self.path_object
        context["rankings_ready"] = self.rankings_ready
        return context
