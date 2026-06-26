# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for translation views."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest import TestCase
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from weblate.addons.resx import ResxUpdateAddon
from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, UserBlock, setup_project_groups
from weblate.checks.models import Check
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import (
    Change,
    Comment,
    Component,
    Project,
    Suggestion,
    Translation,
    Unit,
)
from weblate.trans.templatetags.translations import unit_state_title
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.util import join_plural
from weblate.trans.views.edit import (
    append_unique_ids,
    cleanup_session,
    format_newly_failing_checks_message,
    get_search_session_snapshot,
)
from weblate.utils.docs import get_doc_url
from weblate.utils.hash import calculate_hash, hash_to_checksum
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_NEEDS_CHECKING,
    STATE_NEEDS_REWRITING,
    STATE_TRANSLATED,
)
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.utils.views import get_sort_name

if TYPE_CHECKING:
    from weblate.checks.base import BaseCheck


class SearchSessionTest(TestCase):
    def test_cleanup_session_removes_malformed_entries(self) -> None:
        session = {
            "search_valid": {"ttl": int(time.time()) + 60},
            "search_expired": {"ttl": int(time.time()) - 60},
            "search_missing_ttl": {},
            "search_invalid_ttl": {"ttl": "invalid"},
            "unrelated": {"ttl": "invalid"},
        }

        cleanup_session(session)

        self.assertIn("search_valid", session)
        self.assertIn("unrelated", session)
        self.assertNotIn("search_expired", session)
        self.assertNotIn("search_missing_ttl", session)
        self.assertNotIn("search_invalid_ttl", session)

    def test_search_session_snapshot_handles_full_and_partial_windows(self) -> None:
        full_snapshot = get_search_session_snapshot({"ids": [1, 2, 3]}, -1, 1)

        self.assertIsNotNone(full_snapshot)
        if full_snapshot is None:
            self.fail("Expected full search snapshot")
        self.assertEqual(full_snapshot.ids, [3])
        self.assertEqual(full_snapshot.offset, 3)
        self.assertEqual(full_snapshot.total, 3)

        partial_snapshot = get_search_session_snapshot(
            {"partial_ids": [10, 11], "partial_offset": 3}, 4, 1
        )

        self.assertIsNotNone(partial_snapshot)
        if partial_snapshot is None:
            self.fail("Expected partial search snapshot")
        self.assertEqual(partial_snapshot.ids, [11])
        self.assertEqual(partial_snapshot.offset, 4)
        self.assertIsNone(partial_snapshot.total)
        self.assertIsNone(
            get_search_session_snapshot(
                {"partial_ids": [10, 11], "partial_offset": 3}, 2, 1
            )
        )
        self.assertIsNone(get_search_session_snapshot({"ids": [1, 2, 3]}, 5, 1))

    def test_search_session_snapshot_rejects_malformed_ids(self) -> None:
        self.assertIsNone(get_search_session_snapshot({"ids": ["invalid"]}, 1, 1))
        self.assertIsNone(
            get_search_session_snapshot(
                {"partial_ids": "invalid", "partial_offset": 1}, 1, 1
            )
        )

    def test_append_unique_ids_preserves_order(self) -> None:
        self.assertEqual(append_unique_ids([1, 2], [2, 3, 1, 4]), [1, 2, 3, 4])


class EditScreenshotContextTest(ViewTestCase):
    def test_screenshot_context_has_documentation_link(self) -> None:
        self.make_manager()
        response = self.client.get(self.translation.get_translate_url())
        self.assertContains(
            response, get_doc_url("admin/translating", "screenshots", user=self.user)
        )

    def test_screenshot_context_deduplicates_source_and_unit_links(self) -> None:
        self.make_manager()
        unit = self.get_unit()
        screenshot = Screenshot.objects.create(
            name="Shared screenshot",
            image="screenshots/test.png",
            translation=unit.source_unit.translation,
            user=self.user,
        )
        screenshot.units.add(unit.source_unit, unit)

        response = self.client.get(unit.get_absolute_url())

        self.assertEqual(list(response.context["screenshots"]), [screenshot])


