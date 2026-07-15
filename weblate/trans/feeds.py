# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext

from weblate.lang.models import Language
from weblate.trans.models import Change, Component, Project, Translation, Unit
from weblate.utils.site import get_site_url
from weblate.utils.stats import ProjectLanguage
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest, User


type FeedObject = Translation | Component | Project | Language | Unit | ProjectLanguage


@dataclass(frozen=True)
class ChangeFeedScope:
    user: User
    obj: FeedObject


def get_change_feed_guid(change: Change) -> str:
    return get_site_url(reverse("show_change", kwargs={"pk": change.pk}))


class BaseFeed(Feed):
    def item_title(self, item):
        return item.get_action_display()

    def item_description(self, item):
        return str(item)

    def item_author_name(self, item):
        return item.get_user_display(False)

    def item_pubdate(self, item):
        return item.timestamp

    def item_guid(self, item):
        return get_change_feed_guid(item)

    def item_guid_is_permalink(self, item):
        return False


class ChangesFeed(BaseFeed):
    """Generic RSS feed for Weblate changes."""

    def get_object(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> User:
        return request.user

    def title(self):
        # Translators: %s is site title here
        return gettext("Recent changes on %s") % settings.SITE_TITLE

    def description(self):
        # Translators: %s is site title here
        return gettext("All recent changes made using Weblate on %s.") % (
            settings.SITE_TITLE
        )

    def link(self):
        return reverse("home")

    def items(self, obj):
        return Change.objects.last_changes(obj).recent()


class ObjectChangesFeed(BaseFeed):
    def title(self, scope: ChangeFeedScope):
        # Translators: %s is translation name
        return gettext("Recent changes in %s") % scope.obj

    def description(self, scope: ChangeFeedScope):
        # Translators: %s is translation name
        return gettext("All recent changes made using Weblate in %s.") % scope.obj

    def link(self, scope: ChangeFeedScope):
        return scope.obj.get_absolute_url()

    def items(self, scope: ChangeFeedScope):
        obj = scope.obj
        if isinstance(obj, Translation):
            changes = Change.objects.last_changes(scope.user, translation=obj)
            return changes.recent(skip_preload="translation")
        if isinstance(obj, Component):
            changes = Change.objects.last_changes(scope.user, component=obj)
        elif isinstance(obj, Project):
            changes = Change.objects.last_changes(scope.user, project=obj)
        elif isinstance(obj, Language):
            changes = Change.objects.last_changes(scope.user, language=obj)
        elif isinstance(obj, Unit):
            changes = Change.objects.last_changes(scope.user, unit=obj)
        else:
            changes = Change.objects.last_changes(
                scope.user, project=obj.project, language=obj.language
            )
        return changes.recent()


class TranslationChangesFeed(ObjectChangesFeed):
    """RSS feed for changes in translation."""

    # pylint: disable-next=arguments-differ
    def get_object(self, request: AuthenticatedHttpRequest, path):
        return ChangeFeedScope(
            request.user,
            parse_path(
                request,
                path,
                (Translation, Component, Project, Language, Unit, ProjectLanguage),
            ),
        )


class LanguageChangesFeed(ObjectChangesFeed):
    """RSS feed for changes in language."""

    # pylint: disable-next=arguments-differ
    def get_object(self, request: AuthenticatedHttpRequest, lang):
        return ChangeFeedScope(request.user, get_object_or_404(Language, code=lang))
