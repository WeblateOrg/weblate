# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for unitdata models."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils.html import format_html

from weblate.checks.base import BatchCheckMixin
from weblate.checks.consistency import ConsistencyCheck
from weblate.checks.models import CHECKS, Check
from weblate.checks.tasks import finalize_component_checks
from weblate.trans.models import Project, Unit
from weblate.trans.tasks import auto_translate
from weblate.trans.tests.test_views import FixtureTestCase, ViewTestCase
from weblate.utils.lock import WeblateLock


class CheckLintTestCase(SimpleTestCase):
    def test_check_id(self) -> None:
        for check in CHECKS.values():
            self.assertRegex(check.check_id, r"^[a-z][a-z0-9_-]*[a-z]$")
            self.assertTrue(
                check.description.endswith("."),
                f"{check.__class__.__name__} description does not have a stop: {check.description}",
            )


class CheckModelTestCase(FixtureTestCase):
    def create_check(self, name):
        return Check.objects.create(unit=self.get_unit(), name=name)

    def test_check(self) -> None:
        check = self.create_check("same")
        self.assertEqual(
            str(check.get_description()), "Source and translation are identical."
        )
        self.assertTrue(check.get_doc_url().endswith("user/checks.html#check-same"))
        self.assertEqual(str(check), "Unchanged translation")

    def test_check_nonexisting(self) -> None:
        check = self.create_check("-invalid-")
        self.assertEqual(check.get_description(), "-invalid-")
        self.assertEqual(check.get_doc_url(), "")

    def test_check_render(self) -> None:
        unit = self.get_unit()
        unit.source_unit.extra_flags = "max-size:1:1"
        unit.source_unit.save()
        check = self.create_check("max-size")
        url = reverse(
            "render-check", kwargs={"check_id": check.name, "unit_id": unit.id}
        )
        self.assertHTMLEqual(
            check.get_description(),
            format_html(
                '<a href="{0}?pos={1}" class="thumbnail img-check">'
                '<img class="img-fluid" src="{0}?pos={1}" /></a>',
                url,
                0,
            ),
        )
        self.assert_png(self.client.get(url))


class BatchCheckMixinTest(SimpleTestCase):
    def test_project_checks_lock_uses_unique_file_name(self) -> None:
        project = Project(name="Shared", slug="shared")

        with TemporaryDirectory() as lock_path:
            project.__dict__["full_path"] = lock_path
            with patch("weblate.utils.lock.is_redis_cache", return_value=False):
                project_lock = project.checks_lock
                component_lock = WeblateLock(
                    lock_path=lock_path,
                    scope="component-checks",
                    key=1,
                    slug=project.slug,
                    cache_template="{scope}-lock-{key}",
                    file_template="{slug}-{scope}-{key}.lock",
                    timeout=5,
                    origin=project.full_slug,
                )

        self.assertNotEqual(project_lock._name, component_lock._name)  # noqa: SLF001
        self.assertEqual(
            Path(project_lock._name).name,  # noqa: SLF001
            "shared-project-checks.lock",
        )
        self.assertEqual(
            Path(component_lock._name).name,  # noqa: SLF001
            "shared-component-checks-1.lock",
        )

    def test_component_checks_lock_uses_key_in_file_name(self) -> None:
        with (
            TemporaryDirectory() as lock_path,
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
        ):
            first_lock = WeblateLock(
                lock_path=lock_path,
                scope="component-checks",
                key=1,
                slug="shared",
                cache_template="{scope}-lock-{key}",
                file_template="{slug}-{scope}-{key}.lock",
                timeout=5,
                origin="project/shared",
            )
            second_lock = WeblateLock(
                lock_path=lock_path,
                scope="component-checks",
                key=2,
                slug="shared",
                cache_template="{scope}-lock-{key}",
                file_template="{slug}-{scope}-{key}.lock",
                timeout=5,
                origin="project/shared",
            )

        self.assertNotEqual(first_lock._name, second_lock._name)  # noqa: SLF001
        self.assertEqual(
            Path(first_lock._name).name,  # noqa: SLF001
            "shared-component-checks-1.lock",
        )
        self.assertEqual(
            Path(second_lock._name).name,  # noqa: SLF001
            "shared-component-checks-2.lock",
        )

    def test_project_wide_batch_uses_project_lock(self) -> None:
        project_lock = MagicMock()
        component: Any = SimpleNamespace(
            allow_translation_propagation=True,
            project=SimpleNamespace(checks_lock=project_lock),
        )

        with patch.object(ConsistencyCheck, "_perform_batch") as perform_batch:
            ConsistencyCheck().perform_batch(component)

        project_lock.__enter__.assert_called_once()
        project_lock.__exit__.assert_called_once()
        perform_batch.assert_called_once_with(component)

    def test_perform_batch_sorts_bulk_create_by_unique_key(self) -> None:
        class DummyBatchCheck(BatchCheckMixin):
            check_id = "dummy"

            def should_skip(self, unit) -> bool:
                return False

            def check_component(self, component):
                return [unit_b, unit_a]

        class FakeCheck:
            objects = MagicMock()

            def __init__(self, *, unit, dismissed, name):
                self.dismissed = dismissed
                self.name = name
                self.unit_id = unit.pk

        component: Any = SimpleNamespace(
            id=1,
            allow_translation_propagation=False,
            invalidate_cache=MagicMock(),
        )
        unit_a = SimpleNamespace(
            pk=2,
            all_checks_names=set(),
            translation=SimpleNamespace(component=component),
        )
        unit_b = SimpleNamespace(
            pk=1,
            all_checks_names=set(),
            translation=SimpleNamespace(component=component),
        )
        stale_checks = MagicMock()
        stale_checks.filter.return_value = stale_checks
        stale_checks.delete.return_value = (0, {})
        FakeCheck.objects.exclude.return_value = stale_checks

        with patch("weblate.checks.models.Check", FakeCheck):
            DummyBatchCheck().perform_batch(component)

        self.assertIsNotNone(FakeCheck.objects.bulk_create.call_args)
        created = FakeCheck.objects.bulk_create.call_args.args[0]
        self.assertEqual(
            [(check.unit_id, check.name) for check in created],
            [(1, "dummy"), (2, "dummy")],
        )


