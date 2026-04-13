# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for variants."""

from typing import cast
from unittest.mock import patch

from django.core.cache import cache
from django.test.utils import override_settings
from django.urls import reverse

from weblate.trans.actions import ActionEvents
from weblate.trans.tests.test_views import FixtureTestCase, ViewTestCase


class LabelTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.make_manager()
        self.labels_url = reverse("labels", kwargs=self.kw_project)

    def test_create(self) -> None:
        response = self.client.post(
            self.labels_url,
            {
                "name": "Test label",
                "description": "Test description for Test Label",
                "color": "orange",
                "project": self.project.pk,
            },
            follow=True,
        )
        self.assertRedirects(response, self.labels_url)
        self.assertContains(response, "Test label")
        self.assertTrue(self.project.label_set.filter(name="Test label").exists())

    def test_create_duplicate(self) -> None:
        self.test_create()
        response = self.client.post(
            self.labels_url,
            {
                "name": "Test label",
                "description": "Test description for Test Label",
                "color": "orange",
                "project": self.project.pk,
            },
            follow=True,
        )
        self.assertContains(
            response, "Label with this Project and Label name already exists."
        )
        self.assertEqual(self.project.label_set.filter(name="Test label").count(), 1)

    def test_edit_name(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        response = self.client.post(
            reverse(
                "label_edit", kwargs={"project": self.project.slug, "pk": label.pk}
            ),
            {
                "name": "Renamed label",
                "description": "Test description for Test Label",
                "color": "orange",
                "project": self.project.pk,
            },
            follow=True,
        )
        self.assertRedirects(response, self.labels_url)
        self.assertContains(response, "Renamed label")
        self.assertTrue(self.project.label_set.filter(name="Renamed label").exists())

    def test_edit_description(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        response = self.client.post(
            reverse(
                "label_edit", kwargs={"project": self.project.slug, "pk": label.pk}
            ),
            {
                "name": "Test label",
                "description": "Edited description for Test Label",
                "color": "orange",
                "project": self.project.pk,
            },
            follow=True,
        )
        self.assertRedirects(response, self.labels_url)
        self.assertContains(response, "Test label")
        self.assertTrue(
            self.project.label_set.filter(
                description="Edited description for Test Label"
            ).exists()
        )

    def test_delete(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        response = self.client.post(
            reverse(
                "label_delete", kwargs={"project": self.project.slug, "pk": label.pk}
            ),
            follow=True,
        )
        self.assertRedirects(response, self.labels_url)
        self.assertNotContains(response, "Test label")
        self.assertFalse(self.project.label_set.filter(name="Test label").exists())

    def test_assign(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        unit = self.get_unit().source_unit
        self.client.post(
            reverse("edit_context", kwargs={"pk": unit.pk}),
            {"explanation": "", "extra_flags": "", "labels": label.pk},
        )
        translation = self.get_translation()
        self.assertEqual(getattr(translation.stats, "label:Test label"), 1)
        changes = unit.change_set.filter(action=ActionEvents.LABEL_ADD)
        self.assertEqual(changes.count(), 1)
        self.assertEqual(changes.first().user, self.user)

        self.client.post(
            reverse("edit_context", kwargs={"pk": unit.pk}),
            {"explanation": "", "extra_flags": ""},
        )
        translation = self.get_translation()
        self.assertEqual(getattr(translation.stats, "label:Test label"), 0)
        changes = unit.change_set.filter(action=ActionEvents.LABEL_REMOVE)
        self.assertEqual(changes.count(), 1)
        self.assertEqual(changes.first().user, self.user)

    def test_delete_assigned(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        unit = self.get_unit().source_unit
        self.client.post(
            reverse("edit_context", kwargs={"pk": unit.pk}),
            {"explanation": "", "extra_flags": "", "labels": label.pk},
        )
        translation = self.get_translation()
        self.assertEqual(getattr(translation.stats, "label:Test label"), 1)

        label.delete()

        translation = self.get_translation()
        with self.assertRaises(AttributeError):
            getattr(translation.stats, "label:Test label")

    def test_label_multiple_changes(self) -> None:
        """Test that adding multiple labels creates multiple change events."""
        self.test_create()
        self.client.post(
            self.labels_url,
            {
                "name": "Second label",
                "description": "Second test label",
                "color": "blue",
                "project": self.project.pk,
            },
        )

        label1 = self.project.label_set.get(name="Test label")
        label2 = self.project.label_set.get(name="Second label")
        unit = self.get_unit().source_unit

        self.client.post(
            reverse("edit_context", kwargs={"pk": unit.pk}),
            {"explanation": "", "extra_flags": "", "labels": [label1.pk, label2.pk]},
        )

        changes = unit.change_set.filter(action=ActionEvents.LABEL_ADD)
        self.assertEqual(changes.count(), 2)


class MonolingualLabelTest(ViewTestCase):
    def create_component(self):
        return self.create_ts_mono()

    def test_source_change_recalculates_cached_label_stats(self) -> None:
        label = self.project.label_set.create(
            name="Test label",
            description="Test description for Test Label",
            color="orange",
        )
        target_translation = self.get_translation()
        target_unit = self.get_unit(language="cs")
        target_unit.source_unit.labels.add(label)

        label_words = f"label:{label.name}_words"
        self.assertEqual(
            getattr(target_translation.stats, label_words),
            target_unit.source_unit.num_words,
        )

        self.edit_unit("Hello, world!\n", "Hello, beautiful world!\n", language="en")

        updated_unit = self.get_unit("Hello, beautiful world!\n", language="cs")
        target_translation = self.get_translation()
        self.assertEqual(
            getattr(target_translation.stats, label_words),
            updated_unit.source_unit.num_words,
        )

    def test_apply_source_delta_uses_latest_cached_stats(self) -> None:
        stats = self.get_translation().stats
        _ = stats.all_words
        base_timestamp = cast("float", stats.stats_timestamp)
        latest = stats.get_data_copy()
        latest["all_words"] = cast("int", latest["all_words"]) + 3
        cache.set(stats.cache_key, latest, 30 * 86400)

        self.assertTrue(stats.apply_source_delta(base_timestamp, {"all_words": 2}))
        self.assertEqual(
            cache.get(stats.cache_key)["all_words"],
            cast("int", latest["all_words"]) + 2,
        )

    def test_apply_source_delta_skips_newer_generation(self) -> None:
        stats = self.get_translation().stats
        _ = stats.all_words
        base_timestamp = cast("float", stats.stats_timestamp)
        latest = stats.get_data_copy()
        latest["stats_timestamp"] = base_timestamp + 1
        latest["all_words"] = cast("int", latest["all_words"]) + 7
        cache.set(stats.cache_key, latest, 30 * 86400)

        self.assertFalse(stats.apply_source_delta(base_timestamp, {"all_words": 2}))
        self.assertEqual(cache.get(stats.cache_key), latest)

    @override_settings(STATS_LAZY=False)
    def test_save_holds_lock(self) -> None:
        stats = self.get_translation().stats
        original = cache.set

        def wrapped(*args, **kwargs) -> None:
            if args[0] == stats.cache_key:
                self.assertTrue(stats.lock.is_locked)
            original(*args, **kwargs)

        with patch("weblate.utils.stats.cache.set", side_effect=wrapped):
            stats.update_stats(update_parents=False)
