# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resource authorization for contributor attribution."""

from __future__ import annotations

import csv
from copy import copy
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import PropertyMock, patch
from zipfile import ZipFile

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import connection
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from lxml import etree
from PIL import Image

from weblate.accounts.models import Profile
from weblate.accounts.notifications import (
    LicenseNotification,
    NewAnnouncementNotificaton,
)
from weblate.accounts.visibility import (
    can_view_contributor,
    contributor_translations,
    filter_contributor_changes,
    prepare_contributor_visibility,
    public_change_details,
)
from weblate.addons.ai import evaluation_units
from weblate.addons.models import Addon
from weblate.addons.webhooks import WebhookAddon
from weblate.api.serializers import ChangeSerializer, TranslationSerializer
from weblate.auth.data import SELECTION_ALL, SELECTION_MANUAL
from weblate.auth.models import (
    Group,
    Permission,
    Role,
    TeamMembership,
    User,
    get_anonymous,
)
from weblate.fonts.models import Font
from weblate.fonts.tests.utils import FONT
from weblate.formats.base import is_identity_safe_exporter
from weblate.formats.exporters import PoExporter
from weblate.formats.models import EXPORTERS
from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.autotranslate import AutoTranslate
from weblate.trans.bulk import bulk_perform
from weblate.trans.change_display import get_change_history_context
from weblate.trans.feeds import ChangeFeedScope, ChangesFeed, ObjectChangesFeed
from weblate.trans.models import (
    Alert,
    Change,
    Comment,
    Component,
    Project,
    Report,
    Suggestion,
    Translation,
    Unit,
)
from weblate.trans.source_snapshot import SourceSnapshot
from weblate.trans.templatetags.translations import format_last_changes_content
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.views.files import get_auxiliary_download_permissions
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED
from weblate.utils.views import download_translation_file
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from typing import Any

    from rest_framework.serializers import ListSerializer

    from weblate.accounts.models import Subscription
    from weblate.trans.bulk import BulkUnitEdit


class ContributorVisibilityTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.author = User.objects.create_user(
            "private-contributor",
            "private@example.org",
            full_name="Private Contributor",
        )
        self.translation = self.component.translation_set.get(language__code="cs")
        self.change = Change.objects.create(
            translation=self.translation,
            component=self.component,
            project=self.component.project,
            user=self.author,
            author=self.author,
            action=ActionEvents.USER_REVERT,
            details={"username": self.author.username, "email": self.author.email},
        )

    def hide_authors(self) -> None:
        permission = Permission.objects.get(codename="contribution.view_author")
        for role in Role.objects.filter(permissions=permission):
            role.permissions.remove(permission)
        self.user.clear_permissions_cache()
        get_anonymous().clear_permissions_cache()

    def test_default_and_removed_permission(self) -> None:
        self.assertTrue(can_view_contributor(self.user, self.change))
        self.hide_authors()
        self.assertFalse(can_view_contributor(self.user, self.change))
        self.assertFalse(can_view_contributor(get_anonymous(), self.change))
        self.assertEqual(public_change_details(self.change, self.user), {})
        self.assertEqual(self.change.get_details_display(viewer=self.user), "")
        self.change.refresh_from_db()
        self.assertEqual(self.change.author, self.author)
        self.assertEqual(self.change.details["email"], self.author.email)

    def test_html_and_api_disclosure(self) -> None:
        self.hide_authors()
        request = RequestFactory().get("/")
        request.user = self.user
        rendered = Template(
            "{% load user_display %}{% user_display change.user resource=change %}"
        ).render(Context({"request": request, "change": self.change}))
        data = ChangeSerializer(self.change, context={"request": request}).data
        self.assertIsNone(data["user"])
        self.assertIsNone(data["author"])
        self.assertEqual(data["details"], {})
        for identity in (
            self.author.username,
            self.author.full_name,
            self.author.email,
            self.author.get_absolute_url(),
        ):
            self.assertNotIn(identity, rendered + str(data))
        self.assertNotIn("avatar", rendered)

    def test_site_administrator(self) -> None:
        self.hide_authors()
        self.user.is_superuser = True
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, self.change))
        self.assertEqual(
            public_change_details(self.change, self.user), self.change.details
        )

    def test_repeated_checks_do_not_query(self) -> None:
        self.hide_authors()
        can_view_contributor(self.user, self.change)
        with self.assertNumQueries(0):
            for _ in range(20):
                self.assertFalse(can_view_contributor(self.user, self.change))

    def test_language_scoped_additive_grant(self) -> None:

        self.hide_authors()
        role = Role.objects.create(name="Scoped author visibility")
        role.permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        group = Group.objects.create(
            name="Scoped author viewers", language_selection=SELECTION_ALL
        )
        group.roles.add(role)
        group.components.add(self.component)
        self.user.groups.add(group)
        membership = TeamMembership.objects.get(user=self.user, group=group)
        membership.limit_languages.add(self.translation.language)
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, self.change))
        source = self.component.source_translation
        self.assertFalse(can_view_contributor(self.user, source))
        self.assertFalse(can_view_contributor(self.user, self.component))

    def test_serializer_list_checks_do_not_query(self) -> None:
        self.hide_authors()
        request = RequestFactory().get("/")
        request.user = self.user
        can_view_contributor(self.user, self.change)
        _ = ChangeSerializer(self.change, context={"request": request}).data
        with self.assertNumQueries(0):
            data = ChangeSerializer(
                [self.change] * 20, many=True, context={"request": request}
            ).data
        self.assertEqual(len(data), 20)
        self.assertTrue(
            all(row["user"] is None and row["author"] is None for row in data)
        )

    def test_notification_recipient_controls_attribution(self) -> None:

        self.hide_authors()
        notification = NewAnnouncementNotificaton([])
        subscription = SimpleNamespace(
            user=self.user, get_unsubscribe_url=lambda: "/unsubscribe/"
        )
        context = notification.get_context(
            self.change, subscription=cast("Subscription", subscription)
        )
        self.assertIsNone(context["user"])
        self.assertNotIn(
            self.author.full_name, notification.get_headers(context)["From"]
        )
        self.assertEqual(context["details"], {})
        self.user.is_superuser = True
        self.user.clear_permissions_cache()
        context = notification.get_context(
            self.change, subscription=cast("Subscription", subscription)
        )
        self.assertEqual(context["user"], self.author)
        self.assertIn(self.author.full_name, notification.get_headers(context)["From"])

    def test_content_download_permission_preserved_without_author_access(self) -> None:
        self.assertTrue(self.user.has_perm("translation.download", self.translation))
        self.hide_authors()
        self.assertTrue(self.user.has_perm("translation.download", self.translation))
        self.assertTrue(
            self.translation.__class__.objects.filter(pk=self.translation.pk)
            .filter_permission_scope(self.user, "translation.download")
            .exists()
        )
        self.assertTrue(self.user.has_perm("unit.edit", self.translation))
        self.assertTrue(self.user.has_perm("comment.add", self.translation))
        self.assertTrue(self.user.has_perm("suggestion.add", self.translation))

    def test_project_administrator_and_unrelated_project(self) -> None:

        self.hide_authors()
        Role.objects.get(name="Administration").permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        self.project.add_user(self.user, "Administration")
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, self.translation))
        unrelated = Project.objects.create(
            name="Unrelated identity scope", slug="unrelated-identity"
        )
        self.assertFalse(can_view_contributor(self.user, unrelated))

    def test_translation_preserves_actor_without_visibility(self) -> None:

        self.hide_authors()
        unit = self.translation.unit_set.get(source="Hello, world!\n")
        self.assertTrue(
            unit.translate(self.user, "Confidential translation\n", STATE_TRANSLATED)
        )
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Confidential translation\n")
        change = unit.change_set.get(target=unit.target)
        self.assertEqual(change.user, self.user)
        self.assertEqual(change.author, self.user)

    def test_last_author_names_are_loaded_together(self) -> None:

        unit = self.translation.unit_set.get(source="Hello, world!\n")
        unit.change_set.create(
            action=ActionEvents.CHANGE,
            user=self.author,
            author=self.author,
            target="Updated",
        )
        self.translation.stats.fetch_last_change()
        _ = self.translation.stats.last_author
        can_view_contributor(self.user, self.translation)
        request = RequestFactory().get("/")
        request.user = self.user
        serializer = TranslationSerializer(
            [self.translation] * 20, many=True, context={"request": request}
        )
        child = cast("TranslationSerializer", cast("ListSerializer", serializer).child)
        with self.assertNumQueries(1):
            names = [child.get_last_author(self.translation) for _ in range(20)]
        self.assertEqual(names, [self.author.full_name] * 20)
        self.hide_authors()
        can_view_contributor(self.user, self.translation)
        with self.assertNumQueries(0):
            self.assertIsNone(child.get_last_author(self.translation))

    def test_nested_identity_metadata_is_not_exported(self) -> None:
        self.hide_authors()
        self.change.details = {
            "count": {"username": self.author.username},
            "state": [self.author.email],
            "source": {"author": self.author.full_name},
            "comment": "User-provided content",
        }
        self.assertEqual(
            public_change_details(self.change, self.user),
            {},
        )

    def test_role_and_membership_cache_invalidation(self) -> None:

        self.hide_authors()
        role = Role.objects.create(name="Cached attribution")
        role.permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        group = Group.objects.create(
            name="Cached viewers", language_selection=SELECTION_ALL
        )
        group.projects.add(self.project)
        group.roles.add(role)
        self.assertFalse(can_view_contributor(self.user, self.translation))
        self.assertFalse(
            contributor_translations(self.user).filter(pk=self.translation.pk).exists()
        )
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, self.translation))
        self.assertTrue(
            contributor_translations(self.user).filter(pk=self.translation.pk).exists()
        )
        role.permissions.clear()
        self.user.clear_permissions_cache()
        self.assertFalse(can_view_contributor(self.user, self.translation))
        self.assertFalse(
            contributor_translations(self.user).filter(pk=self.translation.pk).exists()
        )
        role.permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, self.translation))
        self.user.groups.remove(group)
        self.user.clear_permissions_cache()
        self.assertFalse(can_view_contributor(self.user, self.translation))

    def test_translation_scopes_remain_in_subquery(self) -> None:

        # Warm permission caches without evaluating the translation queryset.
        contributor_translations(self.user)
        with self.assertNumQueries(0):
            translations = contributor_translations(self.user)
            changes = filter_contributor_changes(
                Change.objects.filter(pk=self.change.pk), self.user
            )
            _sql, original_params = changes.query.sql_with_params()
        with self.assertNumQueries(1):
            self.assertEqual(
                list(changes.values_list("pk", flat=True)), [self.change.pk]
            )

        before_count = translations.count()
        languages = Language.objects.bulk_create(
            [
                Language(name=f"Attribution {index}", code=f"attribution-{index}")
                for index in range(20)
            ]
        )
        additional_translations = []
        for language in languages:
            translation = copy(self.translation)
            translation.pk = None
            translation.language = language
            translation.language_code = language.code
            additional_translations.append(translation)
        Translation.objects.bulk_create(additional_translations)
        self.assertEqual(translations.count(), before_count + len(languages))
        with self.assertNumQueries(0):
            changes = filter_contributor_changes(
                Change.objects.filter(pk=self.change.pk), self.user
            )
            _sql, expanded_params = changes.query.sql_with_params()
        self.assertEqual(original_params, expanded_params)

    def test_translation_scopes_resolve_anonymous_viewer(self) -> None:

        self.assertEqual(
            set(contributor_translations(AnonymousUser()).values_list("pk", flat=True)),
            set(contributor_translations(get_anonymous()).values_list("pk", flat=True)),
        )

    def test_contribution_lists_filter_and_paginate(self) -> None:

        self.hide_authors()
        german = self.component.translation_set.get(language_code="de")
        denied = self.component.translation_set.get(language_code="it")
        role = Role.objects.create(name="Contribution list attribution")
        role.permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        group = Group.objects.create(name="Contribution list viewers")
        group.roles.add(role)
        group.components.add(self.component)
        group.languages.add(self.translation.language, german.language)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        for translation in (self.translation, self.translation, german, denied):
            Change.objects.create(
                translation=translation,
                user=self.author,
                action=ActionEvents.CHANGE,
            )

        expected = list(
            self.component.translation_set.filter(
                pk__in=(self.translation.pk, german.pk)
            ).order()
        )
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("user_contributions", kwargs={"user": self.author.username}),
        )
        self.assertEqual(response.status_code, 200)
        paginator_page = response.context["page_user_translations"]
        self.assertEqual(paginator_page.paginator.count, 2)
        self.assertEqual(list(paginator_page), expected)
        for page, translation in enumerate(expected, start=1):
            with self.subTest(page=page):
                response = self.client.get(
                    reverse(
                        "api:user-contributions",
                        kwargs={"username": self.author.username},
                    ),
                    {"page_size": 1, "page": page},
                )
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["count"], 2)
                self.assertEqual(
                    [row["language_code"] for row in data["results"]],
                    [translation.language_code],
                )

    def test_suggestion_list_filters_contributors(self) -> None:

        unit = self.translation.unit_set.get(source="Hello, world!\n")
        suggestion = Suggestion.objects.create(
            unit=unit, user=self.author, target="Attributed suggestion"
        )
        url = reverse("user_suggestions", kwargs={"user": self.author.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(suggestion, response.context["object_list"])
        self.hide_authors()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(suggestion, response.context["object_list"])

    def test_workspace_and_global_scopes(self) -> None:

        self.hide_authors()
        workspace = Workspace.objects.create(name="Attribution workspace")
        change = Change(
            workspace=workspace,
            user=self.author,
            action=ActionEvents.WORKSPACE_SETTING_CHANGE,
        )
        self.assertFalse(can_view_contributor(self.user, change))
        role = Role.objects.create(name="Workspace attribution")
        role.permissions.add(Permission.objects.get(codename="workspace.edit"))
        group = Group.objects.create(
            name="Workspace attribution", defining_workspace=workspace
        )
        group.roles.add(role)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, change))
        change.save()
        self.assertTrue(
            filter_contributor_changes(
                Change.objects.filter(pk=change.pk), self.user
            ).exists()
        )
        role.permissions.set(
            Permission.objects.filter(codename="workspace.edit_members")
        )
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, change))
        change.project = self.project
        self.assertFalse(can_view_contributor(self.user, change))
        self.assertFalse(can_view_contributor(self.user, Change(user=self.author)))
        self.user.is_superuser = True
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, Change(user=self.author)))

    def test_original_download_denied_and_content_export_allowed(self) -> None:

        self.hide_authors()
        for method in ("get", "head"):
            request = getattr(RequestFactory(), method)("/")
            request.user = self.user
            with self.assertRaises(PermissionDenied):
                download_translation_file(request, self.translation)
        request = RequestFactory().get("/")
        request.user = self.user
        response = download_translation_file(request, self.translation, "po")
        self.assertEqual(response.status_code, 200)
        for value in (self.author.username, self.author.email, self.author.full_name):
            self.assertNotIn(value.encode(), response.content)

    def test_comment_details_are_action_specific(self) -> None:
        self.hide_authors()
        self.change.details = {"comment": "User-provided comment"}
        self.assertEqual(public_change_details(self.change, self.user), {})
        self.change.action = ActionEvents.COMMENT
        self.assertEqual(
            public_change_details(self.change, self.user), self.change.details
        )

    def test_history_preserves_source_snapshot_rendering(self) -> None:

        unit = self.translation.unit_set.get(source="Hello, world!\n")
        snapshot = SourceSnapshot.from_unit(unit).as_dict()
        snapshot["language_name"] = "Historical source language"
        previous = {
            **snapshot,
            "number": snapshot["number"] + 1,
            "language_name": "Previous source language",
        }
        change = Change(
            unit=unit,
            user=self.author,
            author=self.author,
            action=ActionEvents.SOURCE_CHANGE,
            old="Old source",
            target="New source",
            details={"source_snapshot": snapshot, "previous_source_snapshot": previous},
        )
        expected = get_change_history_context(change, viewer=self.user)
        self.hide_authors()
        self.assertEqual(get_change_history_context(change, viewer=self.user), expected)
        cast("dict[str, Any]", snapshot)["username"] = self.author.username
        self.assertNotIn(
            "username", public_change_details(change, self.user)["source_snapshot"]
        )

    def test_private_project_author_searches_use_request_user(self) -> None:

        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save(update_fields=["access_control"])
        self.project.add_user(self.user, "Administration")
        unit = self.translation.unit_set.get(source="Hello, world!\n")
        unit.change_set.create(
            user=self.author,
            author=self.author,
            action=ActionEvents.CHANGE,
            target="Private edit",
        )
        self.client.force_login(self.user)
        urls = (
            reverse("api:unit-list"),
            reverse(
                "api:translation-units",
                kwargs={
                    "component__project__slug": self.project.slug,
                    "component__slug": self.component.slug,
                    "language__code": self.translation.language.code,
                },
            ),
        )
        for url in urls:
            response = self.client.get(url, {"q": f"changed_by:{self.author.username}"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], 1)
        self.hide_authors()
        for url in urls:
            response = self.client.get(url, {"q": f"changed_by:{self.author.username}"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], 0)

    def test_automatic_translation_editor_attribution(self) -> None:
        unit = self.translation.unit_set.get(source="Hello, world!\n")
        unit.__class__.objects.filter(pk=unit.pk).update(automatically_translated=True)
        unit.change_set.create(
            user=self.author,
            author=self.author,
            action=ActionEvents.AUTO,
            target="Automatic edit",
        )
        self.client.force_login(self.user)
        url = self.translation.get_translate_url()
        response = self.client.get(url, {"checksum": unit.checksum})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.author.full_name)
        self.hide_authors()
        response = self.client.get(url, {"checksum": unit.checksum})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.author.full_name)
        self.assertContains(response, "This string was translated automatically.")

    def test_exporters_require_explicit_safety_declaration(self) -> None:

        class UnclassifiedExporter(PoExporter):
            pass

        self.assertFalse(is_identity_safe_exporter(UnclassifiedExporter))

        mono = self.create_po_mono(
            name="identity-export-template", project=self.project
        )
        bilingual = self.create_po(
            name="identity-export-bilingual", project=self.project
        )
        translations = (
            bilingual.translation_set.get(language_code="cs"),
            mono.translation_set.get(language_code="cs"),
        )
        for translation in translations:
            translation.store.store.updateheader(
                last_translator=f"{self.author.full_name} <{self.author.email}>"
            )
            for unit in translation.unit_set.all():
                unit.change_set.create(
                    user=self.author,
                    author=self.author,
                    action=ActionEvents.CHANGE,
                    target=unit.target,
                )
                Comment.objects.create(
                    unit=unit,
                    user=self.author,
                    comment="Translator note naming Mentioned Person",
                )
                Suggestion.objects.create(
                    unit=unit, user=self.author, target="Suggested content"
                )
        self.hide_authors()
        exercised = set()
        for name, exporter_class in EXPORTERS.items():
            self.assertTrue(is_identity_safe_exporter(exporter_class))
            for translation in translations:
                # Multivalue CSV also serializes single-valued units, while
                # its download support check requires its native format.
                if not exporter_class.supports(translation) and name != "csv-multi":
                    continue
                with self.subTest(exporter=name, translation=translation.language_code):
                    exercised.add(name)
                    exporter = exporter_class(translation=translation)
                    exporter.add_units(
                        translation.unit_set.prefetch_full().order_by("position")
                    )
                    output = exporter.serialize()
                    chunks = [output if isinstance(output, bytes) else output.encode()]
                    if name == "xlsx":
                        with ZipFile(BytesIO(chunks[0])) as archive:
                            chunks = [
                                archive.read(path)
                                for path in archive.namelist()
                                if path.endswith(".xml")
                            ]
                    for chunk in chunks:
                        text = chunk.decode("utf-8", errors="replace")
                        for identity in (
                            self.author.username,
                            self.author.email,
                            self.author.full_name,
                        ):
                            self.assertNotIn(identity, text)
                        if name in {
                            "xliff",
                            "xliff11",
                            "tmx",
                            "tbx",
                            "aresource",
                            "xlsx",
                        }:
                            root = etree.fromstring(chunk)
                            for node in root.iter():
                                for value in node.attrib.values():
                                    for identity in (
                                        self.author.username,
                                        self.author.email,
                                        self.author.full_name,
                                    ):
                                        self.assertNotIn(identity, value)
                    if name == "po":
                        self.assertIn("Mentioned Person", chunks[0].decode())
        self.assertEqual(exercised, set(EXPORTERS))

    def test_independent_reports_and_trusted_webhooks(self) -> None:

        self.project.add_user(self.user, "Administration")
        self.hide_authors()
        report = Report.objects.create(
            creator=self.author,
            kind=Report.Kind.CREDITS,
            project=self.project,
            parameters={"own_data": False},
        )
        self.assertTrue(report.can_access(self.user))
        addon = WebhookAddon(Addon())
        payload = addon.build_webhook_payload(self.change)
        self.assertEqual(payload["user"], self.author.username)
        self.assertEqual(payload["author"], self.author.username)

    def test_alert_dismissal_attribution(self) -> None:

        Alert.objects.create(
            component=self.component,
            name="MissingLicense",
            dismissed_at=timezone.now(),
            dismissed_by=self.author,
        )
        self.client.force_login(self.user)
        response = self.client.get(self.component.get_absolute_url(), {"alerts": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.author.full_name)
        self.hide_authors()
        response = self.client.get(self.component.get_absolute_url(), {"alerts": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.author.full_name)
        self.assertContains(response, "Dismissed")

    def test_private_license_email_uses_recipient(self) -> None:

        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save(update_fields=["access_control"])
        self.project.add_user(self.user, "Administration")
        self.change.action = ActionEvents.LICENSE_CHANGE
        self.change.old = "MIT"
        self.change.target = "Apache-2.0"
        subscription = cast(
            "Subscription",
            SimpleNamespace(
                user=self.user, get_unsubscribe_url=lambda: "/unsubscribe/"
            ),
        )
        notification = LicenseNotification([])
        context = notification.get_context(self.change, subscription=subscription)
        context["subject"] = "License change"
        rendered = render_to_string("mail/component_license.html", context)
        self.assertIn("MIT", rendered)
        self.assertIn("Apache-2.0", rendered)
        self.hide_authors()
        context = notification.get_context(self.change, subscription=subscription)
        self.assertEqual(context["change_details"], "")
        context["subject"] = "License change"
        self.assertNotIn(
            self.author.full_name,
            render_to_string("mail/component_license.html", context),
        )

    def test_project_language_author_filters_match_display(self) -> None:

        self.hide_authors()
        role = Role.objects.create(name="Language identity viewers")
        role.permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        group = Group.objects.create(
            name="Language identity viewers", language_selection=SELECTION_MANUAL
        )
        group.roles.add(role)
        group.projects.add(self.project)
        group.languages.add(self.translation.language)
        self.user.groups.add(group)
        allowed = Change.objects.create(
            project=self.project,
            language=self.translation.language,
            user=self.author,
            action=ActionEvents.ANNOUNCEMENT,
            target="Allowed notice",
        )
        denied = Change.objects.create(
            project=self.project,
            language=self.component.source_language,
            user=self.author,
            action=ActionEvents.ANNOUNCEMENT,
            target="Denied notice",
        )
        self.client.force_login(self.user)
        for membership_limit in (False, True):
            if membership_limit:
                group.language_selection = SELECTION_ALL
                group.save(update_fields=["language_selection"])
                TeamMembership.objects.get(
                    user=self.user, group=group
                ).limit_languages.add(self.translation.language)
            self.user.clear_permissions_cache()
            with self.subTest(membership_limit=membership_limit):
                self.assertTrue(can_view_contributor(self.user, allowed))
                self.assertFalse(can_view_contributor(self.user, denied))
                queryset = Change.objects.filter(pk__in=(allowed.pk, denied.pk))
                self.assertEqual(
                    set(
                        filter_contributor_changes(queryset, self.user).values_list(
                            "pk", flat=True
                        )
                    ),
                    {allowed.pk},
                )
                for url in (
                    reverse("api:change-list"),
                    reverse("api:project-changes", kwargs={"slug": self.project.slug}),
                ):
                    response = self.client.get(url, {"user": self.author.username})
                    self.assertEqual(response.status_code, 200)
                    ids = {row["id"] for row in response.json()["results"]}
                    self.assertIn(allowed.pk, ids)
                    self.assertNotIn(denied.pk, ids)
                response = self.client.get(
                    reverse("changes"), {"user": self.author.username}
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Denied notice")
        with self.assertNumQueries(1):
            list(
                filter_contributor_changes(
                    Change.objects.filter(pk__in=(allowed.pk, denied.pk)), self.user
                )
            )

        Component.objects.filter(pk=self.component.pk).update(restricted=True)
        self.component.refresh_from_db()
        self.user.clear_permissions_cache()
        self.assertFalse(can_view_contributor(self.user, allowed))
        self.assertFalse(
            filter_contributor_changes(
                Change.objects.filter(pk=allowed.pk), self.user
            ).exists()
        )
        group.components.add(self.component)
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, allowed))
        self.assertTrue(
            filter_contributor_changes(
                Change.objects.filter(pk=allowed.pk), self.user
            ).exists()
        )
        self.project.enforced_2fa = True
        self.project.save(update_fields=["enforced_2fa"])
        self.user.clear_permissions_cache()
        self.assertFalse(can_view_contributor(self.user, allowed))
        self.assertFalse(
            filter_contributor_changes(
                Change.objects.filter(pk=allowed.pk), self.user
            ).exists()
        )
        self.user.is_superuser = True
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, allowed))
        self.assertTrue(
            filter_contributor_changes(
                Change.objects.filter(pk=allowed.pk), self.user
            ).exists()
        )

    def test_project_author_filters_enforce_2fa(self) -> None:

        change = Change.objects.create(
            project=self.project,
            user=self.author,
            action=ActionEvents.ANNOUNCEMENT,
            target="Project-only announcement",
        )
        self.project.enforced_2fa = True
        self.project.save(update_fields=["enforced_2fa"])
        self.client.force_login(self.user)
        queryset = Change.objects.filter(pk=change.pk)
        for has_2fa in (False, True):
            with (
                self.subTest(has_2fa=has_2fa),
                patch.object(
                    Profile, "has_2fa", new_callable=PropertyMock, return_value=has_2fa
                ),
            ):
                self.user.clear_permissions_cache()
                self.assertEqual(can_view_contributor(self.user, change), has_2fa)
                self.assertEqual(
                    filter_contributor_changes(queryset, self.user).exists(), has_2fa
                )
                for url in (
                    reverse("api:change-list"),
                    reverse("api:project-changes", kwargs={"slug": self.project.slug}),
                ):
                    response = self.client.get(url, {"user": self.author.username})
                    self.assertEqual(response.status_code, 200)
                    ids = {row["id"] for row in response.json()["results"]}
                    self.assertEqual(change.pk in ids, has_2fa)
                response = self.client.get(
                    reverse("changes"), {"user": self.author.username}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    b"Project-only announcement" in response.content, has_2fa
                )
        for attribute in ("is_bot", "is_superuser"):
            with self.subTest(attribute=attribute):
                setattr(self.user, attribute, True)
                self.user.clear_permissions_cache()
                self.assertTrue(can_view_contributor(self.user, change))
                self.assertTrue(
                    filter_contributor_changes(queryset, self.user).exists()
                )
                setattr(self.user, attribute, False)

    def test_distinct_project_language_scopes_are_batched(self) -> None:

        translations = list(self.component.translation_set.select_related("language"))
        self.assertGreaterEqual(len(translations), 2)
        changes = [
            Change.objects.create(
                project=self.project,
                language=translation.language,
                user=self.author,
                action=ActionEvents.ANNOUNCEMENT,
                target="Language announcement",
            )
            for translation in translations
        ]
        request = RequestFactory().get("/")
        request.user = self.user
        # Warm ordinary role, 2FA, and URL caches, without checking these scopes.
        _ = self.user.profile.has_2fa
        _ = ChangeSerializer(self.change, context={"request": request}).data
        for visible in (True, False):
            if not visible:
                self.hide_authors()
                _ = ChangeSerializer(self.change, context={"request": request}).data
            self.user.contributor_visibility = {}
            with self.assertNumQueries(1):
                prepare_contributor_visibility(self.user, changes)
            with self.assertNumQueries(0):
                for change in changes:
                    self.assertEqual(can_view_contributor(self.user, change), visible)
            self.user.contributor_visibility = {}
            with self.assertNumQueries(1):
                rows = ChangeSerializer(
                    changes, many=True, context={"request": request}
                ).data
            self.assertTrue(all(bool(row["user"]) == visible for row in rows))
            self.user.contributor_visibility = {}
            with self.assertNumQueries(1):
                context = format_last_changes_content(changes, self.user)
            self.assertEqual(len(context["changes_with_context"]), len(changes))
            for get_items in (
                lambda: ChangesFeed().items(self.user),
                lambda: ObjectChangesFeed().items(
                    ChangeFeedScope(self.user, self.project)
                ),
            ):
                self.user.contributor_visibility = {}
                with patch.object(Change.objects, "last_changes") as last_changes:
                    last_changes.return_value.recent.return_value = changes
                    with self.assertNumQueries(1):
                        self.assertEqual(get_items(), changes)
                    with self.assertNumQueries(0):
                        for change in changes:
                            self.assertEqual(
                                can_view_contributor(self.user, change), visible
                            )
            anonymous_request = RequestFactory().get("/")
            anonymous_request.user = AnonymousUser()
            # Anonymous requests must share the resolved public viewer too.
            _ = ChangeSerializer(
                changes, many=True, context={"request": anonymous_request}
            ).data
            with CaptureQueriesContext(connection) as single_scope:
                _ = ChangeSerializer(
                    changes[:1], many=True, context={"request": anonymous_request}
                ).data
            with CaptureQueriesContext(connection) as distinct_scopes:
                rows = ChangeSerializer(
                    changes, many=True, context={"request": anonymous_request}
                ).data
            self.assertEqual(len(single_scope), len(distinct_scopes))
            self.assertTrue(all(bool(row["user"]) == visible for row in rows))

    def test_asset_uploader_attribution(self) -> None:

        image = BytesIO()
        Image.new("RGB", (10, 10)).save(image, format="PNG")
        screenshot = Screenshot.objects.create(
            name="Private uploader",
            translation=self.translation,
            user=self.author,
            image=ContentFile(image.getvalue(), name="private-uploader.png"),
        )
        font = Font.objects.create(
            project=self.project,
            user=self.author,
            family="Test font",
            style="Regular",
            font=ContentFile(FONT.read_bytes(), name="private-uploader.ttf"),
        )
        self.client.force_login(self.user)
        for visible in (True, False):
            if not visible:
                self.hide_authors()
            for obj in (screenshot, font):
                response = self.client.get(obj.get_absolute_url())
                self.assertEqual(response.status_code, 200)
                if visible:
                    self.assertContains(response, self.author.full_name)
                else:
                    for identity in (
                        self.author.full_name,
                        self.author.username,
                        self.author.email,
                        self.author.get_absolute_url(),
                    ):
                        self.assertNotContains(response, identity)

    def test_bulk_author_search_and_trusted_automation(self) -> None:

        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save(update_fields=["access_control"])
        self.project.add_user(self.user, "Administration")
        unit = self.translation.unit_set.get(source="Hello, world!\n")
        unit.change_set.create(
            user=self.author,
            author=self.author,
            action=ActionEvents.CHANGE,
            target="Private edit",
        )
        Unit.objects.filter(pk=unit.pk).update(state=STATE_TRANSLATED)
        for visible in (True, False):
            if not visible:
                self.hide_authors()
            for enforce in (True, False):
                preview: list[BulkUnitEdit] = []
                options: dict[str, Any] = {
                    "query": f"changed_by:{self.author.username}",
                    "target_state": STATE_FUZZY,
                    "add_flags": "",
                    "remove_flags": "",
                    "add_labels": self.project.label_set.none(),
                    "remove_labels": self.project.label_set.none(),
                    "project": self.project,
                    "enforce_permissions": enforce,
                }
                expected = int(visible or not enforce)
                automatic = AutoTranslate(
                    translation=self.translation,
                    user=self.user,
                    q=options["query"],
                    mode="translate",
                    enforce_permissions=enforce,
                )
                self.assertEqual(
                    automatic.get_units().filter(pk=unit.pk).exists(), bool(expected)
                )
                self.assertTrue(
                    evaluation_units(
                        self.component, cast("Any", {"q": options["query"]})
                    )
                    .filter(pk=unit.pk)
                    .exists()
                )
                self.assertEqual(
                    bulk_perform(
                        self.user,
                        Unit.objects.filter(pk=unit.pk),
                        preview=preview,
                        **options,
                    ),
                    expected,
                )
                self.assertEqual(len(preview), expected)
                self.assertEqual(
                    bulk_perform(self.user, Unit.objects.filter(pk=unit.pk), **options),
                    expected,
                )
                # Restore the state so the next case still has an edit to apply.
                Unit.objects.filter(pk=unit.pk).update(state=STATE_TRANSLATED)

    def test_original_archive_auxiliary_language_scope(self) -> None:

        self.component = self.create_po_mono(
            name="auxiliary-privacy", project=self.project
        )
        self.translation = self.component.translation_set.get(language_code="cs")
        source = self.component.source_translation
        self.assertTrue(source.filename)
        source_content = Path(source.get_filename()).read_text(encoding="utf-8")
        for filename in ("private-base.po", "private-intermediate.po"):
            Path(self.component.full_path, filename).write_text(
                f"# {self.author.full_name} <{self.author.email}>\n" + source_content,
                encoding="utf-8",
            )
        Component.objects.filter(pk=self.component.pk).update(
            template=source.filename,
            new_base="private-base.po",
            intermediate="private-intermediate.po",
        )
        self.component.refresh_from_db()
        other = self.create_po_mono(name="auxiliary-other", project=self.project)
        self.hide_authors()
        role = Role.objects.create(name="Auxiliary language scope")
        role.permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        group = Group.objects.create(
            name="Auxiliary language scope", language_selection=SELECTION_ALL
        )
        group.roles.add(role)
        group.components.add(self.component)
        self.user.groups.add(group)
        membership = TeamMembership.objects.get(user=self.user, group=group)
        membership.limit_languages.add(self.translation.language)
        self.user.clear_permissions_cache()
        _ = (
            self.user.project_permissions,
            self.user.component_permissions,
            self.user.profile.has_2fa,
        )
        with self.assertNumQueries(2):
            permissions = get_auxiliary_download_permissions(
                self.user, {self.component.pk: self.component, other.pk: other}
            )
        self.assertTrue(any(permissions.values()))
        self.assertTrue(any(not value for value in permissions.values()))
        self.client.force_login(self.user)
        for url in (
            reverse("download", kwargs={"path": self.component.get_url_path()}),
            reverse(
                "api:component-file",
                kwargs={
                    "project__slug": self.project.slug,
                    "slug": self.component.slug,
                },
            ),
        ):
            response = self.client.get(url, {"format": "zip"})
            self.assertEqual(response.status_code, 200)
            with ZipFile(BytesIO(b"".join(response))) as archive:
                names = archive.namelist()
                for name in names:
                    self.assertNotIn(self.author.email.encode(), archive.read(name))
            self.assertTrue(
                any(name.endswith(self.translation.filename) for name in names)
            )
            self.assertFalse(any(name.endswith(source.filename) for name in names))
            self.assertFalse(
                any(
                    name.endswith(("private-base.po", "private-intermediate.po"))
                    for name in names
                )
            )
        membership.limit_languages.clear()
        self.user.clear_permissions_cache()
        response = self.client.get(
            reverse("download", kwargs={"path": self.component.get_url_path()})
        )
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(b"".join(response))) as archive:
            names = archive.namelist()
        for filename in (source.filename, "private-base.po", "private-intermediate.po"):
            self.assertTrue(any(name.endswith(filename) for name in names))

    def test_component_wide_author_filters_match_display(self) -> None:

        self.hide_authors()
        changes = [
            Change.objects.create(
                component=self.component, user=self.author, action=action
            )
            for action in (ActionEvents.LOCK, ActionEvents.UNLOCK)
        ]
        role = Role.objects.create(name="Component event identities")
        role.permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        group = Group.objects.create(
            name="Component event identities", language_selection=SELECTION_MANUAL
        )
        group.roles.add(role)
        group.projects.add(self.project)
        group.languages.add(self.translation.language)
        self.user.groups.add(group)
        self.client.force_login(self.user)
        for membership_limit in (False, True):
            if membership_limit:
                group.language_selection = SELECTION_ALL
                group.save(update_fields=["language_selection"])
                TeamMembership.objects.get(
                    user=self.user, group=group
                ).limit_languages.add(self.translation.language)
            self.user.clear_permissions_cache()
            visible = not membership_limit
            with self.subTest(membership_limit=membership_limit):
                for change in changes:
                    self.assertEqual(can_view_contributor(self.user, change), visible)
                queryset = Change.objects.filter(
                    pk__in=[change.pk for change in changes]
                )
                self.assertEqual(
                    filter_contributor_changes(queryset, self.user).count(),
                    len(changes) if visible else 0,
                )
                for url in (
                    reverse("api:change-list"),
                    reverse("api:project-changes", kwargs={"slug": self.project.slug}),
                    reverse(
                        "api:component-changes",
                        kwargs={
                            "project__slug": self.project.slug,
                            "slug": self.component.slug,
                        },
                    ),
                ):
                    response = self.client.get(url, {"user": self.author.username})
                    self.assertEqual(response.status_code, 200)
                    ids = {row["id"] for row in response.json()["results"]}
                    for change in changes:
                        self.assertEqual(change.pk in ids, visible)
                response = self.client.get(
                    reverse("changes"), {"user": self.author.username}
                )
                self.assertEqual(response.status_code, 200)
                ids = {change.pk for change in response.context["object_list"]}
                for change in changes:
                    self.assertEqual(change.pk in ids, visible)
        membership = TeamMembership.objects.get(user=self.user, group=group)
        membership.limit_languages.clear()
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.user.clear_permissions_cache()
        self.assertFalse(can_view_contributor(self.user, changes[0]))
        self.assertFalse(filter_contributor_changes(queryset, self.user).exists())
        group.components.add(self.component)
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, changes[0]))
        self.assertEqual(
            filter_contributor_changes(queryset, self.user).count(), len(changes)
        )
        self.project.enforced_2fa = True
        self.project.save(update_fields=["enforced_2fa"])
        self.user.clear_permissions_cache()
        self.assertFalse(can_view_contributor(self.user, changes[0]))
        self.assertFalse(filter_contributor_changes(queryset, self.user).exists())
        with self.assertNumQueries(1):
            self.assertEqual(list(filter_contributor_changes(queryset, self.user)), [])

    def test_csv_author_filters_use_download_authorization(self) -> None:

        self.hide_authors()
        permission = Permission.objects.get(codename="change.download")
        role = Role.objects.create(name="Independent history download")
        role.permissions.add(permission)
        group = Group.objects.create(
            name="Independent history download", language_selection=SELECTION_ALL
        )
        group.projects.add(self.project)
        group.roles.add(role)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        other = Change.objects.create(
            translation=self.translation,
            user=self.user,
            action=ActionEvents.CHANGE,
            target="Another contributor",
        )
        self.assertFalse(can_view_contributor(self.user, self.change))
        self.client.force_login(self.user)
        url = reverse("changes-csv", kwargs={"path": self.project.get_url_path()})
        for params, included, excluded in (
            ({}, (self.change, other), ()),
            ({"user": self.author.username}, (self.change,), (other,)),
            ({"exclude_user": self.author.username}, (other,), (self.change,)),
        ):
            response = self.client.get(url, params)
            self.assertEqual(response.status_code, 200)
            rows = list(csv.DictReader(StringIO(response.content.decode())))
            identities = {(row["user"], row["target"]) for row in rows}
            for change in included:
                assert change.user is not None
                self.assertIn((change.user.username, change.target), identities)
            for change in excluded:
                assert change.user is not None
                self.assertNotIn((change.user.username, change.target), identities)
        role.permissions.remove(permission)
        self.user.clear_permissions_cache()
        response = self.client.get(url, {"user": self.author.username})
        self.assertEqual(response.status_code, 403)
