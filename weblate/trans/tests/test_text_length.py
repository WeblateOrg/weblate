# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the translation text length limit enforced on stored strings."""

from __future__ import annotations

import copy
import pickle  # ruff: ignore[suspicious-pickle-import]
from typing import Any
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.urls import reverse

from weblate.addons.generate import PrefillAddon, PseudolocaleAddon
from weblate.automation.operations import get_operation, validate_result
from weblate.trans.bulk import BulkUnitEdit, bulk_perform
from weblate.trans.models import Change, Component, Suggestion, Unit
from weblate.trans.source_edit import edit_source
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_actor
from weblate.trans.util import join_plural
from weblate.trans.validators import (
    MAX_NEW_TEXT_LENGTH,
    MAX_TRANSLATION_ALTERNATIVES,
    TranslationTextTooLongError,
    get_translation_text_max_length,
    validate_translation_text_length,
)
from weblate.utils.ratelimit import reset_rate_limit
from weblate.utils.state import STATE_EMPTY, STATE_NEEDS_REWRITING, STATE_TRANSLATED

SOURCE = "Hello, world!\n"
OTHER_SOURCE = "Try Weblate at <https://demo.weblate.org/>!\n"
LINKED_SOURCE = "Thank you for using Weblate."


class TranslateTextLengthTest(ViewTestCase):
    def test_rejects_oversized_change(self) -> None:
        unit = self.get_unit(SOURCE)
        limit = get_translation_text_max_length(unit)

        with self.assertRaises(TranslationTextTooLongError):
            unit.translate(self.user, "B" * (limit + 1), STATE_TRANSLATED)

        unit.refresh_from_db()
        self.assertEqual(unit.target, "")

    def test_accepts_change_at_limit(self) -> None:
        unit = self.get_unit(SOURCE)
        limit = get_translation_text_max_length(unit)

        unit.translate(self.user, "B" * limit, STATE_TRANSLATED)

        unit.refresh_from_db()
        self.assertTrue(unit.target.startswith("B" * limit))

    def test_keeps_stored_oversized_text(self) -> None:
        """Text stored from the repository can still change state."""
        unit = self.get_unit(SOURCE)
        oversized = "B" * (get_translation_text_max_length(unit) + 1)
        Unit.objects.filter(pk=unit.pk).update(target=oversized, state=STATE_TRANSLATED)
        unit = Unit.objects.get(pk=unit.pk)

        unit.translate(self.user, unit.get_target_plurals(), STATE_NEEDS_REWRITING)

        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)
        self.assertTrue(unit.target.startswith(oversized))

    def test_error_can_be_copied(self) -> None:
        error = TranslationTextTooLongError()
        restored = pickle.loads(  # ruff: ignore[suspicious-pickle-usage]
            pickle.dumps(error)
        )
        for copied in (copy.copy(error), restored):
            self.assertIsInstance(copied, TranslationTextTooLongError)
            self.assertEqual(copied.messages, error.messages)

    def test_editor_keeps_autofixed_text(self) -> None:
        """Text extended by autofixes can be saved again."""
        unit = self.get_unit(SOURCE)
        limit = get_translation_text_max_length(unit)
        unit.translate(self.user, "B" * limit, STATE_TRANSLATED)
        unit.refresh_from_db()
        # The trailing newline is added by an autofix from the source string
        self.assertEqual(len(unit.target), limit + 1)

        validate_translation_text_length(
            unit, unit.get_target_plurals(), allow_stored=True
        )
        with self.assertRaises(TranslationTextTooLongError):
            validate_translation_text_length(unit, unit.get_target_plurals())

    def enable_source_edit(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        self.component.manage_units = True
        self.component.save(update_fields=["manage_units"])

    def test_source_edit_rejects_oversized_text(self) -> None:
        self.enable_source_edit()
        unit = self.get_unit(SOURCE).source_unit
        oversized = "B" * (MAX_NEW_TEXT_LENGTH + 1)
        cases: tuple[tuple[str, Any], ...] = (
            ("source", [oversized]),
            ("context", oversized),
            ("explanation", oversized),
        )
        for field, value in cases:
            with self.subTest(field):
                with self.assertRaises(ValidationError) as error:
                    edit_source(
                        unit,
                        self.user,
                        content_hash=unit.content_hash,
                        **{field: value},
                    )
                self.assertIn(field, error.exception.message_dict)
        unit.refresh_from_db()
        self.assertEqual(unit.source, SOURCE)
        self.assertEqual(unit.explanation, "")

    def test_source_edit_keeps_stored_text(self) -> None:
        """Other attributes can be edited when the source is stored oversized."""
        self.enable_source_edit()
        unit = self.get_unit(SOURCE).source_unit
        oversized = "B" * (MAX_NEW_TEXT_LENGTH + 1)
        Unit.objects.filter(pk=unit.pk).update(explanation=oversized)
        unit = Unit.objects.get(pk=unit.pk)

        edit_source(unit, self.user, content_hash=unit.content_hash, context="ctx")

        unit.refresh_from_db()
        self.assertEqual(unit.context, "ctx")
        self.assertEqual(unit.explanation, oversized)

    def test_add_unit_rejects_oversized_text(self) -> None:
        translation = self.get_translation()
        count = translation.unit_set.count()
        oversized = "B" * (MAX_NEW_TEXT_LENGTH + 1)
        for name, context, source, target, explanation in (
            ("source", "", oversized, None, ""),
            ("target", "", "new", oversized, ""),
            ("context", oversized, "new", None, ""),
            ("explanation", "", "new", None, oversized),
        ):
            with (
                self.subTest(name),
                self.assertRaises(TranslationTextTooLongError),
            ):
                translation.add_unit(
                    None,
                    context,
                    source,
                    target,
                    explanation=explanation,
                    author=self.user,
                )
        self.assertEqual(translation.unit_set.count(), count)

    def test_add_unit_applies_string_limit(self) -> None:
        """New translations are limited like edits, including the new flags."""
        translation = self.get_translation()
        count = translation.unit_set.count()
        flags = "max-length:5"
        limit = 10 * (5 + 100)
        self.assertLess(limit, MAX_NEW_TEXT_LENGTH)

        with self.assertRaises(TranslationTextTooLongError):
            translation.add_unit(
                None, "", "new", "B" * (limit + 1), extra_flags=flags, author=self.user
            )
        self.assertEqual(translation.unit_set.count(), count)
        self.assertFalse(
            self.component.source_translation.unit_set.filter(source="new").exists()
        )

        unit = translation.add_unit(
            None, "", "new", "B" * limit, extra_flags=flags, author=self.user
        )
        self.assertIsNotNone(unit)

    def test_keeps_stored_text_with_crlf(self) -> None:
        """The editor submits stored CRLF newlines as LF."""
        unit = self.get_unit(SOURCE)
        oversized = "B" * get_translation_text_max_length(unit) + "\r\nB\r\n"
        Unit.objects.filter(pk=unit.pk).update(target=oversized, state=STATE_TRANSLATED)
        unit = Unit.objects.get(pk=unit.pk)

        unit.translate(
            self.user, oversized.replace("\r\n", "\n"), STATE_NEEDS_REWRITING
        )

        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

    def test_prefill_copies_stored_source(self) -> None:
        """Copying stored source text is not limited, generated text is."""
        self.component.check_flags = "max-length:5"
        self.component.save()
        unit = self.get_unit(SOURCE)
        long_source = "B" * (get_translation_text_max_length(unit) + 1)
        assert unit.source_unit_id is not None
        Unit.objects.filter(pk=unit.source_unit_id).update(target=long_source)
        addon = PrefillAddon.create(
            acting_user=get_test_actor(self), component=self.component, run=False
        )

        result = addon.daily_component(self.component)

        self.assertIsNone(result)
        unit.refresh_from_db()
        # Autofixes add the trailing newline of the source string
        self.assertEqual(unit.target, f"{long_source}\n")

    def prepare_bulk_replace(self) -> tuple[Unit, Unit, str]:
        short = self.get_unit(SOURCE)
        long = self.get_unit(OTHER_SOURCE)
        short.translate(self.user, "zz", STATE_TRANSLATED)
        long.translate(self.user, "z", STATE_TRANSLATED)
        # Two replacements exceed the first limit, one fits the second limit.
        replacement = "B" * (get_translation_text_max_length(short) // 2 + 1)
        self.assertLessEqual(len(replacement), get_translation_text_max_length(long))
        return short, long, replacement

    def bulk_replace(
        self,
        units: list[Unit],
        replacement: str,
        too_long: set[int],
        preview: list[BulkUnitEdit] | None = None,
    ) -> int:
        return bulk_perform(
            self.user,
            Unit.objects.filter(pk__in=[unit.pk for unit in units]),
            query="",
            target_state=-1,
            add_flags="",
            remove_flags="",
            add_labels=self.project.label_set.none(),
            remove_labels=self.project.label_set.none(),
            project=self.project,
            enforce_permissions=False,
            components=[self.component],
            search="z",
            replacement=replacement,
            too_long_unit_ids=too_long,
            preview=preview,
        )

    def test_bulk_replace_skips_oversized_result(self) -> None:
        short, long, replacement = self.prepare_bulk_replace()
        too_long: set[int] = set()

        updated = self.bulk_replace([short, long], replacement, too_long)

        self.assertEqual(updated, 1)
        self.assertEqual(too_long, {short.pk})
        short.refresh_from_db()
        long.refresh_from_db()
        # Autofixes add the trailing newline of the source strings
        self.assertEqual(short.target, "zz\n")
        self.assertEqual(long.target, f"{replacement}\n")

    def test_bulk_clear_oversized_alternatives(self) -> None:
        unit = self.get_unit(SOURCE)
        stored = join_plural(["stored"] * (MAX_TRANSLATION_ALTERNATIVES + 1))
        Unit.objects.filter(pk=unit.pk).update(target=stored, state=STATE_TRANSLATED)
        for preview_only in (True, False):
            with self.subTest(preview=preview_only):
                too_long: set[int] = set()
                preview: list[BulkUnitEdit] = []
                with patch.object(Component, "is_multivalue", True):
                    updated = bulk_perform(
                        self.user,
                        Unit.objects.filter(pk=unit.pk),
                        query="",
                        target_state=STATE_EMPTY,
                        add_flags="",
                        remove_flags="",
                        add_labels=self.project.label_set.none(),
                        remove_labels=self.project.label_set.none(),
                        project=self.project,
                        enforce_permissions=False,
                        components=[self.component],
                        too_long_unit_ids=too_long,
                        preview=preview if preview_only else None,
                    )

                self.assertEqual(updated, 1)
                self.assertEqual(too_long, set())
                unit.refresh_from_db()
                if preview_only:
                    self.assertEqual(preview[0].target, [""])
                    self.assertEqual(preview[0].state, STATE_EMPTY)
                    self.assertEqual(unit.target, stored)
                else:
                    self.assertEqual(unit.get_target_plurals(), [""])
                    self.assertEqual(unit.state, STATE_EMPTY)

    def test_bulk_replace_allows_autofix_expansion(self) -> None:
        """Bulk edit accepts what the editor accepts, autofixes can extend it."""
        unit = self.get_unit(SOURCE)
        # Stored without the trailing newline of the source, as from a repository
        Unit.objects.filter(pk=unit.pk).update(target="z", state=STATE_TRANSLATED)
        replacement = "B" * get_translation_text_max_length(unit)
        too_long: set[int] = set()
        preview: list[BulkUnitEdit] = []

        count = self.bulk_replace([unit], replacement, too_long, preview=preview)
        self.assertEqual(count, 1)
        self.assertEqual(preview[0].target, [f"{replacement}\n"])

        updated = self.bulk_replace([unit], replacement, too_long)

        self.assertEqual(updated, 1)
        self.assertEqual(too_long, set())
        unit.refresh_from_db()
        # The trailing newline is added by an autofix from the source string
        self.assertEqual(unit.target, f"{replacement}\n")

    def test_bulk_replace_preview_reports_oversized_result(self) -> None:
        short, long, replacement = self.prepare_bulk_replace()
        too_long: set[int] = set()
        preview: list[BulkUnitEdit] = []

        count = self.bulk_replace([short, long], replacement, too_long, preview=preview)

        self.assertEqual(count, 1)
        self.assertEqual([edit.unit.pk for edit in preview], [long.pk])
        self.assertEqual(too_long, {short.pk})

    def test_bulk_edit_view_reports_oversized_result(self) -> None:
        short, _long, replacement = self.prepare_bulk_replace()
        self.user.is_superuser = True
        self.user.save()
        reset_rate_limit("bulk_edit", user=self.user)

        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {
                "q": f"id:{short.pk}",
                "state": -1,
                "search_type": "text",
                "search": "z",
                "replacement": replacement,
            },
            follow=True,
        )

        self.assertContains(
            response,
            "1 string was left unchanged because the edited text would be too long.",
        )
        short.refresh_from_db()
        self.assertEqual(short.target, "zz\n")

    def test_propagation_skips_stricter_component(self) -> None:
        linked = self.create_link_existing()
        linked.check_flags = "max-length:5"
        linked.save()
        unit = self.get_unit(LINKED_SOURCE)
        other = Unit.objects.get(
            translation__component=linked,
            translation__language_code="cs",
            source=LINKED_SOURCE,
        )
        limit = get_translation_text_max_length(other)
        target = "B" * (limit + 1)
        self.assertLessEqual(len(target), get_translation_text_max_length(unit))

        unit.translate(self.user, target, STATE_TRANSLATED)

        other.refresh_from_db()
        self.assertEqual(other.target, "")
        unit.refresh_from_db()
        self.assertEqual(unit.target, target)

    def test_propagation_allows_autofix_expansion(self) -> None:
        """Peers with the same limit accept text extended by autofixes."""
        linked = self.create_link_existing()
        unit = self.get_unit(SOURCE)
        other = Unit.objects.get(
            translation__component=linked,
            translation__language_code="cs",
            source=SOURCE,
        )
        limit = get_translation_text_max_length(unit)
        self.assertEqual(get_translation_text_max_length(other), limit)

        unit.translate(self.user, "B" * limit, STATE_TRANSLATED)

        other.refresh_from_db()
        # The trailing newline is added by an autofix from the source string
        self.assertEqual(other.target, "B" * limit + "\n")

    def test_propagation_reports_stricter_component(self) -> None:
        linked = self.create_link_existing()
        linked.check_flags = "max-length:5"
        linked.save()
        other = Unit.objects.get(
            translation__component=linked,
            translation__language_code="cs",
            source=LINKED_SOURCE,
        )
        target = "B" * (get_translation_text_max_length(other) + 1)

        response = self.edit_unit(LINKED_SOURCE, target, follow=True)

        self.assertContains(
            response,
            f"String could not be propagated to {linked}: Translation text too long!",
        )
        other.refresh_from_db()
        self.assertEqual(other.target, "")

    def test_revert_to_oversized_text(self) -> None:
        unit = self.get_unit(SOURCE)
        long_text = "B" * 1100
        unit.translate(self.user, long_text, STATE_TRANSLATED)
        unit.translate(self.user, "short", STATE_TRANSLATED)
        change = (
            Change.objects.filter(unit=unit, target__startswith="short")
            .order_by("pk")
            .last()
        )
        assert change is not None
        # The limit is stricter now than when the text was stored
        self.component.check_flags = "max-length:5"
        self.component.save()
        unit = Unit.objects.get(pk=unit.pk)
        self.assertLess(get_translation_text_max_length(unit), len(long_text))

        # Reverting restores text which was already stored
        response = self.client.post(
            unit.translation.get_translate_url(),
            {"checksum": unit.checksum, "revert": change.pk},
            follow=True,
        )
        self.assertNotContains(response, "Translation text too long!")

        unit.refresh_from_db()
        self.assertTrue(unit.target.startswith(long_text))

    def test_accept_oversized_suggestion(self) -> None:
        unit = self.get_unit(SOURCE)
        suggestion, _result = Suggestion.objects.add(
            unit, ["B" * 1100], self.get_request()
        )
        assert suggestion is not None
        self.component.check_flags = "max-length:5"
        self.component.save()
        suggestion = Suggestion.objects.get(pk=suggestion.pk)

        with self.assertRaises(TranslationTextTooLongError):
            suggestion.accept(self.get_request())

        self.assertTrue(Suggestion.objects.filter(pk=suggestion.pk).exists())
        unit.refresh_from_db()
        self.assertEqual(unit.target, "")

    def test_vote_reports_failed_automatic_accept(self) -> None:
        unit = self.get_unit(SOURCE)
        suggestion, _result = Suggestion.objects.add(
            unit, ["B" * 1100], self.get_request()
        )
        assert suggestion is not None
        self.component.check_flags = "max-length:5"
        self.component.suggestion_voting = True
        self.component.suggestion_autoaccept = 1
        self.component.save()
        self.user.is_superuser = True
        self.user.save()
        suggestion = Suggestion.objects.get(pk=suggestion.pk)
        request = self.get_request()

        suggestion.add_vote(request, 1)

        self.assertEqual(
            [str(message) for message in request._messages],  # ruff: ignore[private-member-access]
            [
                (
                    "The suggestion could not be accepted automatically: "
                    "Translation text too long!"
                )
            ],
        )
        self.assertTrue(Suggestion.objects.filter(pk=suggestion.pk).exists())

    def test_pseudolocale_skips_oversized_strings(self) -> None:
        translation = self.get_translation()
        with patch(
            "weblate.trans.validators.get_translation_text_max_length",
            return_value=5,
        ):
            addon = PseudolocaleAddon.create(
                acting_user=get_test_actor(self),
                component=self.component,
                configuration={
                    "source": self.component.source_translation.pk,
                    "target": translation.pk,
                    "prefix": "@@@",
                    "suffix": "!!!",
                },
                run=False,
            )
            # The result is stored in the add-on activity log
            result = addon.daily_component(self.component)
        skipped = translation.unit_set.exclude(state=STATE_TRANSLATED).count()
        self.assertGreater(skipped, 0)
        self.assertEqual(result, {"skipped_too_long": skipped})
        self.assertFalse(translation.unit_set.filter(target__startswith="@@@").exists())

    def test_bulk_edit_automation_result_reports_skipped(self) -> None:
        validate_result(
            get_operation("weblate.bulk_edit"),
            {"component": self.component.pk, "updated": 1, "skipped_too_long": 2},
        )
