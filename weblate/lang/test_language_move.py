# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from io import StringIO
from typing import TYPE_CHECKING, ClassVar, cast
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command
from django.db.models.signals import post_migrate
from django.test import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse
from weblate_language_data import languages, population
from weblate_language_data.aliases import ALIASES

from weblate.auth.models import Group, Invitation, Permission, Role, TeamMembership
from weblate.auth.permissions import check_permission
from weblate.fonts.models import Font, FontGroup, FontOverride
from weblate.lang import data, models
from weblate.lang.models import Language, Plural
from weblate.memory.models import Memory
from weblate.trans.actions import ActionEvents
from weblate.trans.models import (
    Announcement,
    Category,
    Change,
    Component,
    Project,
    Translation,
    WorkflowSetting,
)
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.stats import ProjectLanguage
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Generator

    from django.db.models import Field, Model

    from weblate.accounts.models import Profile


class LanguageMoveFixtures(ViewTestCase):
    """Executable fixtures for every forward relation to Language."""

    relation_fixtures: ClassVar[dict[tuple[str, str], str]] = {
        ("accounts.profile", "languages"): "profile_fixture",
        ("accounts.profile", "secondary_languages"): "profile_fixture",
        ("weblate_auth.group", "languages"): "group_fixture",
        ("weblate_auth.teammembership", "limit_languages"): "membership_fixture",
        ("weblate_auth.invitation", "limit_languages"): "invitation_fixture",
        ("workspaces.workspace", "secondary_language"): "workspace_fixture",
        ("trans.project", "secondary_language"): "project_fixture",
        ("trans.category", "secondary_language"): "category_fixture",
        ("trans.component", "secondary_language"): "component_fixture",
        ("trans.component", "source_language"): "component_fixture",
        ("trans.translation", "language"): "translation_fixture",
        ("trans.announcement", "language"): "announcement_fixture",
        ("trans.change", "language"): "change_fixture",
        ("trans.workflowsetting", "language"): "workflow_fixture",
        ("trans.workflowsetting", "source_language"): "source_workflow_fixture",
        ("fonts.fontoverride", "language"): "font_fixture",
        ("memory.memory", "source_language"): "memory_fixture",
        ("memory.memory", "target_language"): "memory_fixture",
        ("lang.plural", "language"): "plural_fixture",
    }

    def setUp(self) -> None:
        super().setUp()
        self.source = Language.objects.get(code="it")
        self.unrelated = Language.objects.get(code="cs")

    def create_component(self) -> Component:
        return self.create_po_new_base()

    def profile_fixture(self) -> Profile:
        return self.user.profile

    def group_fixture(self) -> Group:
        group, created = Group.objects.get_or_create(name="Language migration")
        if created:
            role = Role.objects.create(name="Language migration editor")
            role.permissions.add(Permission.objects.get(codename="unit.edit"))
            group.roles.add(role)
            group.projects.add(self.project)
        return group

    def membership_fixture(self) -> TeamMembership:
        self.anotheruser.groups.clear()
        return TeamMembership.objects.get_or_create(
            user=self.anotheruser, group=self.group_fixture()
        )[0]

    def invitation_fixture(self) -> Invitation:
        return Invitation.objects.create(
            author=self.user,
            email="migration@example.com",
            group=self.group_fixture(),
        )

    def workspace_fixture(self) -> Workspace:
        workspace = Workspace.objects.create(name="Language migration")
        Project.objects.filter(pk=self.project.pk).update(workspace=workspace)
        self.project.refresh_from_db()
        return workspace

    def project_fixture(self) -> Project:
        return self.project

    def category_fixture(self) -> Category:
        return self.create_category(self.project)

    def component_fixture(self) -> Component:
        return self.component

    def translation_fixture(self) -> Translation:
        return self.component.translation_set.get(language=self.source)

    def announcement_fixture(self) -> Announcement:
        return Announcement.objects.create(
            message="Migration announcement", project=self.project
        )

    def change_fixture(self) -> Change:
        return Change.objects.create(action=ActionEvents.UPDATE, project=self.project)

    def workflow_fixture(self) -> WorkflowSetting:
        return WorkflowSetting.objects.create(
            project=self.project,
            language=self.source,
            translation_review=True,
            enable_suggestions=False,
            restrict_direct_editing=True,
        )

    def source_workflow_fixture(self) -> WorkflowSetting:
        return WorkflowSetting.objects.create(
            project=self.project,
            language=self.unrelated,
            source_language=self.source,
        )

    def font_fixture(self) -> FontOverride:
        font = Font.objects.create(family="Migration", project=self.project)
        group = FontGroup.objects.create(
            name="Migration", font=font, project=self.project
        )
        return FontOverride.objects.create(group=group, font=font, language=self.source)

    def memory_fixture(self) -> Memory:
        return Memory.objects.create(
            source_language=self.source,
            target_language=self.source,
            source="Source text",
            target="Translated text",
            origin="Language migration test",
            legacy_project=self.project,
        )

    def plural_fixture(self) -> Plural:
        return self.source.plural_set.create(
            source=Plural.SOURCE_MANUAL, number=2, formula="(n != 1)"
        )

    def populate_relations(
        self, target: Language | None = None
    ) -> dict[tuple[str, str], Model]:
        records = {}
        self.original_values = {}
        for key, factory in self.relation_fixtures.items():
            with self.subTest(relation=key):
                instance = getattr(self, factory)()
                self.assertEqual(instance._meta.label_lower, key[0])  # ruff: ignore[private-member-access]
                field = instance._meta.get_field(key[1])  # ruff: ignore[private-member-access]
                if field.many_to_many:
                    selections = [self.source, self.unrelated]
                    if target is not None:
                        selections.append(target)
                    getattr(instance, field.name).set(selections)
                else:
                    type(instance).objects.filter(pk=instance.pk).update(
                        **{field.attname: self.source.pk}
                    )
                instance.refresh_from_db()
                records[key] = instance
                self.original_values[key] = self.record_values(instance)
        return records

    @staticmethod
    def record_values(instance: Model) -> dict[str, object]:
        """Preserve every stored value except language references and plurals."""
        return {
            field.attname: getattr(instance, field.attname)
            for field in instance._meta.concrete_fields  # ruff: ignore[private-member-access]
            if not field.primary_key
            and field.related_model is not Language
            and not (isinstance(instance, Translation) and field.name == "plural")
        }

    def assert_relations_moved(
        self, records: dict[tuple[str, str], Model], target: Language
    ) -> None:
        for key, instance in records.items():
            with self.subTest(relation=key):
                if key == ("lang.plural", "language"):
                    plural = cast("Plural", instance)
                    self.assertTrue(
                        target.plural_set.filter(
                            source=plural.source,
                            number=plural.number,
                            formula=plural.formula,
                        ).exists()
                    )
                    continue
                instance.refresh_from_db()
                self.assertEqual(
                    self.record_values(instance), self.original_values[key]
                )
                field = cast("Field", instance._meta.get_field(key[1]))  # ruff: ignore[private-member-access]
                if field.many_to_many:
                    self.assertEqual(
                        set(getattr(instance, field.name).values_list("pk", flat=True)),
                        {target.pk, self.unrelated.pk},
                    )
                else:
                    self.assertEqual(getattr(instance, field.attname), target.pk)

        translation = cast("Translation", records["trans.translation", "language"])
        self.assertEqual(translation.plural.language_id, target.pk)
        workflow = ProjectLanguage(self.project, target)
        self.assertTrue(workflow.workflow_settings.translation_review)
        self.assertFalse(workflow.enable_suggestions)
        self.assertTrue(workflow.restrict_direct_editing)
        self.anotheruser.clear_permissions_cache()
        self.assertTrue(check_permission(self.anotheruser, "unit.edit", translation))
        denied = self.component.translation_set.get(language__code="de")
        self.assertFalse(check_permission(self.anotheruser, "unit.edit", denied))