class EditTest(ViewTestCase):
    """Test for manipulating translation."""

    has_plurals = True
    source = "Hello, world!\n"
    target = "Nazdar svete!\n"
    second_target = "Ahoj svete!\n"
    already_translated = 0
    needs_bilingual_context = False
    new_source_string = "Source string" * 100000

    def setUp(self) -> None:
        super().setUp()
        self.translate_url = reverse("translate", kwargs=self.kw_translation)

    def test_edit(self) -> None:
        response = self.edit_unit(self.source, self.target)
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 2)
        unit = self.get_unit(source=self.source)
        self.assertEqual(unit.target, self.target)
        self.assertEqual(len(unit.all_checks), 0)
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assert_backend(self.already_translated + 1)

        # Test that second edit with no change does not break anything
        response = self.edit_unit(self.source, self.target)
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 2)
        unit = self.get_unit(source=self.source)
        self.assertEqual(unit.target, self.target)
        self.assertEqual(len(unit.all_checks), 0)
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assert_backend(self.already_translated + 1)

        # Test that third edit still works
        response = self.edit_unit(self.source, self.second_target)
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 2)
        unit = self.get_unit(source=self.source)
        self.assertEqual(unit.target, self.second_target)
        self.assertEqual(len(unit.all_checks), 0)
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assert_backend(self.already_translated + 1)

    def test_plurals(self) -> None:
        """Test plural editing."""
        if not self.has_plurals:
            return

        response = self.edit_unit(
            "Orangutan",
            "Opice má %d banán.\n",
            target_1="Opice má %d banány.\n",
            target_2="Opice má %d banánů.\n",
        )
        # We should get to next message
        self.assert_redirects_offset(response, self.translate_url, 3)
        # Check translations
        unit = self.get_unit("Orangutan")
        plurals = unit.get_target_plurals()
        self.assertEqual(len(plurals), 3)
        self.assertEqual(plurals[0], "Opice má %d banán.\n")
        self.assertEqual(plurals[1], "Opice má %d banány.\n")
        self.assertEqual(plurals[2], "Opice má %d banánů.\n")

    def test_fuzzy(self) -> None:
        """Test for fuzzy flag handling."""
        unit = self.get_unit(source=self.source)
        self.assertNotEqual(unit.state, STATE_FUZZY)

        self.edit_unit(self.source, self.target, fuzzy="yes", review="10")
        unit = self.get_unit(source=self.source)
        self.assertEqual(unit.state, STATE_FUZZY)
        self.assertEqual(unit.target, self.target)
        self.assertFalse(unit.has_failing_check)

        self.edit_unit(self.source, self.target)
        unit = self.get_unit(source=self.source)
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assertEqual(unit.target, self.target)
        self.assertFalse(unit.has_failing_check)

        self.edit_unit(self.source, self.target, fuzzy="yes")
        unit = self.get_unit(source=self.source)
        self.assertEqual(unit.state, STATE_FUZZY)
        self.assertEqual(unit.target, self.target)
        self.assertFalse(unit.has_failing_check)

        # Should not have was translated check
        self.edit_unit(self.source, "")
        unit = self.get_unit(source=self.source)
        self.assertFalse(unit.has_failing_check)

        self.change_unit(self.target, source=self.source, state=STATE_NEEDS_CHECKING)
        self.edit_unit(self.source, self.target, fuzzy="yes")
        unit = self.get_unit(source=self.source)
        self.assertEqual(unit.state, STATE_NEEDS_CHECKING)

        self.change_unit(self.target, source=self.source, state=STATE_NEEDS_REWRITING)
        self.edit_unit(self.source, self.target, fuzzy="yes")
        unit = self.get_unit(source=self.source)
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

    def test_fuzzy_with_review(self) -> None:
        self.project.translation_review = True
        self.project.save()
        self.make_manager()

        unit = self.get_unit(source=self.source)
        self.assertNotEqual(unit.state, STATE_FUZZY)
        self.change_unit(self.target, source=self.source, state=STATE_NEEDS_CHECKING)

        self.edit_unit(self.source, self.target, review=str(STATE_NEEDS_CHECKING))
        unit = self.get_unit(source=self.source)
        self.assertEqual(unit.state, STATE_NEEDS_CHECKING)

    def test_approved_state_visible_without_edit_permission(self) -> None:
        self.project.translation_review = True
        self.project.save()
        unit = self.change_unit(self.target, source=self.source, state=STATE_APPROVED)

        self.assertFalse(self.user.has_perm("unit.edit", unit))

        response = self.client.get(unit.get_absolute_url())

        form = response.context["form"]
        self.assertTrue(form.fields["fuzzy"].widget.is_hidden)
        self.assertFalse(form.fields["review"].widget.is_hidden)
        self.assertTrue(form.fields["review"].disabled)
        self.assertEqual(
            [choice[0] for choice in form.fields["review"].choices],
            [STATE_APPROVED],
        )
        self.assertContains(response, "Approved")
        self.assertNotContains(response, "fuzzy_checkbox")

    def add_unit(self, key, force_source: bool = False):
        if force_source or self.component.has_template():
            args = {"context": key, "source_0": self.new_source_string}
            language = "en"
        else:
            args = {"source_0": key, "target_0": "Translation string"}
            if self.needs_bilingual_context:
                args["context"] = key * 2
            language = "cs"
        return self.client.post(
            reverse(
                "new-unit",
                kwargs={
                    "path": [self.component.project.slug, self.component.slug, language]
                },
            ),
            args,
            follow=True,
        )

    def test_new_unit(self) -> None:
        # No permissions
        response = self.add_unit("key")
        self.assertEqual(response.status_code, 403)

        self.make_manager()

        # No adding
        self.component.manage_units = False
        self.component.save()
        response = self.add_unit("key")
        self.assertEqual(response.status_code, 403)

        # Adding allowed (if format supports that)
        self.component.manage_units = True
        self.component.save()
        response = self.add_unit("key")
        if not self.component.file_format_cls.can_add_unit:
            self.assertEqual(response.status_code, 403)
            return
        self.assertContains(response, "New string has been added")

        # Duplicate string
        response = self.add_unit("key")
        self.assertContains(response, "This string seems to already exist.")

        # Invalid params
        response = self.add_unit("")
        self.assertContains(response, "Error in parameter ")

        # Adding on source in bilingual
        if (
            not self.component.has_template()
            and self.component.file_format_cls.can_add_unit
        ):
            start = Unit.objects.count()
            response = self.add_unit("Test string", force_source=True)
            self.assertContains(response, "New string has been added")
            self.assertEqual(
                start + self.component.translation_set.count(),
                Unit.objects.count(),
            )

        # Make sure writing out pending units works
        self.component.commit_pending("test", None)

    def test_edit_new_unit(self) -> None:
        if (
            not self.component.has_template()
            or not self.component.file_format_cls.can_add_unit
        ):
            self.skipTest("Not supported")

        test_target = "TEST TRANSLATION"

        def check_translated() -> None:
            self.assertTrue(
                Unit.objects.filter(
                    translation__language__code="cs",
                    source=self.new_source_string,
                    target=test_target,
                    state=STATE_TRANSLATED,
                ).exists()
            )

        self.make_manager()

        # Add string
        self.component.manage_units = True
        self.component.save()
        response = self.add_unit("key")
        self.assertContains(response, "New string has been added")

        # Edit translation
        self.edit_unit(self.new_source_string, test_target)
        check_translated()

        # Make sure writing out pending units works
        self.component.commit_pending("test", None)
        check_translated()

    def add_plural_unit(self, args=None, language="en"):
        if args is None:
            args = {
                "context": "test-plural",
                "source_0": "%(count)s test",
                "source_1": "%(count)s tests",
            }

        return self.client.post(
            reverse(
                "new-unit",
                kwargs={
                    "path": [self.component.project.slug, self.component.slug, language]
                },
            ),
            args,
            follow=True,
        )

    def test_new_plural_unit(self, args=None, language="en") -> None:
        """Test the implementation of adding a new plural unit."""
        response = self.add_plural_unit(args, language)
        self.assertEqual(response.status_code, 403)

        self.make_manager()

        self.component.manage_units = False
        self.component.save()
        response = self.add_plural_unit(args, language)
        self.assertEqual(response.status_code, 403)

        self.component.manage_units = True
        self.component.save()
        response = self.add_plural_unit(args, language)
        if not self.component.file_format_cls.can_add_unit:
            self.assertEqual(response.status_code, 403)
            return
        if not self.component.file_format_cls.supports_plural:
            self.assertContains(
                response, "Plurals are not supported by the file format"
            )
            return
        self.assertContains(response, "New string has been added")

        # Duplicate string
        response = self.add_plural_unit(args)
        self.assertContains(response, "This string seems to already exist.")

        self.component.commit_pending("test", None)

    def test_bilingual_new_plural_unit(self) -> None:
        """Test the implementation of adding a bilingual new plural unit."""
        if (
            not self.component.has_template()
            and self.component.file_format_cls.can_add_unit
        ):
            args = {
                "context": "new-bilingual-plural-unit",
                "source_0": "%(count)s word",
                "source_1": "%(count)s words",
                "target_0": "%(count)s slovo",
                "target_1": "%(count)s slova",
                "target_2": "%(count)s slov",
            }

            self.test_new_plural_unit(args, language="cs")
        else:
            self.skipTest("Not supported")

    def test_dismiss_automatically_translated(self) -> None:
        """Test dismissing automatically translated flag."""
        unit = self.get_unit(self.source)
        unit.automatically_translated = True
        unit.save(update_fields=["automatically_translated"])

        response = self.client.post(
            reverse("js-dismiss-automatically-translated", kwargs={"unit_id": unit.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/json")

        unit = self.get_unit(self.source)
        self.assertFalse(unit.automatically_translated)

    def test_dismiss_automatically_translated_no_permission(self) -> None:
        """Test dismissing automatically translated without permission."""
        unit = self.get_unit(self.source)
        unit.automatically_translated = True
        unit.save(update_fields=["automatically_translated"])

        # Remove edit permission
        self.user.groups.clear()

        response = self.client.post(
            reverse("js-dismiss-automatically-translated", kwargs={"unit_id": unit.id})
        )
        self.assertEqual(response.status_code, 403)

        unit = self.get_unit(self.source)
        self.assertTrue(unit.automatically_translated)

    def test_dismiss_automatically_translated_not_authenticated(self) -> None:
        """Test dismissing automatically translated without authentication."""
        unit = self.get_unit(self.source)
        unit.automatically_translated = True
        unit.save(update_fields=["automatically_translated"])

        self.client.logout()

        response = self.client.post(
            reverse("js-dismiss-automatically-translated", kwargs={"unit_id": unit.id})
        )
        self.assertEqual(response.status_code, 302)

        unit = self.get_unit(self.source)
        self.assertTrue(unit.automatically_translated)


class EditAccessTest(ViewTestCase):
    def assert_unit_action_urls_not_found(self, unit: Unit) -> None:
        check = Check.objects.create(unit=unit, name="same")

        urls = (
            reverse("js-dismiss-automatically-translated", kwargs={"unit_id": unit.pk}),
            reverse("delete-unit", kwargs={"unit_id": unit.source_unit.pk}),
            reverse("js-ignore-check", kwargs={"check_id": check.pk}),
            reverse("js-ignore-check-source", kwargs={"check_id": check.pk}),
        )
        for url in urls:
            response = self.client.post(url)
            self.assertEqual(response.status_code, 404)

    def test_private_unit_actions_return_not_found(self) -> None:
        private_project = self.create_project(
            name="Private edit",
            slug="private-edit",
            access_control=Project.ACCESS_PRIVATE,
        )
        private_component = self.create_po(project=private_project, name="private-edit")
        private_translation = private_component.translation_set.get(language_code="cs")
        unit = self.get_unit("Hello, world!\n", translation=private_translation)

        self.assert_unit_action_urls_not_found(unit)

    def test_blocked_project_unit_actions_return_not_found(self) -> None:
        group = Group.objects.create(
            name="All projects edit", project_selection=SELECTION_ALL
        )
        self.user.groups.add(group)
        private_project = self.create_project(
            name="Blocked edit",
            slug="blocked-edit",
            access_control=Project.ACCESS_PRIVATE,
        )
        private_component = self.create_po(project=private_project, name="blocked-edit")
        private_translation = private_component.translation_set.get(language_code="cs")
        unit = self.get_unit("Hello, world!\n", translation=private_translation)
        UserBlock.objects.create(user=self.user, project=private_project)
        self.user.clear_cache()

        self.assert_unit_action_urls_not_found(unit)


class EditValidationTest(ViewTestCase):
    def edit(self, **kwargs):
        """Editing with no specific params."""
        unit = self.get_unit()
        params = {"checksum": unit.checksum}
        params.update(kwargs)
        return self.client.post(
            unit.translation.get_translate_url(), params, follow=True
        )

    def test_edit_invalid(self) -> None:
        """Editing with invalid params."""
        response = self.edit()
        self.assertContains(response, "This field is required.")

    def test_suggest_invalid(self) -> None:
        """Suggesting with invalid params."""
        response = self.edit(suggest="1")
        self.assertContains(response, "This field is required.")

    def test_merge(self) -> None:
        """Merging with invalid parameter."""
        unit = self.get_unit()
        response = self.client.post(
            f"{unit.translation.get_translate_url()}?checksum={unit.checksum}",
            {"merge": "invalid"},
            follow=True,
        )
        self.assertContains(response, "Enter a whole number.")

    def test_merge_lang(self) -> None:
        """Merging across languages."""
        unit = self.get_unit()
        trans = self.component.translation_set.exclude(language_code="cs")[0]
        other = trans.unit_set.get(source=unit.source, context=unit.context)
        response = self.client.post(
            f"{unit.translation.get_translate_url()}?checksum={unit.checksum}",
            {"merge": other.pk},
            follow=True,
        )
        self.assertContains(response, "Could not find the merged string.")

    def test_revert(self) -> None:
        unit = self.get_unit()
        # Try the merge
        response = self.client.get(
            unit.translation.get_translate_url(),
            {"checksum": unit.checksum, "revert": "invalid"},
            follow=True,
        )
        self.assertContains(response, "Enter a whole number.")
        # Try the merge
        response = self.client.get(
            unit.translation.get_translate_url(),
            {"checksum": unit.checksum, "revert": -1},
            follow=True,
        )
        self.assertContains(response, "Could not find the reverted change.")


class EditResourceTest(EditTest):
    has_plurals = False

    def create_component(self):
        return self.create_android()

    def test_new_unit_translate(self, commit_translation: bool = False) -> None:
        """Test for translating newly added string, issue #6890."""
        self.make_manager()
        self.component.manage_units = True
        self.component.save()

        # Add new string
        response = self.add_unit("key")
        self.assertContains(response, "New string has been added")
        self.assertEqual(Unit.objects.filter(pending_changes__isnull=False).count(), 1)
        self.assertEqual(Unit.objects.filter(context="key").count(), 2)

        # Edit unit
        self.edit_unit(source=self.new_source_string, target="Překlad")
        self.assertEqual(Unit.objects.filter(pending_changes__isnull=False).count(), 2)

        # Commit to the file
        if commit_translation:
            translation = self.get_translation()
            translation.commit_pending("test", None)
        else:
            self.component.commit_pending("test", None)
        self.assertEqual(Unit.objects.filter(pending_changes__isnull=False).count(), 0)
        self.assertEqual(Unit.objects.filter(context="key").count(), 2)
        self.assertEqual(
            Unit.objects.filter(context="key", state=STATE_TRANSLATED).count(), 2
        )
        self.component.create_translations_immediate(force=True)
        self.assertEqual(
            Unit.objects.filter(context="key", state=STATE_TRANSLATED).count(), 2
        )

    def test_new_unit_translate_commit_translation(
        self, commit_translation=False
    ) -> None:
        self.test_new_unit_translate(commit_translation=True)


class EditResxTest(EditTest):
    has_plurals = False

    def create_component(self):
        component = self.create_resx()
        ResxUpdateAddon.create(component=component)
        return component


class EditLanguageTest(EditTest):
    """Language wide editing tests."""

    def setUp(self) -> None:
        super().setUp()
        self.translate_url = reverse(
            "translate",
            kwargs={"path": [self.project.slug, "-", "cs"]},
        )

    # pylint: disable=arguments-differ
    def edit_unit(self, source, target, language="cs", **kwargs):
        """Do edit single unit using web interface."""
        unit = self.get_unit(source, language)
        params = {
            "checksum": unit.checksum,
            "contentsum": hash_to_checksum(unit.content_hash),
            "translationsum": hash_to_checksum(unit.get_target_hash()),
            "target_0": target,
            "review": "20",
        }
        params.update(kwargs)
        return self.client.post(self.translate_url, params)


class EditResourceSourceTest(ViewTestCase):
    """Source strings (template) editing."""

    has_plurals = False

    def test_edit(self) -> None:
        translate_url = reverse(
            "translate",
            kwargs={"path": self.component.source_translation.get_url_path()},
        )

        response = self.edit_unit("Hello, world!\n", "Nazdar svete!\n", "en")
        # We should get to second message
        self.assert_redirects_offset(response, translate_url, 2)
        unit = self.get_unit("Nazdar svete!\n", "en")
        self.assertEqual(unit.target, "Nazdar svete!\n")
        self.assertEqual(len(unit.all_checks), 0)
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assert_backend(4, "en")

    def test_edit_does_not_rebuild_component_language_stats(self) -> None:
        self.assertGreater(self.get_translation().stats.all, 0)
        with patch(
            "weblate.trans.models.component.Component.invalidate_cache",
            autospec=True,
        ) as invalidate_cache:
            self.edit_unit("Hello, world!\n", "Nazdar svete!\n", "en")
        invalidate_cache.assert_not_called()

    def test_suppress_cache_invalidation_is_reentrant(self) -> None:
        translation = self.get_translation()
        with patch(
            "weblate.trans.models.translation.transaction.on_commit"
        ) as on_commit:
            with translation.suppress_cache_invalidation():
                translation.invalidate_cache()
                with translation.suppress_cache_invalidation():
                    translation.invalidate_cache()
                translation.invalidate_cache()
                on_commit.assert_not_called()

            translation.invalidate_cache()
            translation.invalidate_cache()

        on_commit.assert_called_once()

    def test_source_edit_updates_translation_and_component_stats(self) -> None:
        translation = self.get_translation()
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", "cs")
        translation = Translation.objects.get(pk=translation.pk)
        component = Component.objects.get(pk=self.component.pk)
        unit_before = translation.unit_set.get(context="hello")
        all_chars_before = translation.stats.all_chars
        all_words_before = translation.stats.all_words
        translated_before = translation.stats.translated
        component_all_chars_before = component.stats.all_chars

        with self.captureOnCommitCallbacks(execute=True):
            self.edit_unit("Hello, world!\n", "Hello, universe!\n", "en")

        translation = Translation.objects.get(pk=translation.pk)
        component = Component.objects.get(pk=self.component.pk)
        unit_after = translation.unit_set.get(context="hello")
        all_chars_delta = len(unit_after.source) - len(unit_before.source)
        all_words_delta = unit_after.num_words - unit_before.num_words

        self.assertEqual(
            translation.stats.all_chars,
            all_chars_before + all_chars_delta,
        )
        self.assertEqual(
            translation.stats.all_words,
            all_words_before + all_words_delta,
        )
        self.assertEqual(translation.stats.translated, translated_before - 1)
        self.assertNotEqual(component.stats.all_chars, component_all_chars_before)
        self.assertEqual(
            component.stats.all_chars,
            sum(
                child.stats.all_chars
                for child in Component.objects.get(
                    pk=self.component.pk
                ).translation_set.all()
            ),
        )

    def test_source_edit_falls_back_to_full_recompute_on_nonlocal_checks(self) -> None:
        def fake_run_checks(unit, *args, **kwargs) -> None:
            unit.translation.require_full_stats_rebuild()

        with (
            patch(
                "weblate.trans.models.unit.Unit.run_checks",
                autospec=True,
                side_effect=fake_run_checks,
            ),
            patch(
                "weblate.trans.models.component.Component.invalidate_cache",
                autospec=True,
            ) as invalidate_cache,
        ):
            self.edit_unit("Hello, world!\n", "Nazdar svete!\n", "en")

        invalidate_cache.assert_called()

    def test_edit_revert(self) -> None:
        translation = self.get_translation()
        # Edit translation
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", "cs")

        unit = translation.unit_set.get(context="hello")
        self.assertEqual(unit.state, STATE_TRANSLATED)

        # Edit source
        self.edit_unit("Hello, world!\n", "Hello, universe!\n", "en")

        unit = translation.unit_set.get(context="hello")
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

        # Revert source
        self.edit_unit("Hello, universe!\n", "Hello, world!\n", "en")

        unit = translation.unit_set.get(context="hello")
        self.assertEqual(unit.state, STATE_TRANSLATED)

    def test_needs_edit(self) -> None:
        translation = self.get_translation()

        # Edit translation
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", "cs")

        # Change state
        self.edit_unit("Hello, world!\n", "Hello, world!\n", "en", fuzzy="yes")
        unit = translation.unit_set.get(context="hello")
        self.assertEqual(unit.state, STATE_TRANSLATED)

        # Change state and source
        self.edit_unit("Hello, world!\n", "Hello, universe!\n", "en", fuzzy="yes")
        unit = translation.unit_set.get(context="hello")
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

        # Change state and source
        self.edit_unit("Hello, universe!\n", "Hello, universe!\n", "en")
        unit = translation.unit_set.get(context="hello")
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

        # Revert source
        self.edit_unit("Hello, universe!\n", "Hello, world!\n", "en")
        unit = translation.unit_set.get(context="hello")
        self.assertEqual(unit.state, STATE_TRANSLATED)

    def create_component(self):
        return self.create_android()


class EditBranchTest(EditTest):
    def create_component(self):
        return self.create_po_branch()


class EditMercurialTest(EditTest):
    def create_component(self):
        return self.create_po_mercurial()


class EditPoMonoTest(EditTest):
    def create_component(self):
        return self.create_po_mono()

    def test_remove_unit(self) -> None:
        self.assertEqual(self.component.stats.all, 16)
        unit_count = Unit.objects.count()
        unit = self.get_unit()
        # Deleting translation unit
        response = self.client.post(reverse("delete-unit", kwargs={"unit_id": unit.pk}))
        self.assertEqual(response.status_code, 403)
        # Lack of permissions
        response = self.client.post(
            reverse("delete-unit", kwargs={"unit_id": unit.source_unit.pk})
        )
        self.assertEqual(response.status_code, 403)
        # Make superuser
        self.user.is_superuser = True
        self.user.save()
        # Deleting translation unit
        response = self.client.post(reverse("delete-unit", kwargs={"unit_id": unit.pk}))
        self.assertEqual(response.status_code, 403)
        # Actual removal
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("delete-unit", kwargs={"unit_id": unit.source_unit.pk}),
                data={"next": f"{self.translate_url}?offset=3"},
            )
        self.assertEqual(response.status_code, 302)
        self.assert_redirects_offset(response, self.translate_url, 3)
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.stats.all, 12)
        self.assertEqual(unit_count - 4, Unit.objects.count())

    def test_remove_unit_locked(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        unit = self.get_unit().source_unit

        with patch(
            "weblate.trans.models.translation.Translation.delete_unit",
            side_effect=WeblateLockTimeoutError(
                "repository locked",
                lock=SimpleNamespace(scope="repository", origin="test/component"),
            ),
        ):
            response = self.client.post(
                reverse("delete-unit", kwargs={"unit_id": unit.pk}),
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Could not remove the string because another background operation is in progress. Please try again later.",
        )


class EditIphoneTest(EditTest):
    has_plurals = False

    def create_component(self):
        return self.create_iphone()


class EditJSONTest(EditTest):
    has_plurals = False

    def create_component(self):
        return self.create_json()


class EditJoomlaTest(EditTest):
    has_plurals = False

    def create_component(self):
        return self.create_joomla()


class EditRubyYAMLTest(EditTest):
    def create_component(self):
        return self.create_ruby_yaml()

    def test_new_unit_hierarchical_context_validation(self) -> None:
        self.make_manager()
        self.component.manage_units = True
        self.component.save()

        response = self.add_unit("weblate")
        self.assertContains(
            response, "This key conflicts with an existing hierarchical key."
        )

        response = self.add_unit("weblate->hello->title")
        self.assertContains(
            response, "This key conflicts with an existing hierarchical key."
        )


class EditDTDTest(EditTest):
    has_plurals = False

    def create_component(self):
        return self.create_dtd()


class EditJSONMonoTest(EditTest):
    has_plurals = False
    new_source_string = "Source string"

    def create_component(self):
        return self.create_json_mono()

    def enable_nested_unit_management(self) -> None:
        self.component.manage_units = True
        self.component.file_format = "json-nested"
        self.component.drop_file_format_cache()
        # These tests only need the changed settings to be visible to the view.
        # Avoid Component.save(), which rescans the repository as a side effect.
        Component.objects.filter(pk=self.component.pk).update(
            file_format=self.component.file_format,
            manage_units=self.component.manage_units,
        )

    def test_new_unit_validation(self) -> None:
        self.make_manager()
        self.enable_nested_unit_management()
        response = self.add_unit("key")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New string has been added")

    def test_new_unit_validation_flat_format_does_not_load_store(self) -> None:
        self.translation.__dict__.pop("store", None)

        with patch.object(
            self.translation,
            "load_store",
            side_effect=AssertionError("store should not be loaded"),
        ):
            self.translation.validate_new_unit_data(
                "flat.key",
                ["Added source string"],
                ["Added target string"],
            )

    def test_new_unit_validation_parse_error(self) -> None:
        self.make_manager()
        self.enable_nested_unit_management()

        with patch.object(
            Translation,
            "load_store",
            side_effect=FileParseError("Broken JSON"),
        ):
            response = self.add_unit("test.key")

        self.assertContains(response, "Could not parse translation file: Broken JSON")

    def test_new_unit_validation_materializes_pending_contexts(self) -> None:
        self.enable_nested_unit_management()
        store = self.translation.store

        with patch.object(store, "validate_new_context") as validate_new_context:
            self.translation.validate_new_unit_data(
                "test.key",
                ["Added source string"],
                ["Added target string"],
            )

        self.assertIsInstance(
            validate_new_context.call_args.kwargs["pending_contexts"], list
        )

    def test_add_unit_revalidates_hierarchical_context(self) -> None:
        self.enable_nested_unit_management()
        translation = self.component.source_translation

        translation.add_unit(
            None,
            "test.key",
            ["Added source string"],
            "",
            author=self.user,
        )

        with self.assertRaisesMessage(
            ValidationError, "This key conflicts with an existing hierarchical key."
        ):
            translation.add_unit(
                None,
                "test.key.title",
                ["Other source string"],
                "",
                author=self.user,
            )

    def test_new_unit_hierarchical_context_validation(self) -> None:
        self.make_manager()
        self.enable_nested_unit_management()

        response = self.add_unit("test.key")
        self.assertContains(response, "New string has been added")

        response = self.add_unit("test.key.title")
        self.assertContains(
            response, "This key conflicts with an existing hierarchical key."
        )

        response = self.add_unit("other.key.title")
        self.assertContains(response, "New string has been added")


class EditJavaTest(EditTest):
    has_plurals = False
    already_translated = 1

    def create_component(self):
        return self.create_java()

    def test_untranslate(self) -> None:
        translation = self.get_translation()

        # Edit translation
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", "cs")
        self.component.commit_pending("test", None)
        self.assertEqual(translation.unit_set.filter(state=STATE_TRANSLATED).count(), 1)

        # Untranslate
        self.edit_unit("Hello, world!\n", "", "cs")
        self.assertEqual(translation.unit_set.filter(state=STATE_TRANSLATED).count(), 0)
        self.component.commit_pending("test", None)
        self.assertEqual(translation.unit_set.filter(state=STATE_TRANSLATED).count(), 0)


class EditAppStoreTest(EditTest):
    has_plurals = False
    source = "Weblate - continuous localization"
    target = "Weblate - průběžná lokalizace"
    second_target = "Weblate - průběžný překlad"
    already_translated = 2

    def create_component(self):
        return self.create_appstore()


class EditXliffComplexTest(EditTest):
    has_plurals = False
    needs_bilingual_context = True

    def create_component(self):
        return self.create_xliff("complex")

    def test_invalid_xml(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar & svete!\n")
        self.assert_backend(1)


class EditXliffResnameTest(EditTest):
    has_plurals = False
    needs_bilingual_context = True

    def create_component(self):
        return self.create_xliff("only-resname")


class EditXliffTest(EditTest):
    has_plurals = False
    needs_bilingual_context = True

    def create_component(self):
        return self.create_xliff()


class EditXliffMonoTest(EditTest):
    has_plurals = False

    def create_component(self):
        return self.create_xliff_mono()


class EditLinkTest(EditTest):
    def create_component(self):
        return self.create_link()


class EditPropagateTest(EditTest):
    def create_component(self):
        result = super().create_component()
        self._create_component(
            "po", "second-po/*.po", name="Second", project=result.project
        )
        return result

    def test_edit_restricted_component(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])

        response = self.edit_unit(self.source, self.target)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.get_unit(source=self.source).target, "")

    def test_edit_skips_restricted_propagated_component(self) -> None:
        second_translation = Translation.objects.get(
            component__slug="second", language_code="cs"
        )
        second_component = second_translation.component
        self.component.allow_translation_propagation = True
        self.component.save(update_fields=["allow_translation_propagation"])
        second_component.allow_translation_propagation = True
        second_component.restricted = True
        second_component.save(
            update_fields=["allow_translation_propagation", "restricted"]
        )

        self.assertFalse(self.user.has_perm("unit.edit", second_translation))

        self.edit_unit(self.source, self.target)

        self.assertEqual(self.get_unit(source=self.source).target, self.target)
        self.assertEqual(
            self.get_unit(source=self.source, translation=second_translation).target, ""
        )
        self.assertFalse(
            Change.objects.filter(
                component=second_component, action=ActionEvents.PROPAGATED_EDIT
            ).exists()
        )

    def test_edit(self) -> None:
        def get_targets() -> list[str]:
            return list(
                Unit.objects.filter(
                    source=self.source, translation__language_code="cs"
                ).values_list("target", flat=True)
            )

        # String should not be translated now
        self.assertEqual(get_targets(), ["", ""])

        super().test_edit()

        # Verify that propagation worked well
        self.assertEqual(get_targets(), [self.second_target, self.second_target])

        second_translation = Translation.objects.get(
            component__slug="second", language_code="cs"
        )

        # Verify second component backend
        self.assert_backend(1, translation=second_translation)

        # Force rescan
        components = Component.objects.all()
        for component in components:
            component.do_file_scan()

        # Verify that propagated units survived scan
        self.assertEqual(get_targets(), [self.second_target, self.second_target])

        # Verify that changes were properly generated
        for unit in Unit.objects.filter(
            source=self.source, translation__language_code="cs"
        ):
            self.assertEqual(
                unit.change_set.filter(action=ActionEvents.NEW_UNIT_REPO).count(),
                1,
            )
            self.assertEqual(
                unit.change_set.filter(action=ActionEvents.STRING_REPO_UPDATE).count(),
                0,
            )
            if unit.translation.component.slug == "second":
                self.assertEqual(
                    unit.change_set.filter(action=ActionEvents.PROPAGATED_EDIT).count(),
                    2,
                )
            else:
                self.assertEqual(
                    unit.change_set.filter(action=ActionEvents.NEW).count(), 1
                )
                self.assertEqual(
                    unit.change_set.filter(action=ActionEvents.CHANGE).count(),
                    1,
                )

        # Bring strins out of sync
        unit = self.get_unit()
        test_edit = "Test edit\n"
        unit.translate(
            None,
            test_edit,
            STATE_TRANSLATED,
            change_action=ActionEvents.AUTO,
            propagate=False,
        )
        self.assertEqual(set(get_targets()), {self.second_target, test_edit})
        self.assertEqual(
            {"inconsistent"}, set(unit.check_set.values_list("name", flat=True))
        )

        # Resync them
        unit.translate(
            None,
            self.second_target,
            STATE_TRANSLATED,
            change_action=ActionEvents.AUTO,
            propagate=False,
        )
        self.assertEqual(set(get_targets()), {self.second_target})
        self.assertEqual(set(), set(unit.check_set.values_list("name", flat=True)))


class EditTSTest(EditTest):
    def create_component(self):
        return self.create_ts()


class EditTSMonoTest(EditTest):
    has_plurals = False

    def create_component(self):
        return self.create_ts_mono()


class ZenViewTest(ViewTestCase):
    def create_zen_unit(self, position: int) -> Unit:
        source = f"Zen source {position}\n"
        id_hash = calculate_hash(source, "")
        source_unit = Unit(
            translation=self.component.source_translation,
            id_hash=id_hash,
            source=source,
            target=source,
            state=STATE_TRANSLATED,
            original_state=STATE_TRANSLATED,
            position=position,
        )
        source_unit.save(run_checks=False)
        unit = Unit(
            translation=self.translation,
            id_hash=id_hash,
            source=source,
            target=f"Zen target {position}\n",
            state=STATE_TRANSLATED,
            original_state=STATE_TRANSLATED,
            position=position,
            source_unit=source_unit,
        )
        unit.save(run_checks=False)
        return unit

    def test_zen(self) -> None:
        response = self.client.get(reverse("zen", kwargs=self.kw_translation))
        self.assertContains(response, "Thank you for using Weblate.")
        self.assertContains(response, "Orangutan has %d bananas")
        self.assertContains(response, "The translation has come to an end.")

    def test_zen_invalid(self) -> None:
        response = self.client.get(
            reverse("zen", kwargs=self.kw_translation),
            {"q": "has:nonexisting"},
            follow=True,
        )
        self.assertContains(response, "Unsupported lookup for has: nonexisting")

    def test_load_zen(self) -> None:
        response = self.client.get(reverse("load_zen", kwargs=self.kw_translation))
        self.assertContains(response, "Thank you for using Weblate.")
        self.assertContains(response, "Orangutan has %d bananas")
        self.assertContains(response, "The translation has come to an end.")

    def test_load_zen_offset(self) -> None:
        response = self.client.get(
            reverse("load_zen", kwargs=self.kw_translation),
            {"offset": "2"},
        )
        self.assertNotContains(response, "Hello, world")
        self.assertContains(response, "Orangutan has %d bananas")
        response = self.client.get(
            reverse("load_zen", kwargs=self.kw_translation),
            {"offset": "bug"},
        )
        self.assertContains(response, "Hello, world")

    def test_load_zen_deep_offset(self) -> None:
        for position in range(5, 27):
            self.create_zen_unit(position)

        response = self.client.get(
            reverse("load_zen", kwargs=self.kw_translation),
            {"offset": "21"},
        )

        self.assertNotContains(response, "Hello, world")
        self.assertContains(response, "Zen source 21")
        self.assertContains(response, "Zen source 26")
        self.assertContains(response, "The translation has come to an end.")

    def test_zen_stores_full_search_ids(self) -> None:
        for position in range(5, 27):
            self.create_zen_unit(position)

        response = self.client.get(reverse("zen", kwargs=self.kw_translation))

        session = self.client.session
        session_keys = list(session.keys())
        search_key = next(key for key in session_keys if key.startswith("search_"))
        self.assertEqual(response.context["filter_count"], 26)
        self.assertEqual(len(session[search_key]["ids"]), 26)

    def test_zen_skips_glossary_fetch_without_glossaries(self) -> None:
        with patch("weblate.trans.views.edit.fetch_glossary_terms") as fetch_terms:
            self.client.get(reverse("zen", kwargs=self.kw_translation))

        fetch_terms.assert_not_called()

    def test_save_zen(self) -> None:
        unit = self.get_unit()
        params = {
            "checksum": unit.checksum,
            "contentsum": hash_to_checksum(unit.content_hash),
            "translationsum": hash_to_checksum(unit.get_target_hash()),
            "target_0": "Zen translation",
            "review": "20",
        }
        response = self.client.post(
            reverse("save_zen", kwargs=self.kw_translation),
            params,
        )
        self.assertContains(
            response,
            "The following fix-up was applied to the translation: Trailing and leading whitespace",
        )

    def test_save_zen_lock(self) -> None:
        self.component.locked = True
        self.component.save()
        unit = self.get_unit()
        params = {
            "checksum": unit.checksum,
            "contentsum": hash_to_checksum(unit.content_hash),
            "translationsum": hash_to_checksum(unit.get_target_hash()),
            "target_0": "Zen translation",
            "review": "20",
        }
        response = self.client.post(
            reverse("save_zen", kwargs=self.kw_translation),
            params,
        )
        self.assertContains(
            response, "Insufficient privileges for saving translations."
        )

    def test_browse(self) -> None:
        response = self.client.get(reverse("browse", kwargs=self.kw_translation))
        self.assertContains(response, "Thank you for using Weblate.")
        self.assertContains(
            response,
            'Orangutan has <span class="hlcheck" data-value="%d"><span class="highlight-number"></span>%d</span> banana.',
        )


class EditComplexTest(ViewTestCase):
    """Test for complex manipulating translation."""

    def setUp(self) -> None:
        super().setUp()
        self.translation = self.get_translation()
        self.translate_url = reverse("translate", kwargs=self.kw_translation)

    def test_add_duplicate_plural(self) -> None:
        self.component.manage_units = True
        self.component.save()
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("new-unit", kwargs=self.kw_translation),
            {
                "source_0": "Hello, world!\n",
                "source_1": "Hello, worlds!\n",
                "target_0": "Ahoj světe!\n",
                "target_1": "Ahoj světy!\n",
                "target_2": "Ahoj světy!\n",
            },
            follow=True,
        )
        self.assertContains(response, "This string seems to already exist.")
        response = self.client.post(
            reverse("new-unit", kwargs=self.kw_translation),
            {
                "source_0": "Hello, %d world!\n",
                "source_1": "Hello, %d worlds!\n",
                "target_0": "Ahoj %d světe!\n",
                "target_1": "Ahoj %d světy!\n",
                "target_2": "Ahoj %d světy!\n",
            },
            follow=True,
        )
        self.assertNotContains(response, "This string seems to already exist.")

    def test_merge(self) -> None:
        # Translate unit to have something to start with
        response = self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        unit = self.get_unit()
        # Try the merge
        response = self.client.post(
            f"{self.translate_url}?checksum={unit.checksum}", {"merge": unit.id}
        )
        self.assert_backend(1)
        # We should stay on same message
        self.assert_redirects_offset(response, self.translate_url, unit.position + 1)

        # Test error handling
        unit2 = self.translation.unit_set.get(source="Thank you for using Weblate.")
        response = self.client.post(
            f"{self.translate_url}?checksum={unit.checksum}", {"merge": unit2.id}
        )
        self.assertContains(response, "Could not find the merged string.")

    def test_merge_inconsistent(self) -> None:
        # Translate unit to have something to start with
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        units = Unit.objects.filter(
            translation__language__code="cs", source="Hello, world!\n"
        )
        self.assertEqual(
            set(units.values_list("target", flat=True)), {"Nazdar svete!\n"}
        )
        self.create_link_existing()
        self.assertEqual(
            set(units.values_list("target", flat=True)), {"Nazdar svete!\n", ""}
        )
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, {"inconsistent"})
        self.client.post(
            f"{self.translate_url}?checksum={unit.checksum}", {"merge": unit.id}
        )
        self.assertEqual(
            set(units.values_list("target", flat=True)), {"Nazdar svete!\n"}
        )
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, set())

    def test_edit_propagated(self) -> None:
        units = Unit.objects.filter(
            translation__language__code="cs", source="Thank you for using Weblate."
        )
        self.create_link_existing()
        self.assertEqual(set(units.values_list("target", flat=True)), {""})
        self.edit_unit("Thank you for using Weblate.", "Díky za použití Weblate")
        self.assertEqual(
            set(units.values_list("target", flat=True)), {"Díky za použití Weblate"}
        )
        self.assertEqual(
            [unit.all_checks_names for unit in units.iterator()],
            [{"end_stop"}, {"end_stop"}],
        )
        self.edit_unit("Thank you for using Weblate.", "Díky za použití Weblate.")
        self.assertEqual(
            set(units.values_list("target", flat=True)), {"Díky za použití Weblate."}
        )
        self.assertEqual(
            [unit.all_checks_names for unit in units.iterator()], [set(), set()]
        )

    def test_revert(self) -> None:
        source = "Hello, world!\n"
        target = "Nazdar svete!\n"
        target_2 = "Hei maailma!\n"
        self.edit_unit(source, target)
        # Ensure other edit gets different timestamp
        time.sleep(1)
        self.edit_unit(source, target_2)
        unit = self.get_unit()
        changes = Change.objects.content().filter(unit=unit).order()
        self.assertEqual(changes[1].target, target)
        self.assertEqual(changes[0].target, target_2)
        self.assert_backend(1)
        # revert it
        self.client.get(
            self.translate_url, {"checksum": unit.checksum, "revert": changes[1].id}
        )
        unit = self.get_unit()
        self.assertEqual(unit.target, "")
        self.assertEqual(unit.state, STATE_EMPTY)
        # check that we cannot revert to string from another translation
        self.edit_unit("Thank you for using Weblate.", "Kiitoksia Weblaten kaytosta.")
        unit2 = self.get_unit(source="Thank you for using Weblate.")
        change = unit2.change_set.order()[0]
        response = self.client.get(
            self.translate_url, {"checksum": unit.checksum, "revert": change.id}
        )
        self.assertContains(response, "Could not find the reverted change.")
        self.assert_backend(1)

    def test_revert_history_after_component_move_uses_current_translate_url(
        self,
    ) -> None:
        second_project = Project.objects.create(
            name="Second project",
            slug="second-project",
            web="https://weblate.org/",
        )
        setup_project_groups(Project, second_project, created=False)
        second_project.add_user(self.user, "Administration")

        self.component.project = second_project
        self.component.save()
        self.component.refresh_from_db()
        self.translation.refresh_from_db()

        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        unit = self.get_unit(translation=self.translation)
        change = Change.objects.content().filter(unit=unit).order()[0]
        translate_url = ProjectLanguage(
            second_project,
            self.translation.language,
        ).get_translate_url()

        response = self.client.get(translate_url, {"checksum": unit.checksum})

        self.assertContains(
            response,
            f'href="{translate_url}?checksum={unit.checksum}&amp;revert={change.id}"',
        )

    def test_translate_get_search_uses_lightweight_state(self) -> None:
        Check.objects.all().delete()
        unit = self.get_unit(source="Thank you for using Weblate.")
        Check.objects.get_or_create(unit=unit, name="end_stop")

        response = self.client.get(self.translate_url, {"q": "has:check"})

        self.assertEqual(response.context["unit"].pk, unit.pk)
        self.assertEqual(response.context["filter_count"], 1)
        session = self.client.session
        session_keys = session.keys()
        search_key = next(key for key in session_keys if key.startswith("search_"))
        self.assertNotIn("ids", session[search_key])
        self.assertEqual(session[search_key]["last_viewed_unit_id"], unit.pk)

    def test_translate_checksum_search_stores_full_ids(self) -> None:
        unit = self.get_unit(source="Thank you for using Weblate.")

        self.client.get(self.translate_url, {"checksum": unit.checksum, "offset": 1})

        session = self.client.session
        session_keys = session.keys()
        search_key = next(key for key in session_keys if key.startswith("search_"))
        self.assertIn("ids", session[search_key])
        self.assertIn(unit.pk, session[search_key]["ids"])

    def test_translate_post_converts_full_search_session_to_partial(self) -> None:
        unit = self.get_unit()

        self.client.get(self.translate_url, {"checksum": unit.checksum, "offset": 1})
        session = self.client.session
        session_keys = session.keys()
        search_key = next(key for key in session_keys if key.startswith("search_"))
        self.assertIn("ids", session[search_key])

        params = {
            "checksum": unit.checksum,
            "contentsum": hash_to_checksum(unit.content_hash),
            "translationsum": hash_to_checksum(unit.get_target_hash()),
            "target_0": "Translated first string",
            "review": "20",
        }
        response = self.client.post(f"{self.translate_url}?offset=1", params)

        self.assert_redirects_offset(response, self.translate_url, 2)
        session = self.client.session
        session_data = session[search_key]
        self.assertNotIn("ids", session_data)
        self.assertEqual(session_data["partial_offset"], 1)
        self.assertEqual(session_data["partial_ids"][0], unit.pk)

    def test_translate_filtered_search_keeps_stable_navigation(self) -> None:
        first = self.get_unit()

        response = self.client.get(self.translate_url, {"q": "state:<translated"})
        self.assertEqual(response.context["unit"].pk, first.pk)

        params = {
            "checksum": first.checksum,
            "contentsum": hash_to_checksum(first.content_hash),
            "translationsum": hash_to_checksum(first.get_target_hash()),
            "target_0": "Translated first string",
            "review": "20",
        }
        response = self.client.post(
            f"{self.translate_url}?q=state:%3Ctranslated&offset=1",
            params,
        )
        self.assert_redirects_offset(response, self.translate_url, 2)

        session = self.client.session
        session_keys = session.keys()
        search_key = next(key for key in session_keys if key.startswith("search_"))
        expected_unit_id = session[search_key]["partial_ids"][1]
        self.assertNotIn("ids", session[search_key])

        response = self.client.get(
            self.translate_url, {"q": "state:<translated", "offset": 2}
        )
        self.assertEqual(response.context["unit"].pk, expected_unit_id)

    def test_translate_post_offset_uses_limited_search_lookup(self) -> None:
        response = self.client.get(self.translate_url, {"offset": 1})
        unit = response.context["unit"]
        self.assertContains(
            response, f'name="checksum" value="{unit.checksum}"', html=False
        )
        params = {
            "checksum": unit.checksum,
            "contentsum": hash_to_checksum(unit.content_hash),
            "translationsum": hash_to_checksum(unit.get_target_hash()),
            "target_0": "Translated first string",
            "review": "20",
        }

        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(f"{self.translate_url}?offset=1", params)

        self.assert_redirects_offset(response, self.translate_url, 2)
        unit_id_searches = [
            query["sql"]
            for query in queries
            if '"trans_unit"."id" AS "id"' in query["sql"]
            and 'FROM "trans_unit"' in query["sql"]
            and "ORDER BY" in query["sql"]
        ]
        self.assertTrue(
            any("LIMIT 2" in sql for sql in unit_id_searches),
            "\n".join(query["sql"] for query in queries),
        )
        self.assertFalse(
            any("LIMIT" not in sql for sql in unit_id_searches),
            "\n".join(query["sql"] for query in queries),
        )

    def test_translate_consecutive_filtered_post_uses_partial_search_lookup(
        self,
    ) -> None:
        def get_targets(unit: Unit) -> dict[str, str]:
            replacements = {
                "Hello": "Hi",
                "Orangutan": "Monkey",
                "Weblate": "Software",
            }
            targets = {}
            sources = unit.get_source_plurals()
            plural_count = unit.translation.plural.number if unit.is_plural else 1
            for position in range(plural_count):
                source = sources[min(position, len(sources) - 1)]
                target = source
                for old, new in replacements.items():
                    target = target.replace(old, new)
                if target == source:
                    target = f"Translated {source}"
                targets[f"target_{position}"] = target
            return targets

        response = self.client.get(
            self.translate_url, {"q": "state:<translated", "offset": 2}
        )
        first = response.context["unit"]

        params = {
            "checksum": first.checksum,
            "contentsum": hash_to_checksum(first.content_hash),
            "translationsum": hash_to_checksum(first.get_target_hash()),
            "review": "20",
        }
        params.update(get_targets(first))
        response = self.client.post(
            f"{self.translate_url}?q=state:%3Ctranslated&offset=2", params
        )
        self.assert_redirects_offset(response, self.translate_url, 3)

        session = self.client.session
        session_keys = session.keys()
        search_key = next(key for key in session_keys if key.startswith("search_"))
        second = Unit.objects.get(pk=session[search_key]["partial_ids"][1])
        params = {
            "checksum": second.checksum,
            "contentsum": hash_to_checksum(second.content_hash),
            "translationsum": hash_to_checksum(second.get_target_hash()),
            "review": "20",
        }
        params.update(get_targets(second))

        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(
                f"{self.translate_url}?q=state:%3Ctranslated&offset=3", params
            )

        self.assert_redirects_offset(response, self.translate_url, 4)
        unit_id_searches = [
            query["sql"]
            for query in queries
            if '"trans_unit"."id" AS "id"' in query["sql"]
            and 'FROM "trans_unit"' in query["sql"]
            and "ORDER BY" in query["sql"]
        ]
        self.assertTrue(
            any("LIMIT" in sql for sql in unit_id_searches),
            "\n".join(query["sql"] for query in queries),
        )
        self.assertFalse(
            any("LIMIT" not in sql for sql in unit_id_searches),
            "\n".join(query["sql"] for query in queries),
        )
        session = self.client.session
        self.assertNotIn("ids", session[search_key])
        self.assertGreaterEqual(len(session[search_key]["partial_ids"]), 3)

    def test_translate_partial_total_keeps_cached_unit_after_filter_removal(
        self,
    ) -> None:
        unit = self.get_unit()
        suggestion = Suggestion.objects.create(
            unit=unit,
            user=self.user,
            target="Suggested",
        )

        response = self.client.get(self.translate_url, {"q": "has:suggestion"})
        self.assertEqual(response.context["unit"].pk, unit.pk)
        self.assertEqual(response.context["filter_count"], 1)

        response = self.client.post(
            f"{self.translate_url}?q=has:suggestion&offset=1",
            {"checksum": unit.checksum, "delete": suggestion.pk},
        )

        self.assert_redirects_offset(response, self.translate_url, 1)
        response = self.client.get(
            self.translate_url, {"q": "has:suggestion", "offset": 1}
        )
        self.assertEqual(response.context["unit"].pk, unit.pk)
        self.assertEqual(response.context["filter_count"], 1)

    def test_nearby_embed_prefetches_state_relations(self) -> None:
        unit = self.get_unit(source="Thank you for using Weblate.")
        Check.objects.get_or_create(unit=unit, name="end_stop")
        Comment.objects.create(unit=unit, user=self.user, comment="Needs work")
        Suggestion.objects.create(unit=unit, user=self.user, target="Suggested")

        nearby = unit.nearby(1)
        nearby_unit = next(item for item in nearby if item.pk == unit.pk)

        with self.assertNumQueries(0):
            self.assertTrue(nearby_unit.active_checks)
            self.assertTrue(nearby_unit.has_comment)
            self.assertTrue(nearby_unit.has_suggestion)
            self.assertIn("Failing checks:", unit_state_title(nearby_unit))

    def test_translate_keeps_addterm_form_behind_project_permission(self) -> None:
        self.create_po(
            name="Glossary",
            project=self.project,
            is_glossary=True,
            manage_units=True,
        )
        user_class = type(self.user)
        has_perm = user_class.has_perm

        def has_project_glossary_permission(user, permission, obj=None):
            if permission == "glossary.add":
                return False
            return has_perm(user, permission, obj)

        with (
            patch.object(
                user_class,
                "has_perm",
                autospec=True,
                side_effect=has_project_glossary_permission,
            ),
            patch("weblate.trans.views.edit.TermForm") as term_form,
        ):
            response = self.client.get(self.translate_url)

        term_form.assert_not_called()
        self.assertIsNone(response.context["addterm_form"])
        self.assertNotContains(response, "Add term to glossary")

    def test_translate_addterm_form_uses_addable_glossary(self) -> None:
        self.make_manager()
        self.create_po(
            name="Glossary",
            project=self.project,
            is_glossary=True,
            manage_units=True,
        )

        response = self.client.get(self.translate_url)

        self.assertIsNotNone(response.context["addterm_form"])
        self.assertContains(response, "Add term to glossary")

    def test_translate_source_language_renders_glossary_term_once(self) -> None:
        glossary = self.create_po(
            name="Glossary",
            project=self.project,
            is_glossary=True,
            manage_units=True,
        )
        glossary.source_translation.unit_set.create(
            source="Hello",
            target="Hello",
            context="",
            id_hash=calculate_hash("Hello", ""),
            position=glossary.source_translation.unit_set.count() + 1,
            state=STATE_TRANSLATED,
        )
        glossary.invalidate_glossary_cache()

        response = self.client.get(
            self.component.source_translation.get_translate_url()
        )

        self.assertEqual(response.context["glossary"][0].source, "Hello")
        self.assertTrue(response.context["glossary"][0].is_source)
        content = response.content.decode()
        glossary_start = content.index('<tbody id="glossary-terms">')
        glossary_end = content.index("</tbody>", glossary_start)
        glossary_body = content[glossary_start:glossary_end]
        self.assertIn('class="source target" colspan="2"', glossary_body)
        self.assertIn("Hello", glossary_body)
        self.assertNotIn('class="source">', glossary_body)
        self.assertNotIn('class="target">', glossary_body)

    def test_translate_skips_glossary_fetch_without_glossaries(self) -> None:
        with patch("weblate.trans.views.edit.fetch_glossary_terms") as fetch_terms:
            response = self.client.get(self.translate_url)

        fetch_terms.assert_not_called()
        self.assertEqual(response.context["glossary"], [])

    def test_project_language_warns_when_switching_component(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(priority=120)
        high_component = self.create_po(name="High", priority=80, project=self.project)
        high_translation = high_component.translation_set.get(
            language=self.translation.language
        )
        translate_url = ProjectLanguage(
            self.project, self.translation.language
        ).get_translate_url()
        high_component_offset = high_translation.unit_set.count()

        response = self.client.get(translate_url, {"offset": high_component_offset})
        self.assertNotContains(response, "You have shifted from")
        self.assertContains(response, 'value="component,-priority"')

        response = self.client.get(translate_url, {"offset": high_component_offset + 1})
        self.assertContains(response, "You have shifted from")

    def test_language_scope_sort_defaults_to_component_priority(self) -> None:
        request = SimpleNamespace(GET={})
        category = self.create_category(self.project)

        self.assertEqual(
            get_sort_name(
                request, ProjectLanguage(self.project, self.translation.language)
            )["query"],
            "component,-priority",
        )
        self.assertEqual(
            get_sort_name(
                request, CategoryLanguage(category, self.translation.language)
            )["query"],
            "component,-priority",
        )

    def test_project_language_get_search_uses_lightweight_state(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(priority=120)
        self.create_po(name="High", locked=True, priority=80, project=self.project)
        translate_url = ProjectLanguage(
            self.project, self.translation.language
        ).get_translate_url()

        self.client.get(translate_url, {"sort_by": "component,-priority", "offset": 1})

        session = self.client.session
        session_keys = session.keys()
        search_key = next(key for key in session_keys if key.startswith("search_"))
        self.assertNotIn("ids", session[search_key])
        self.assertIn("last_viewed_unit_id", session[search_key])

    def test_project_language_checksum_search_keeps_component_order(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(priority=120)
        high_component = self.create_po(
            name="High", locked=True, priority=80, project=self.project
        )
        high_translation = high_component.translation_set.get(
            language=self.translation.language
        )
        translate_url = ProjectLanguage(
            self.project, self.translation.language
        ).get_translate_url()
        unit = high_translation.unit_set.order_by("position")[0]

        self.client.get(
            translate_url,
            {
                "sort_by": "component,-priority",
                "checksum": unit.checksum,
            },
        )

        session = self.client.session
        session_keys = session.keys()
        search_key = next(key for key in session_keys if key.startswith("search_"))
        expected_ids = [
            *self.translation.unit_set.order_by("position").values_list(
                "pk", flat=True
            ),
            *high_translation.unit_set.order_by("position").values_list(
                "pk", flat=True
            ),
        ]
        self.assertEqual(session[search_key]["ids"], expected_ids)

    def test_project_language_ignores_stale_component_shift_unit(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(priority=120)
        high_component = self.create_po(name="High", priority=80, project=self.project)
        high_translation = high_component.translation_set.get(
            language=self.translation.language
        )
        translate_url = ProjectLanguage(
            self.project, self.translation.language
        ).get_translate_url()
        high_component_offset = high_translation.unit_set.count()

        response = self.client.get(translate_url, {"offset": high_component_offset})
        self.assertEqual(response.status_code, 200)

        last_unit_id = Unit.objects.order_by("-pk").values_list("pk", flat=True)[0]
        stale_unit_id = last_unit_id + 1
        session = self.client.session
        session_keys = session.keys()
        search_key = next(key for key in session_keys if key.startswith("search_"))
        session_result = session[search_key]
        session_result["last_viewed_unit_id"] = stale_unit_id
        session[search_key] = session_result
        session.save()

        response = self.client.get(translate_url, {"offset": high_component_offset + 1})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "You have shifted from")
        self.assertNotEqual(
            self.client.session[search_key]["last_viewed_unit_id"], stale_unit_id
        )

    def test_revert_plural(self) -> None:
        source = "Orangutan has %d banana.\n"
        target = [
            "Opice má %d banán.\n",
            "Opice má %d banány.\n",
            "Opice má %d banánů.\n",
        ]
        target_2 = [
            "Orangutan má %d banán.\n",
            "Orangutan má %d banány.\n",
            "Orangutan má %d banánů.\n",
        ]
        self.edit_unit(source, target[0], target_1=target[1], target_2=target[2])
        # Ensure other edit gets different timestamp
        time.sleep(1)
        self.edit_unit(source, target_2[0], target_1=target_2[1], target_2=target_2[2])
        unit = self.get_unit(source)
        changes = Change.objects.content().filter(unit=unit).order()
        self.assertEqual(changes[1].target, join_plural(target))
        self.assertEqual(changes[0].target, join_plural(target_2))
        self.assert_backend(1)
        # revert it
        self.client.get(
            self.translate_url, {"checksum": unit.checksum, "revert": changes[0].id}
        )
        unit = self.get_unit(source)
        self.assertEqual(unit.get_target_plurals(), target)

    def test_revert_empty(self) -> None:
        source = "Hello, world!\n"
        target = "Nazdar svete!\n"
        self.edit_unit(source, target)
        unit = self.get_unit(source)
        change = Change.objects.content().filter(unit=unit).order()[0]

        self.client.get(
            self.translate_url, {"checksum": unit.checksum, "revert": change.id}
        )

        unit = self.get_unit(source)
        self.assertEqual(unit.target, "")
        self.assertEqual(unit.state, STATE_EMPTY)

    def test_revert_invalid_old_state(self) -> None:
        source = "Hello, world!\n"
        target = "Nazdar svete!\n"
        self.edit_unit(source, target)
        unit = self.get_unit(source)
        change = Change.objects.content().filter(unit=unit).order()[0]
        change.details["old_state"] = -1
        change.save(update_fields=["details"])

        self.assertFalse(change.can_revert())
        self.assertIsNone(change.get_revert_state())
        self.assertFalse(change.revert(self.user))

        response = self.client.get(
            self.translate_url,
            {"checksum": unit.checksum, "revert": change.id},
            follow=True,
        )

        self.assertContains(response, "Could not find the reverted change.")
        unit.refresh_from_db()
        self.assertEqual(unit.target, target)
        self.assertEqual(unit.state, STATE_TRANSLATED)

    def test_revert_restores_old_state(self) -> None:
        source = "Hello, world!\n"
        original = "Nazdar svete!\n"
        updated = "Hei maailma!\n"
        self.change_unit(original, source=source, state=STATE_NEEDS_REWRITING)
        self.edit_unit(source, updated)
        unit = self.get_unit(source)
        change = Change.objects.content().filter(unit=unit).order()[0]

        self.client.get(
            self.translate_url, {"checksum": unit.checksum, "revert": change.id}
        )

        unit = self.get_unit(source)
        self.assertEqual(unit.target, original)
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

    def test_edit_fixup(self) -> None:
        # Save with failing check
        response = self.edit_unit("Hello, world!\n", "Nazdar svete!")
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 2)
        unit = self.get_unit()
        self.assertEqual(unit.target, "Nazdar svete!\n")
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.all_checks), 0)
        self.assertEqual(len(unit.active_checks), 0)
        self.assertEqual(unit.translation.stats.allchecks, 0)
        self.assert_backend(1)

    def test_edit_check(self) -> None:
        # Save with failing check
        response = self.edit_unit("Hello, world!\n", "Hello, world!\n")
        # We should stay on current message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, "Hello, world!\n")
        self.assertTrue(unit.has_failing_check)
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assertEqual(len(unit.all_checks), 1)
        self.assertEqual(len(unit.active_checks), 1)
        self.assertEqual(unit.translation.stats.allchecks, 1)

        # Ignore check
        check_id = unit.active_checks[0].id
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("js-ignore-check", kwargs={"check_id": check_id})
            )
        self.assertContains(response, "ok")

        # Should have one less failing check
        unit = self.get_unit()
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.all_checks), 1)
        self.assertEqual(len(unit.active_checks), 0)
        self.assertEqual(unit.translation.stats.allchecks, 0)

        # Ignore check for all languages
        check_obj = Check.objects.get(pk=int(check_id)).check_obj
        self.assertIsNotNone(check_obj)
        ignore_flag = cast("BaseCheck", check_obj).ignore_string
        ignore_url = reverse("js-ignore-check-source", kwargs={"check_id": check_id})
        response = self.client.post(ignore_url)
        self.assertEqual(response.status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(ignore_url)
        self.assertEqual(response.headers["Content-Type"], "application/json")

        # Should have one less check
        unit = self.get_unit()
        self.assertJSONEqual(
            response.content.decode("utf-8"),
            {
                "extra_flags": ignore_flag,
                "all_flags": unit.all_flags.format(),
                "ignore_check": ignore_flag,
            },
        )
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.all_checks), 0)
        self.assertEqual(len(unit.active_checks), 0)
        self.assertEqual(unit.translation.stats.allchecks, 0)

        # Save with no failing checks
        response = self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        # We should stay on current message
        self.assert_redirects_offset(response, self.translate_url, 2)
        unit = self.get_unit()
        self.assertEqual(unit.target, "Nazdar svete!\n")
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.all_checks), 0)
        self.assertEqual(unit.translation.stats.allchecks, 0)
        self.assert_backend(1)

    def test_newly_failing_checks_message_pluralization_and_order(self) -> None:
        self.assertEqual(
            format_newly_failing_checks_message({"end_newline"}),
            "The translation has been saved, however there is a newly failing "
            "check: Trailing newline",
        )
        self.assertEqual(
            format_newly_failing_checks_message({"end_newline", "same"}),
            "The translation has been saved, however there are some newly "
            "failing checks: Trailing newline, Unchanged translation",
        )

    def test_enforced_check(self) -> None:
        # Enforce same check
        self.component.enforced_checks = ["same"]
        self.component.save(update_fields=["enforced_checks"])
        # Save with failing check
        response = self.edit_unit("Hello, world!\n", "Hello, world!\n")
        # We should stay on current message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, "Hello, world!\n")
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)
        self.assertTrue(unit.has_failing_check)
        self.assertEqual(len(unit.all_checks), 1)
        self.assertEqual(len(unit.active_checks), 1)
        self.assertEqual(unit.translation.stats.allchecks, 1)
        # There should be a change for enforced check
        self.assertTrue(
            unit.change_set.filter(action=ActionEvents.ENFORCED_CHECK).exists()
        )
        # The pending change should be only fuzzy
        pending_changes = unit.pending_changes.all()
        self.assertEqual(len(pending_changes), 1)
        self.assertEqual(pending_changes[0].state, STATE_NEEDS_REWRITING)

    def test_enforced_check_noop(self) -> None:
        # Update unit object to match edits in test_enforced_check
        unit = self.get_unit()
        unit.state = STATE_TRANSLATED
        unit.target = "Hello, world!\n"
        unit.save_backend(None)
        unit.pending_changes.all().delete()

        # Enforce same check, the unit should become fuzzy with pending change
        self.component.enforced_checks = ["same"]
        self.component.save(update_fields=["enforced_checks"])
        self.assertEqual(unit.pending_changes.count(), 1)
        unit = self.get_unit()
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

        # Remove pending units and make the string in the database translated
        unit.pending_changes.all().delete()
        Unit.objects.filter(pk=unit.pk).update(state=STATE_TRANSLATED)

        # Now test the actual no-op edit
        self.test_enforced_check()

    def test_commit_push(self) -> None:
        response = self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 2)
        self.assertTrue(self.translation.needs_commit())
        self.assertTrue(self.component.needs_commit())
        self.assertTrue(self.component.project.needs_commit())

        self.translation.commit_pending("test", self.user)

        self.assertFalse(self.translation.needs_commit())
        self.assertFalse(self.component.needs_commit())
        self.assertFalse(self.component.project.needs_commit())

        self.assertTrue(self.translation.repo_needs_push())
        self.assertTrue(self.component.repo_needs_push())
        self.assertTrue(self.component.project.repo_needs_push())

        self.translation.do_push(self.get_request())

        self.assertFalse(self.translation.repo_needs_push())
        self.assertFalse(self.component.repo_needs_push())
        self.assertFalse(self.component.project.repo_needs_push())

    def test_edit_locked(self) -> None:
        self.component.locked = True
        self.component.save()
        response = self.edit_unit("Hello, world!\n", "Nazdar svete!\n", follow=True)
        # We should get to second message
        self.assertContains(
            response,
            "The translation is temporarily closed for contributions due "
            "to maintenance, please come back later.",
        )
        self.assert_backend(0)

    def test_edit_changed_source(self) -> None:
        # We use invalid contentsum here
        response = self.edit_unit(
            "Hello, world!\n", "Nazdar svete!\n", contentsum="aaa"
        )
        # We should get an error message
        self.assertContains(response, "The source string has changed meanwhile.")
        self.assert_backend(0)

    def test_edit_changed_translation(self) -> None:
        # We use invalid translationsum here
        response = self.edit_unit(
            "Hello, world!\n", "Nazdar svete!\n", translationsum="aaa"
        )
        # We should get an error message
        self.assertContains(
            response, "The translation of the string has changed meanwhile."
        )
        self.assert_backend(0)

    def test_edit_view(self) -> None:
        url = self.get_unit("Hello, world!\n").get_absolute_url()
        response = self.client.get(url)
        form = response.context["form"]
        params = {field: form[field].value() for field in form.fields}
        params["target_0"] = "Nazdar svete!\n"
        self.client.post(url, params)
        unit = self.get_unit()
        self.assertEqual(unit.target, "Nazdar svete!\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assert_backend(1)

    def test_remove_unit(self) -> None:
        self.component.manage_units = True
        self.component.save()
        self.user.is_superuser = True
        self.user.save()

        unit_count = Unit.objects.count()
        unit = self.get_unit()
        source_unit = unit.source_unit
        all_units = source_unit.unit_set.exclude(pk__in=[unit.pk, source_unit.pk])
        # Delete all other units
        for i, other in enumerate(all_units):
            response = self.client.post(
                reverse("delete-unit", kwargs={"unit_id": other.pk})
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(unit_count - 1 - i, Unit.objects.count())
        # Deleting translation unit
        response = self.client.post(reverse("delete-unit", kwargs={"unit_id": unit.pk}))
        self.assertEqual(response.status_code, 302)

        # The source unit should be now removed as well
        self.assertFalse(Unit.objects.filter(pk=source_unit.pk).exists())
        self.assertEqual(unit_count - 4, Unit.objects.count())

    def test_remove_source_unit(self) -> None:
        self.component.manage_units = True
        self.component.save()
        self.user.is_superuser = True
        self.user.save()

        unit_count = Unit.objects.count()
        unit = self.get_unit()
        source_unit = unit.source_unit

        response = self.client.post(
            reverse("delete-unit", kwargs={"unit_id": source_unit.pk})
        )
        self.assertEqual(response.status_code, 302)

        # The source unit should be now removed as well
        self.assertFalse(Unit.objects.filter(pk=source_unit.pk).exists())
        self.assertEqual(unit_count - 4, Unit.objects.count())

        # Verify that reparsing will not bring the unit back
        self.component.create_translations_immediate(force=True)
        self.assertFalse(Unit.objects.filter(pk=source_unit.pk).exists())
        self.assertEqual(unit_count - 4, Unit.objects.count())

    def test_edit_checks(self) -> None:
        source = "Thank you for using Weblate."
        self.change_unit(
            target="Díky za použití Weblate",
            source=source,
            user=self.anotheruser,
        )
        self.change_unit(
            target="Díky za použití Weblate.",
            source=source,
            user=self.user,
        )
        unit = self.get_unit(source=source)
        self.assertEqual(set(unit.check_set.values_list("name", flat=True)), set())
        self.component.commit_pending("test", None)
        self.assertEqual(set(unit.check_set.values_list("name", flat=True)), set())


class EditSourceTest(ViewTestCase):
    def create_component(self):
        return self.create_ts_mono()

    def test_edit_source_pending(self) -> None:
        old_revision = self.get_translation().revision

        # Edit source string
        self.edit_unit("Hello, world!\n", "Hello, beautiful world!\n", language="en")

        # Force committing source string change
        self.component.commit_pending("test", None)

        # Translation revision should have been updated now
        self.assertNotEqual(old_revision, self.get_translation().revision)

        # Add translation
        self.edit_unit("Hello, beautiful world!\n", "Ahoj, světe!\n", language="cs")

        # Verify it has been stored in the database
        self.assertEqual(
            self.get_unit("Hello, beautiful world!\n", language="cs").target,
            "Ahoj, světe!\n",
        )

        # Check sync should be no-op now
        self.component.create_translations_immediate()

        # Check that translation was preserved
        self.assertEqual(
            self.get_unit("Hello, beautiful world!\n", language="cs").target,
            "Ahoj, světe!\n",
        )


class EditSourceAddonTest(EditSourceTest):
    def create_component(self):
        # This pulls in cleanup add-on
        return self.create_android()
