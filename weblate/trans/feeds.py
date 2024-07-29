# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext

from weblate.lang.models import Language
from weblate.trans.models import Change, Component, Project, Translation, Unit
from weblate.utils.stats import ProjectLanguage
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest, User


class ChangesFeed(Feed):
    """Generic RSS feed for Weblate changes."""

    def get_object(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> User:
        return request.user

    def title(self):
        return gettext("Recent changes in %s") % settings.SITE_TITLE

    def description(self):
        return gettext("All recent changes made using Weblate in %s.") % (
            settings.SITE_TITLE
        )

    def link(self):
        return reverse("home")

    def items(self, obj):
        return Change.objects.last_changes(obj).recent()

    def item_title(self, item):
        return item.get_action_display()

    def item_description(self, item):
        return str(item)

    def item_author_name(self, item):
        return item.get_user_display(False)

    def item_pubdate(self, item):
        return item.timestamp


class TranslationChangesFeed(ChangesFeed):
    """RSS feed for changes in translation."""

    def get_object(self, request: AuthenticatedHttpRequest, path):
        return parse_path(
            request,
            path,
            (Translation, Component, Project, Language, Unit, ProjectLanguage),
        )

    def title(self, obj):
        return gettext("Recent changes in %s") % obj

    def description(self, obj):
        return gettext("All recent changes made using Weblate in %s.") % obj

    def link(self, obj):
        return obj.get_absolute_url()

    def items(self, obj):
        return obj.change_set.prefetch().recent(skip_preload="translation")


class LanguageChangesFeed(TranslationChangesFeed):
    """RSS feed for changes in language."""

    def get_object(self, request: AuthenticatedHttpRequest, lang):
        return get_object_or_404(Language, code=lang)