class LanguageMoveTest(LanguageMoveFixtures):
    def setUp(self) -> None:
        super().setUp()
        self.target = Language.objects.auto_create("it_XX")

    def test_relation_coverage(self) -> None:
        relations = {
            (model._meta.label_lower, field.name)  # ruff: ignore[private-member-access]
            for model in apps.get_models()
            for field in model._meta.get_fields()  # ruff: ignore[private-member-access]
            if field.is_relation
            and not field.auto_created
            and field.related_model is Language
        }
        self.assertSetEqual(relations, set(self.relation_fixtures))

    def test_move_all_relations(self) -> None:
        records = self.populate_relations()
        translation = cast("Translation", records["trans.translation", "language"])
        original_file = (translation.filename, translation.language_code)
        original_units = list(translation.unit_set.values_list("pk", "target"))
        Language.objects.move_language(self.source, self.target)
        self.assert_relations_moved(records, self.target)
        self.assertEqual(
            (translation.filename, translation.language_code), original_file
        )
        self.assertCountEqual(
            list(translation.unit_set.values_list("pk", "target")), original_units
        )
        self.assertTrue(self.source.has_no_children())
        Language.objects.move_language(self.source, self.target)
        self.assert_relations_moved(records, self.target)

    def test_move_existing_selections(self) -> None:
        records = self.populate_relations(self.target)
        Language.objects.move_language(self.source, self.target)
        self.assert_relations_moved(records, self.target)

    def assert_move_skipped(self, records: dict[tuple[str, str], Model]) -> None:
        logs: list[str] = []
        Language.objects.move_language(self.source, self.target, logs.append)
        self.assertEqual(len(logs), 1)
        self.assertIn("Skipping language move", logs[0])
        self.assert_relations_unchanged(records)

    def assert_relations_unchanged(self, records: dict[tuple[str, str], Model]) -> None:
        for key, instance in records.items():
            with self.subTest(relation=key):
                instance.refresh_from_db()
                self.assertEqual(
                    self.record_values(instance), self.original_values[key]
                )
                field = cast("Field", instance._meta.get_field(key[1]))  # ruff: ignore[private-member-access]
                if field.many_to_many:
                    self.assertEqual(
                        set(getattr(instance, field.name).values_list("pk", flat=True)),
                        {self.source.pk, self.unrelated.pk},
                    )
                else:
                    self.assertEqual(getattr(instance, field.attname), self.source.pk)

    def test_translation_conflict(self) -> None:
        self.component.new_lang = "add"
        self.component.save()
        self.component.add_new_language(self.target, None)
        records = self.populate_relations()
        self.assert_move_skipped(records)

    def test_workflow_conflict(self) -> None:
        records = self.populate_relations()
        WorkflowSetting.objects.create(project=self.project, language=self.target)
        self.assert_move_skipped(records)

    def test_font_conflict(self) -> None:
        records = self.populate_relations()
        override = cast("FontOverride", records["fonts.fontoverride", "language"])
        font = Font.objects.create(family="Different", project=self.project)
        FontOverride.objects.create(
            group=override.group, font=font, language=self.target
        )
        self.assert_move_skipped(records)

    def test_identical_settings(self) -> None:
        records = self.populate_relations()
        for key in (
            ("trans.workflowsetting", "language"),
            ("fonts.fontoverride", "language"),
        ):
            original = cast("WorkflowSetting | FontOverride", records[key])
            values = {
                field.attname: getattr(original, field.attname)
                for field in original._meta.concrete_fields  # ruff: ignore[private-member-access]
                if not field.primary_key
            }
            values["language_id"] = self.target.pk
            records[key] = type(original).objects.create(**values)
        Language.objects.move_language(self.source, self.target)
        self.assert_relations_moved(records, self.target)
        self.assertFalse(self.source.workflowsetting_set.exists())
        self.assertFalse(self.source.fontoverride_set.exists())

    def test_global_workflow(self) -> None:
        workflow = WorkflowSetting.objects.create(
            language=self.source, project=None, translation_review=True
        )
        Language.objects.move_language(self.source, self.target)
        workflow.refresh_from_db()
        self.assertEqual(workflow.language, self.target)
        self.assertTrue(
            ProjectLanguage(
                self.project, self.target
            ).workflow_settings.translation_review
        )

    def test_rollback(self) -> None:
        records = self.populate_relations()
        with (
            patch.object(
                WorkflowSetting, "save", side_effect=RuntimeError("Move failed")
            ),
            self.assertRaisesMessage(RuntimeError, "Move failed"),
        ):
            Language.objects.move_language(self.source, self.target)
        self.assert_relations_unchanged(records)

    def test_same_language(self) -> None:
        records = self.populate_relations()
        Language.objects.move_language(self.source, self.source)
        self.assert_relations_unchanged(records)