class BatchUpdateTest(ViewTestCase):
    """Test for complex manipulating translation."""

    def setUp(self) -> None:
        super().setUp()
        self.translation = self.get_translation()

    def do_base(self):
        # Single unit should have no consistency check
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, set())

        # Add linked project
        other = self.create_link_existing()

        # Now the inconsistent check should be there
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, {"inconsistent"})
        return other

    def test_autotranslate(self) -> None:
        other = self.do_base()
        translation = other.translation_set.get(language_code="cs")
        auto_translate(
            user_id=None,
            mode="translate",
            q="state:<translated",
            auto_source="others",
            source_component_id=self.component.pk,
            engines=[],
            threshold=99,
            translation_id=translation.pk,
        )
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, set())

    def test_noop(self) -> None:
        other = self.do_base()
        # The batch update should not remove it
        finalize_component_checks(
            self.component.id, [], ["inconsistent"], batch_mode=True
        )
        finalize_component_checks(other.id, [], ["inconsistent"], batch_mode=True)
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, {"inconsistent"})

    def test_toggle(self) -> None:
        other = self.do_base()
        one_unit = self.get_unit()
        other_unit = Unit.objects.get(
            translation__language_code=one_unit.translation.language_code,
            translation__component=other,
            id_hash=one_unit.id_hash,
        )
        translated = one_unit.target

        combinations: tuple[tuple[str, str, set[str]], ...] = (
            (translated, "", {"inconsistent"}),
            ("", translated, {"inconsistent"}),
            ("", "", set()),
            (translated, translated, set()),
            ("", translated, {"inconsistent"}),
        )
        for update_one, update_other, expected in combinations:
            Unit.objects.filter(pk=one_unit.pk).update(target=update_one)
            Unit.objects.filter(pk=other_unit.pk).update(target=update_other)

            finalize_component_checks(
                self.component.id, [], ["inconsistent"], batch_mode=True
            )
            unit = self.get_unit()
            self.assertEqual(unit.all_checks_names, expected)

        for update_one, update_other, expected in combinations:
            Unit.objects.filter(pk=one_unit.pk).update(target=update_one)
            Unit.objects.filter(pk=other_unit.pk).update(target=update_other)

            finalize_component_checks(other.id, [], ["inconsistent"], batch_mode=True)
            unit = self.get_unit()
            self.assertEqual(unit.all_checks_names, expected)
