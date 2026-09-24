# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from django.db import transaction
from django.urls import reverse

from weblate.auth.models import User
from weblate.checks.flags import Flags
from weblate.trans.actions import ActionEvents
from weblate.trans.bulk import bulk_perform
from weblate.trans.forms import UnitFlagsForm
from weblate.trans.models import Unit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_EMPTY, STATE_FUZZY, STATE_TRANSLATED

if TYPE_CHECKING:
    from django.db.models import Model


class UnitFlagsTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user.is_superuser = True
        self.user.save()
        self.unit = self.get_unit()
        self.source = self.unit.source_unit
        self.url = reverse("edit_context", kwargs={"pk": self.unit.pk})

    def set_flags(self, unit: Unit, flags: str) -> None:
        with transaction.atomic():
            unit.update_extra_flags(flags, self.user)
        unit.refresh_from_db()
        unit.__dict__.pop("all_flags", None)
        unit.store_old_unit(unit)

    def actions(self) -> set[tuple[str, str, str]]:
        unit = Unit.objects.get(pk=self.unit.pk)
        return {
            (action, flag, scope)
            for action, flag, _label, scope in unit.get_flag_actions(self.user)
        }

    def test_readonly_action_matrix_and_promotion(self) -> None:
        self.assertEqual(
            self.actions(),
            {
                ("addflag", "read-only", "source"),
                ("addflag", "read-only", "translation"),
            },
        )
        state = self.unit.state
        self.set_flags(self.unit, "read-only, max-length:10, discard:check-glossary")
        self.assertEqual(
            self.actions(),
            {
                ("removeflag", "read-only", "translation"),
                ("promoteflag", "read-only", "source"),
            },
        )
        response = self.client.post(
            self.url, {"promoteflag": "read-only", "scope": "source"}
        )
        self.assertRedirects(response, self.unit.get_absolute_url())
        self.unit.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual(self.unit.extra_flags, "discard:check-glossary, max-length:10")
        self.assertEqual(self.source.extra_flags, "read-only")
        self.assertTrue(self.unit.readonly)
        self.assertEqual(self.actions(), {("removeflag", "read-only", "source")})
        self.assertTrue(
            self.unit.change_set.filter(
                action=ActionEvents.EXTRA_FLAGS, target=self.unit.extra_flags
            ).exists()
        )
        response = self.client.post(
            self.url, {"removeflag": "read-only", "scope": "source"}
        )
        self.assertRedirects(response, self.unit.get_absolute_url())
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.state, state)

    def test_local_readonly_restores_state_and_leaves_source_unchanged(self) -> None:
        state = self.unit.state
        for action, readonly in (("addflag", True), ("removeflag", False)):
            response = self.client.post(
                self.url, {action: "read-only", "scope": "translation"}
            )
            self.assertEqual(response.status_code, 302)
            self.unit.refresh_from_db()
            self.assertEqual(self.unit.readonly, readonly)
            self.source.refresh_from_db()
            self.assertEqual(self.source.extra_flags, "")
        self.assertEqual(self.unit.state, state)

    def test_source_removal_preserves_local_readonly(self) -> None:
        self.set_flags(self.unit, "read-only")
        self.set_flags(self.source, "read-only")
        self.client.post(self.url, {"removeflag": "read-only", "scope": "source"})
        self.unit.refresh_from_db()
        self.assertTrue(self.unit.readonly)
        self.assertEqual(self.unit.extra_flags, "read-only")

    def test_source_readonly_cannot_be_discarded(self) -> None:
        self.set_flags(self.unit, "discard:read-only, max-length:10")
        self.set_flags(self.source, "read-only, max-length:20")
        unit = Unit.objects.get(pk=self.unit.pk)
        self.assertIn("read-only", unit.all_flags)
        self.assertTrue(unit.readonly)
        self.assertEqual(unit.all_flags.get_value("max-length"), 10)
        self.set_flags(self.source, "max-length:30")
        unit = Unit.objects.get(pk=self.unit.pk)
        self.assertFalse(unit.readonly)
        self.assertEqual(unit.all_flags.get_value("max-length"), 10)

    def test_inheritance_priority_and_clearing_local_override(self) -> None:
        self.set_flags(self.source, "max-length:20, priority:60")
        unit = Unit.objects.get(pk=self.unit.pk)
        self.assertEqual(unit.all_flags.get_value("max-length"), 20)
        self.set_flags(unit, "max-length:10, priority:80")
        self.assertEqual(unit.priority, 80)
        self.assertEqual(unit.all_flags.get_value("max-length"), 10)
        sibling = unit.source_unit.unit_set.exclude(
            pk__in=[unit.pk, self.source.pk]
        ).first()
        if sibling is None:
            self.fail("Missing sibling translation")
        self.assertEqual(sibling.all_flags.get_value("max-length"), 20)
        self.set_flags(unit, "")
        self.assertEqual(unit.priority, 60)
        self.assertEqual(unit.all_flags.get_value("max-length"), 20)

    def test_flags_form_updates_both_scopes(self) -> None:
        response = self.client.post(
            self.url,
            {
                "edit_flags": "1",
                "source_flags": "max-length:20",
                "translation_flags": "max-length:10, priority:70",
            },
        )
        self.assertEqual(response.status_code, 302)
        unit = Unit.objects.get(pk=self.unit.pk)
        self.assertEqual(unit.all_flags.get_value("max-length"), 10)
        self.assertEqual(unit.priority, 70)
        self.assertEqual(unit.source_unit.extra_flags, "max-length:20")
        form = UnitFlagsForm(unit=unit.source_unit, user=self.user)
        self.assertNotIn("translation_flags", form.fields)

    def test_invalid_form_is_atomic(self) -> None:
        response = self.client.post(
            self.url,
            {
                "edit_flags": "1",
                "source_flags": "read-only",
                "translation_flags": "max-length:not-a-number",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.source.refresh_from_db()
        self.assertEqual(self.source.extra_flags, "")

    def test_promotion_requires_both_permissions(self) -> None:
        self.set_flags(self.unit, "read-only")
        original = User.has_perm
        source_id = self.source.translation_id

        def has_perm(user: User, permission: str, obj: Model | None = None) -> bool:
            if permission == "meta:unit.flag":
                return obj is not None and obj.pk != source_id
            return bool(original(user, permission, obj))

        with patch.object(User, "has_perm", has_perm):
            self.assertNotIn(("promoteflag", "read-only", "source"), self.actions())
            response = self.client.post(
                self.url, {"promoteflag": "read-only", "scope": "source"}
            )
        self.assertEqual(response.status_code, 403)
        self.source.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.source.extra_flags, "")
        self.assertEqual(self.unit.extra_flags, "read-only")

    def test_forged_action_rejected(self) -> None:
        for data in (
            {"addflag": "read-only", "scope": "unknown"},
            {"addflag": "terminology", "scope": "source"},
            {"promoteflag": "max-length:10", "scope": "source"},
            {"addflag": "read-only", "removeflag": "read-only"},
        ):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.url, data).status_code, 404)

    def test_bulk_translation_flags_include_empty_and_readonly(self) -> None:
        Unit.objects.filter(pk=self.unit.pk).update(state=STATE_EMPTY, target="")
        units = Unit.objects.filter(pk__in=[self.unit.pk, self.source.pk])
        for add, remove, readonly in (
            ("read-only", "", True),
            ("", "read-only", False),
        ):
            bulk_perform(
                self.user,
                units,
                query="",
                target_state=-1,
                add_flags="",
                remove_flags="",
                add_translation_flags=add,
                remove_translation_flags=remove,
                add_labels=self.project.label_set.none(),
                remove_labels=self.project.label_set.none(),
                project=self.project,
            )
            self.unit.refresh_from_db()
            self.source.refresh_from_db()
            self.assertEqual(self.unit.readonly, readonly)
            self.assertEqual(self.source.extra_flags, "")

    def test_source_view_offers_source_scope_only(self) -> None:
        actions = self.source.get_flag_actions(self.user)
        self.assertTrue(actions)
        self.assertTrue(
            all(scope == "source" for _action, _flag, _label, scope in actions)
        )

    def test_glossary_flags_have_explicit_scope(self) -> None:
        self.component.is_glossary = True
        self.component.save(update_fields=["is_glossary"])
        actions = self.actions()
        self.assertIn(("addflag", "forbidden", "translation"), actions)
        self.assertIn(("addflag", "terminology", "source"), actions)
        self.client.post(self.url, {"addflag": "forbidden", "scope": "translation"})
        self.unit.refresh_from_db()
        self.source.refresh_from_db()
        self.assertIn("forbidden", Flags(self.unit.extra_flags))
        self.assertNotIn("forbidden", Flags(self.source.extra_flags))

    def test_bulk_flags_use_matches_before_state_change(self) -> None:
        Unit.objects.filter(pk=self.unit.pk).update(state=STATE_FUZZY)
        bulk_perform(
            self.user,
            Unit.objects.filter(pk=self.unit.pk),
            query="state:needs-editing",
            target_state=STATE_TRANSLATED,
            add_flags="",
            remove_flags="",
            add_translation_flags="read-only",
            add_labels=self.project.label_set.none(),
            remove_labels=self.project.label_set.none(),
            project=self.project,
        )
        self.unit.refresh_from_db()
        self.assertTrue(self.unit.readonly)
        self.assertEqual(self.unit.original_state, STATE_TRANSLATED)

    def test_bulk_flags_require_language_permission(self) -> None:
        with patch.object(User, "has_perm", return_value=False):
            updated = bulk_perform(
                self.user,
                Unit.objects.filter(pk=self.unit.pk),
                query="",
                target_state=-1,
                add_flags="",
                remove_flags="",
                add_translation_flags="read-only",
                add_labels=self.project.label_set.none(),
                remove_labels=self.project.label_set.none(),
                project=self.project,
            )
        self.assertEqual(updated, 0)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.extra_flags, "")

    def test_disabled_source_field_rejects_forged_edit(self) -> None:
        with patch.object(User, "has_perm", return_value=False):
            form = UnitFlagsForm(
                {"source_flags": "read-only", "translation_flags": ""},
                unit=self.unit,
                user=self.user,
            )
        self.assertFalse(form.is_valid())
        self.source.refresh_from_db()
        self.assertEqual(self.source.extra_flags, "")

    def test_editor_exposes_both_flag_scopes(self) -> None:
        response = self.client.get(self.unit.get_absolute_url())
        self.assertContains(response, 'id="id_source_flags"')
        self.assertContains(response, 'id="id_translation_flags"')
        self.assertContains(response, "Source flags — all languages")
        self.assertContains(response, "Mark this translation as read-only")
        self.assertContains(response, "Mark as read-only for all languages")

    def test_malformed_file_flags_do_not_break_actions(self) -> None:
        self.unit.flags = 'max-length:"'
        self.unit.extra_flags = "read-only"
        actions = self.unit.get_flag_actions(self.user)
        self.assertIn(
            ("removeflag", "read-only", "translation"),
            {(action, flag, scope) for action, flag, _label, scope in actions},
        )