@contextmanager
def norwegian_alias_data() -> Generator[None, None, None]:
    """Simulate a coherent reversal without changing the shipped dataset."""

    def rename(rows: tuple) -> tuple:
        return tuple(("nb" if row[0] == "nb_NO" else row[0], *row[1:]) for row in rows)

    aliases = {
        key: "nb" if value == "nb_NO" else value
        for key, value in ALIASES.items()
        if key != "nb"
    }
    aliases["nb_no"] = "nb"
    populations = population.POPULATION.copy()
    if "nb" not in populations:
        populations["nb"] = populations["nb_NO"]
    populations.pop("nb_NO", None)
    with ExitStack() as stack:
        for obj, name, value in (
            (languages, "LANGUAGES", rename(languages.LANGUAGES)),
            (population, "POPULATION", populations),
            (models, "ALIASES", aliases),
            (data, "ALIASES", aliases),
            (data, "NO_CODE_LANGUAGES", (data.NO_CODE_LANGUAGES - {"nb_NO"}) | {"nb"}),
        ):
            stack.enter_context(patch.object(obj, name, value))
        for name in ("EXTRAPLURALS", "CLDRPLURALS", "QTPLURALS"):
            stack.enter_context(
                patch.object(models, name, rename(getattr(models, name)))
            )
        yield


