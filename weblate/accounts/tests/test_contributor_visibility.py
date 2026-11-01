# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resource authorization for contributor attribution."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.template import Context, Template
from django.test import RequestFactory

from weblate.accounts.visibility import can_view_contributor, public_change_details
from weblate.api.serializers import ChangeSerializer
from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Permission, Role, User, get_anonymous
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change
from weblate.trans.tests.test_views import FixtureTestCase

if TYPE_CHECKING:
    from typing import Any

    from rest_framework.serializers import ListSerializer

    from weblate.accounts.models import Subscription


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
        from weblate.auth.models import Group, TeamMembership  # ruff: ignore[import-outside-top-level]

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
        from types import SimpleNamespace  # ruff: ignore[import-outside-top-level]

        from weblate.accounts.notifications import NewAnnouncementNotificaton  # ruff: ignore[import-outside-top-level]

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
        from weblate.trans.models import Project  # ruff: ignore[import-outside-top-level]

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
        from weblate.utils.state import STATE_TRANSLATED  # ruff: ignore[import-outside-top-level]

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
        from weblate.api.serializers import TranslationSerializer  # ruff: ignore[import-outside-top-level]

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
        from weblate.accounts.visibility import contributor_translation_ids  # ruff: ignore[import-outside-top-level]
        from weblate.auth.models import Group  # ruff: ignore[import-outside-top-level]

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
        self.assertNotIn(self.translation.pk, contributor_translation_ids(self.user))
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, self.translation))
        self.assertIn(self.translation.pk, contributor_translation_ids(self.user))
        role.permissions.clear()
        self.user.clear_permissions_cache()
        self.assertFalse(can_view_contributor(self.user, self.translation))
        self.assertNotIn(self.translation.pk, contributor_translation_ids(self.user))
        role.permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        self.user.clear_permissions_cache()
        self.assertTrue(can_view_contributor(self.user, self.translation))
        self.user.groups.remove(group)
        self.user.clear_permissions_cache()
        self.assertFalse(can_view_contributor(self.user, self.translation))

    def test_workspace_and_global_scopes(self) -> None:
        from weblate.auth.models import Group  # ruff: ignore[import-outside-top-level]
        from weblate.workspaces.models import Workspace  # ruff: ignore[import-outside-top-level]

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
        from weblate.accounts.visibility import filter_contributor_changes  # ruff: ignore[import-outside-top-level]

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
        from django.core.exceptions import PermissionDenied  # ruff: ignore[import-outside-top-level]

        from weblate.utils.views import download_translation_file  # ruff: ignore[import-outside-top-level]

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
        from weblate.trans.change_display import get_change_history_context  # ruff: ignore[import-outside-top-level]
        from weblate.trans.source_snapshot import SourceSnapshot  # ruff: ignore[import-outside-top-level]

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
        from django.urls import reverse  # ruff: ignore[import-outside-top-level]

        from weblate.trans.models import Project  # ruff: ignore[import-outside-top-level]

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
        from weblate.formats.base import is_identity_safe_exporter  # ruff: ignore[import-outside-top-level]
        from weblate.formats.exporters import PoExporter  # ruff: ignore[import-outside-top-level]
        from weblate.formats.models import EXPORTERS  # ruff: ignore[import-outside-top-level]

        class UnclassifiedExporter(PoExporter):
            pass

        self.assertFalse(is_identity_safe_exporter(UnclassifiedExporter))
        from io import BytesIO  # ruff: ignore[import-outside-top-level]
        from zipfile import ZipFile  # ruff: ignore[import-outside-top-level]

        from lxml import etree  # ruff: ignore[import-outside-top-level]

        from weblate.trans.models import Comment, Suggestion  # ruff: ignore[import-outside-top-level]

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
        from weblate.addons.models import Addon  # ruff: ignore[import-outside-top-level]
        from weblate.addons.webhooks import WebhookAddon  # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Report  # ruff: ignore[import-outside-top-level]

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
        from django.utils import timezone  # ruff: ignore[import-outside-top-level]

        from weblate.trans.models import Alert  # ruff: ignore[import-outside-top-level]

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
        from types import SimpleNamespace  # ruff: ignore[import-outside-top-level]

        from django.template.loader import render_to_string  # ruff: ignore[import-outside-top-level]

        from weblate.accounts.notifications import LicenseNotification  # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Project  # ruff: ignore[import-outside-top-level]

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
        from django.urls import reverse  # ruff: ignore[import-outside-top-level]

        from weblate.accounts.visibility import filter_contributor_changes  # ruff: ignore[import-outside-top-level]
        from weblate.auth.data import SELECTION_MANUAL  # ruff: ignore[import-outside-top-level]
        from weblate.auth.models import Group, TeamMembership  # ruff: ignore[import-outside-top-level]

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

        from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

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