class NorwegianAliasMigrationTest(LanguageMoveFixtures):
    def setUp(self) -> None:
        super().setUp()
        self.source, _created = Language.objects.get_or_create(
            code="nb_NO", defaults={"name": "Norwegian Bokmål"}
        )
        self.source.plural_set.get_or_create(
            source=Plural.SOURCE_DEFAULT,
            defaults={"number": 2, "formula": "n != 1"},
        )
        self.component.new_lang = "add"
        self.component.save()
        self.component.add_new_language(self.source, None)

    def test_local_language_lookup(self) -> None:
        self.assertEqual(Language.objects.fuzzy_get("nb_NO"), self.source)
        self.assertEqual(Language.objects.fuzzy_get("nb-NO"), self.source)

    def test_request_language_after_upgrade(self) -> None:
        request = RequestFactory().get("/", HTTP_ACCEPT_LANGUAGE="nb-NO")
        with norwegian_alias_data():
            Language.objects.setup(update=True)
            target = Language.objects.get(code="nb")
            self.assertEqual(Language.objects.get_request_language(request), target)
            self.assertEqual(
                Language.objects.filter(translation__component=self.component)
                .distinct()
                .get_request_language(request),
                target,
            )

    @override_settings(UPDATE_LANGUAGES=True)
    def test_populated_upgrade(self) -> None:
        records = self.populate_relations()
        translation = cast("Translation", records["trans.translation", "language"])
        filename = translation.filename
        with norwegian_alias_data():
            self.send_post_migrate()
            target = Language.objects.get(code="nb")
            self.assert_relations_moved(records, target)
            self.assertFalse(Language.objects.filter(code="nb_NO").exists())
            self.assertEqual(translation.filename, filename)
            self.assertEqual(translation.language_code, "nb_NO")
            for code in ("nb_NO", "nb-NO"):
                self.assertEqual(Language.objects.fuzzy_get(code), target)
                cache = Language.objects.all().build_fuzzy_get_cache()
                self.assertEqual(Language.objects.fuzzy_get(code, cache=cache), target)
            self.send_post_migrate()
            self.assert_relations_moved(records, target)

    def test_rescan_and_redirects(self) -> None:
        translation = self.translation_fixture()
        filename = translation.filename
        units = list(translation.unit_set.values_list("pk", "target"))
        old_url = translation.get_absolute_url()
        with norwegian_alias_data():
            Language.objects.setup(update=True)
            translation.refresh_from_db()
            self.assertEqual(translation.language.code, "nb")
            component = Component.objects.get(pk=self.component.pk)
            component.create_translations_immediate(force=True, force_scan=True)
            translation.refresh_from_db()
            self.assertEqual(translation.filename, filename)
            self.assertEqual(translation.language_code, "nb_NO")
            self.assertEqual(
                list(translation.unit_set.values_list("pk", "target")), units
            )
            self.assertRedirects(
                self.client.get(f"{old_url}?q=hello"),
                f"{translation.get_absolute_url()}?q=hello",
                status_code=301,
            )
            self.assertRedirects(
                self.client.get(reverse("show_language", kwargs={"lang": "nb_NO"})),
                translation.language.get_absolute_url(),
                status_code=302,
            )

    @override_settings(UPDATE_LANGUAGES=False)
    def test_explicit_setup_when_updates_disabled(self) -> None:
        translation = self.translation_fixture()
        with norwegian_alias_data():
            self.send_post_migrate()
            self.assertTrue(Language.objects.filter(code="nb_NO").exists())
            call_command("setuplang", stdout=StringIO())
            self.assertFalse(Language.objects.filter(code="nb_NO").exists())
            translation.refresh_from_db()
            self.assertEqual(translation.language.code, "nb")

    def test_conflict_does_not_block_other_aliases(self) -> None:
        target, _created = Language.objects.get_or_create(
            code="nb", defaults={"name": "Norwegian Bokmål"}
        )
        target.plural_set.get_or_create(
            source=Plural.SOURCE_DEFAULT,
            defaults={"number": 2, "formula": "n != 1"},
        )
        self.component.add_new_language(target, None)
        other = Language.objects.auto_create("CZE")
        self.user.profile.languages.add(other)
        logs: list[str] = []
        with norwegian_alias_data():
            Language.objects.setup(update=True, logger=logs.append)
        self.assertTrue(Language.objects.filter(code="nb_NO").exists())
        self.assertTrue(self.source.translation_set.exists())
        self.assertFalse(Language.objects.filter(pk=other.pk).exists())
        self.assertIn(self.unrelated, self.user.profile.languages.all())
        self.assertTrue(
            any("Skipping language move nb_NO to nb" in log for log in logs)
        )

    def send_post_migrate(self) -> None:
        app_config = apps.get_app_config("lang")
        post_migrate.send(
            sender=app_config,
            app_config=app_config,
            using="default",
            verbosity=0,
            interactive=False,
        )
