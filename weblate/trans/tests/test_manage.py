# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for management views."""

from __future__ import annotations

import os.path
import pathlib
from typing import ClassVar
from unittest.mock import patch

from django.core import mail
from django.db import connection, transaction
from django.urls import reverse
from lxml.html import fromstring

from weblate.auth.data import SELECTION_ALL, SELECTION_MANUAL
from weblate.auth.models import Group, Role, TeamMembership
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.forms import ComponentRenameForm
from weblate.trans.models import Announcement, Category, Component, Project, Translation
from weblate.trans.models.component import ComponentLink, ComponentQuerySet
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.data import data_dir
from weblate.utils.files import remove_tree
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.vcs.base import RepositoryLock


class RemovalTest(ViewTestCase):
    def test_translation_remove_is_atomic(self) -> None:
        translation = self.get_translation()
        original_delete = Translation.delete

        def wrapped_delete(instance, *args, **kwargs):
            self.assertTrue(connection.in_atomic_block)
            return original_delete(instance, *args, **kwargs)

        with (
            patch.object(
                Translation,
                "delete",
                autospec=True,
                side_effect=wrapped_delete,
            ),
            patch.object(
                Component, "schedule_update_checks", autospec=True
            ) as schedule,
            self.captureOnCommitCallbacks(execute=True),
        ):
            translation.remove(self.user)

        self.assertFalse(Translation.objects.filter(pk=translation.pk).exists())
        schedule.assert_called_once_with(self.component)

    def test_translation(self) -> None:
        self.make_manager()
        url = reverse("remove", kwargs=self.kw_translation)
        response = self.client.post(url, {"confirm": ""}, follow=True)
        self.assertContains(
            response, "The slug does not match the one marked for deletion!"
        )
        response = self.client.post(url, {"confirm": "test/test/cs"}, follow=True)
        self.assertContains(response, "The translation has been removed.")

    def test_project_language_view_remove_is_atomic(self) -> None:
        self.make_manager()
        atomic_states: list[bool] = []
        url = reverse("remove", kwargs={"path": [self.project.slug, "-", "cs"]})

        def wrapped_remove(instance, user) -> None:
            atomic_states.append(connection.in_atomic_block)

        with patch.object(
            Translation, "remove", autospec=True, side_effect=wrapped_remove
        ):
            response = self.client.post(url, {"confirm": "test/-/cs"}, follow=True)

        self.assertContains(response, "A language in the project was removed.")
        self.assertTrue(atomic_states)
        self.assertEqual(set(atomic_states), {True})

    def test_component(self) -> None:
        self.make_manager()
        url = reverse("remove", kwargs=self.kw_component)
        response = self.client.post(url, {"confirm": ""}, follow=True)
        self.assertContains(
            response, "The slug does not match the one marked for deletion!"
        )
        response = self.client.post(url, {"confirm": "test/test"}, follow=True)
        self.assertContains(
            response, "The translation component was scheduled for removal."
        )

    def test_component_with_memory(self) -> None:
        self.make_manager()
        url = reverse("remove", kwargs=self.kw_component)

        with patch(
            "weblate.trans.views.settings.component_removal.delay"
        ) as mocked_removal:
            response = self.client.post(
                url,
                {"confirm": "test/test", "delete_memory": "on"},
                follow=True,
            )

        self.assertContains(
            response, "The translation component was scheduled for removal."
        )
        mocked_removal.assert_called_once_with(self.component.pk, self.user.pk, True)

    def test_component_memory_warning(self) -> None:
        self.make_manager()

        response = self.client.get(self.component.get_absolute_url())

        self.assertContains(
            response,
            "If this action removes restricted components, retained translation memory",
        )

    def test_category_with_memory(self) -> None:
        self.make_manager()
        category = Category.objects.create(
            name="Removal category",
            slug="removal-category",
            project=self.project,
        )
        self.component.category = category
        self.component.save(update_fields=["category"])
        url = reverse("remove", kwargs={"path": category.get_url_path()})

        response = self.client.get(category.get_absolute_url())
        self.assertContains(
            response,
            "If this action removes restricted components, retained translation memory",
        )
        self.assertContains(
            response,
            "Delete translation memory created from components in this category",
        )

        with patch(
            "weblate.trans.views.settings.category_removal.delay"
        ) as mocked_removal:
            response = self.client.post(
                url,
                {"confirm": category.full_slug, "delete_memory": "on"},
                follow=True,
            )

        self.assertContains(response, "The category was scheduled for removal.")
        mocked_removal.assert_called_once_with(category.pk, self.user.pk, True)

    def test_project(self) -> None:
        self.make_manager()
        url = reverse("remove", kwargs={"path": self.project.get_url_path()})
        response = self.client.post(url, {"confirm": ""}, follow=True)
        self.assertContains(
            response, "The slug does not match the one marked for deletion!"
        )
        response = self.client.post(url, {"confirm": "test"}, follow=True)
        self.assertContains(response, "The project was scheduled for removal.")

    def test_project_language(self) -> None:
        self.make_manager()
        self.assertEqual(Translation.objects.count(), 4)
        url = reverse("remove", kwargs={"path": [self.project.slug, "-", "cs"]})
        response = self.client.post(url, {"confirm": ""}, follow=True)
        self.assertContains(
            response, "The slug does not match the one marked for deletion!"
        )
        response = self.client.post(url, {"confirm": "test/-/cs"}, follow=True)
        self.assertContains(response, "A language in the project was removed.")
        self.assertEqual(Translation.objects.count(), 3)


class RenameTest(ViewTestCase):
    lock_timeout_message = (
        "There appears to be an ongoing operation on the repository. "
        "Please try again later."
    )

    def test_denied(self) -> None:
        self.assertNotContains(
            self.client.get(self.project.get_absolute_url()), "#organize"
        )
        self.assertNotContains(
            self.client.get(self.component.get_absolute_url()), "#organize"
        )
        response = self.client.post(
            reverse("rename", kwargs={"path": self.project.get_url_path()}),
            {"project": self.project.pk, "slug": "xxxx", "name": self.project.name},
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {"project": self.project.pk, "slug": "xxxx", "name": self.component.name},
        )
        self.assertEqual(response.status_code, 403)

        other = Project.objects.create(name="Other", slug="other")
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {
                "project": other.pk,
                "slug": self.component.slug,
                "name": self.component.name,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_move_component(self) -> None:
        self.make_manager()
        other = Project.objects.create(name="Other project", slug="other")
        # Other project should be visible as target for moving
        self.assertContains(
            self.client.get(self.component.get_absolute_url()),
            "Other project",
        )
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {
                "project": other.pk,
                "slug": self.component.slug,
                "name": self.component.name,
            },
        )
        self.assertRedirects(response, "/projects/other/test/")
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.project.slug, "other")
        self.assertIsNotNone(component.repository.last_remote_revision)

    def test_rename_invalid(self) -> None:
        url = self.component.get_absolute_url()
        Component.objects.filter(pk=self.component.id).update(filemask="invalid/*.po")
        self.make_manager()
        self.assertContains(self.client.get(url), "#organize")
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {"project": self.project.pk, "slug": "xxxx", "name": self.component.name},
            follow=True,
        )
        self.assertRedirects(response, f"{url}#organize")
        self.assertContains(
            response,
            "Could not change Test/Test due to an outstanding issue in its settings:",
        )

    def test_rename_component(self) -> None:
        self.make_manager()
        original_url = self.component.get_absolute_url()
        self.assertContains(self.client.get(original_url), "#organize")
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {"project": self.project.pk, "slug": "xxxx", "name": self.component.name},
        )
        self.assertRedirects(response, "/projects/test/xxxx/")
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.slug, "xxxx")
        self.assertEqual(
            component.change_set.get(action=ActionEvents.RENAME_COMPONENT).user,
            self.user,
        )
        self.assertIsNotNone(component.repository.last_remote_revision)
        response = self.client.get(component.get_absolute_url())
        self.assertContains(response, "/projects/test/xxxx/")

        # Test rename redirect for the old name in middleware
        response = self.client.get(original_url)
        self.assertRedirects(response, component.get_absolute_url(), status_code=301)

    def test_rename_component_repository_locked(self) -> None:
        self.make_manager()
        url = reverse("rename", kwargs=self.kw_component)
        lock_error = WeblateLockTimeoutError(
            "repository locked", lock=self.component.repository.lock.lock_object
        )

        with patch.object(Component, "locked_for_update", side_effect=lock_error):
            response = self.client.post(
                url,
                {
                    "project": self.project.pk,
                    "slug": "locked-rename",
                    "name": "Locked rename",
                },
                follow=True,
            )

        self.assertRedirects(response, f"{self.component.get_absolute_url()}#organize")
        self.assertContains(response, self.lock_timeout_message)
        self.component.refresh_from_db()
        self.assertEqual(self.component.slug, "test")
        self.assertEqual(self.component.name, "Test")

    def test_rename_project_repository_locked(self) -> None:
        self.make_manager()
        url = reverse("rename", kwargs={"path": self.project.get_url_path()})
        lock_error = WeblateLockTimeoutError(
            "repository locked", lock=self.component.repository.lock.lock_object
        )

        with patch.object(RepositoryLock, "__enter__", side_effect=lock_error):
            response = self.client.post(
                url,
                {"slug": "locked-project", "name": "Locked project"},
                follow=True,
            )

        self.assertRedirects(response, f"{self.project.get_absolute_url()}#organize")
        self.assertContains(response, self.lock_timeout_message)
        self.project.refresh_from_db()
        self.assertEqual(self.project.slug, "test")
        self.assertEqual(self.project.name, "Test")

    def test_rename_category_repository_locked(self) -> None:
        self.make_manager()
        category = Category.objects.create(
            name="Category", slug="category", project=self.project
        )
        Component.objects.filter(pk=self.component.pk).update(category=category)
        url = reverse("rename", kwargs={"path": category.get_url_path()})
        lock_error = WeblateLockTimeoutError(
            "repository locked", lock=self.component.repository.lock.lock_object
        )

        with patch.object(RepositoryLock, "__enter__", side_effect=lock_error):
            response = self.client.post(
                url,
                {
                    "project": self.project.pk,
                    "slug": "locked-category",
                    "name": "Locked category",
                },
                follow=True,
            )

        self.assertRedirects(response, f"{category.get_absolute_url()}#organize")
        self.assertContains(response, self.lock_timeout_message)
        category.refresh_from_db()
        self.assertEqual(category.slug, "category")
        self.assertEqual(category.name, "Category")

    def test_rename_component_replaces_stale_target_dir(self) -> None:
        self.make_manager()
        old_path = self.component.full_path
        target = os.path.join(data_dir("vcs"), self.project.slug, "stale-target")
        os.makedirs(os.path.join(target, ".git"))
        pathlib.Path(os.path.join(target, ".git", "config")).write_text(
            "[stale]\n", encoding="utf-8"
        )
        self.addCleanup(remove_tree, target, True)

        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {
                "project": self.project.pk,
                "slug": "stale-target",
                "name": self.component.name,
            },
        )

        self.assertRedirects(response, "/projects/test/stale-target/")
        component = Component.objects.get(pk=self.component.pk)
        config = pathlib.Path(component.full_path) / ".git" / "config"
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.isdir(component.full_path))
        self.assertTrue(config.is_file())
        self.assertNotIn("[stale]", config.read_text(encoding="utf-8"))

    def test_rename_project_locks_repositories_before_path_move(self) -> None:
        self.make_manager()
        other_component = self.create_json(project=self.project, name="JSON")
        expected_locks = {self.component.pk, other_component.pk}
        events: list[tuple[str, int]] = []
        original_lock_enter = RepositoryLock.__enter__
        original_lock_exit = RepositoryLock.__exit__
        original_atomic_exit = transaction.Atomic.__exit__
        original_rename = os.rename

        def record_lock_enter(lock):
            component = lock.repository.component
            if component is not None and component.pk in expected_locks:
                events.append(("repo_lock", component.pk))
            return original_lock_enter(lock)

        def record_lock_exit(lock, exc_type, exc_value, traceback):
            component = lock.repository.component
            if component is not None and component.pk in expected_locks:
                events.append(("repo_unlock", component.pk))
            return original_lock_exit(lock, exc_type, exc_value, traceback)

        def record_atomic_exit(atomic, exc_type, exc_value, traceback):
            events.append(("atomic_exit", 0))
            return original_atomic_exit(atomic, exc_type, exc_value, traceback)

        def record_rename(old_path, new_path):
            events.append(("rename", 0))
            return original_rename(old_path, new_path)

        with (
            patch.object(
                RepositoryLock,
                "__enter__",
                autospec=True,
                side_effect=record_lock_enter,
            ),
            patch.object(
                RepositoryLock,
                "__exit__",
                autospec=True,
                side_effect=record_lock_exit,
            ),
            patch.object(
                transaction.Atomic,
                "__exit__",
                autospec=True,
                side_effect=record_atomic_exit,
            ),
            patch("weblate.trans.mixins.os.rename", side_effect=record_rename),
        ):
            response = self.client.post(
                reverse("rename", kwargs={"path": self.project.get_url_path()}),
                {"slug": "locked-project", "name": self.project.name},
            )

        self.assertRedirects(response, "/projects/locked-project/")
        rename_index = events.index(("rename", 0))
        self.assertEqual(
            {
                component_pk
                for event, component_pk in events[:rename_index]
                if event == "repo_lock"
            },
            expected_locks,
        )
        atomic_exit_index = next(
            index
            for index, event in enumerate(events)
            if index > rename_index and event == ("atomic_exit", 0)
        )
        for event in expected_locks:
            unlock_index = events.index(("repo_unlock", event))
            self.assertLess(atomic_exit_index, unlock_index)

    def test_rename_category_locks_linked_repository_before_path_move(self) -> None:
        self.make_manager()
        category = Category.objects.create(
            project=self.project, name="Category test", slug="testcat"
        )
        self.create_link_existing(category=category)
        events: list[tuple[str, int]] = []
        original_lock_enter = RepositoryLock.__enter__
        original_rename = os.rename

        def record_lock_enter(lock):
            component = lock.repository.component
            if component is not None:
                events.append(("repo_lock", component.pk))
            return original_lock_enter(lock)

        def record_rename(old_path, new_path):
            events.append(("rename", 0))
            return original_rename(old_path, new_path)

        with (
            patch.object(
                RepositoryLock,
                "__enter__",
                autospec=True,
                side_effect=record_lock_enter,
            ),
            patch("weblate.trans.mixins.os.rename", side_effect=record_rename),
        ):
            response = self.client.post(
                reverse("rename", kwargs={"path": category.get_url_path()}),
                {
                    "project": self.project.pk,
                    "category": "",
                    "slug": "renamed-category",
                    "name": category.name,
                },
            )

        self.assertRedirects(response, "/projects/test/renamed-category/")
        rename_index = events.index(("rename", 0))
        self.assertIn(("repo_lock", self.component.pk), events[:rename_index])
        self.assertEqual(
            self.project.change_set.get(
                action=ActionEvents.RENAME_CATEGORY,
                old="testcat",
                target="renamed-category",
            ).user,
            self.user,
        )

    def test_rename_project_missing_source_path(self) -> None:
        self.make_manager()
        old_path = self.project.full_path
        original_rename = os.rename

        def move_source(old_path, new_path):
            original_rename(old_path, new_path)
            raise FileNotFoundError(2, "No such file or directory", old_path, new_path)

        with patch("weblate.trans.mixins.os.rename", side_effect=move_source):
            response = self.client.post(
                reverse("rename", kwargs={"path": self.project.get_url_path()}),
                {"slug": "missing-source", "name": self.project.name},
            )

        self.assertRedirects(response, "/projects/missing-source/")
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.slug, "missing-source")
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.isdir(project.full_path))

    def test_rename_project_requires_destination_on_missing_source(self) -> None:
        self.make_manager()

        def remove_source(old_path, new_path):
            remove_tree(old_path, ignore_errors=True)
            raise FileNotFoundError(2, "No such file or directory", old_path, new_path)

        with (
            patch("weblate.trans.mixins.os.rename", side_effect=remove_source),
            self.assertRaises(FileNotFoundError),
        ):
            self.client.post(
                reverse("rename", kwargs={"path": self.project.get_url_path()}),
                {"slug": "missing-source", "name": self.project.name},
            )

        self.assertFalse(Project.objects.filter(slug="missing-source").exists())

    def test_rename_project_keeps_destination_file_not_found(self) -> None:
        self.make_manager()
        old_path = self.project.full_path

        with (
            patch(
                "weblate.trans.mixins.os.rename",
                side_effect=FileNotFoundError(2, "No such file or directory", old_path),
            ),
            self.assertRaises(FileNotFoundError),
        ):
            self.client.post(
                reverse("rename", kwargs={"path": self.project.get_url_path()}),
                {"slug": "missing-destination", "name": self.project.name},
            )

        self.assertTrue(os.path.exists(old_path))

    def test_rename_component_locks_component_before_binding_form(self) -> None:
        self.make_manager()
        events: list[tuple[str, int]] = []
        original_get_for_update = ComponentQuerySet.get_for_update
        original_form_init = ComponentRenameForm.__init__

        def record_get_for_update(*args, **kwargs):
            events.append(("lock", kwargs["pk"]))
            return original_get_for_update(*args, **kwargs)

        def record_form_init(*args, **kwargs):
            events.append(("form_init", kwargs["instance"].pk))
            return original_form_init(*args, **kwargs)

        with (
            patch.object(
                ComponentQuerySet,
                "get_for_update",
                autospec=True,
                side_effect=record_get_for_update,
            ),
            patch.object(
                ComponentRenameForm,
                "__init__",
                autospec=True,
                side_effect=record_form_init,
            ),
        ):
            response = self.client.post(
                reverse("rename", kwargs=self.kw_component),
                {
                    "project": self.project.pk,
                    "slug": "locked-rename",
                    "name": self.component.name,
                },
            )

        self.assertRedirects(response, "/projects/test/locked-rename/")
        lock_index = events.index(("lock", self.component.pk))
        form_init_index = events.index(("form_init", self.component.pk))
        self.assertLess(
            lock_index,
            form_init_index,
            "Component row should be locked before the bound rename form is created",
        )

    def test_rename_component_acquires_repository_lock_before_row_lock(self) -> None:
        self.make_manager()
        events: list[tuple[str, int]] = []
        original_lock_enter = RepositoryLock.__enter__
        original_get_for_update = ComponentQuerySet.get_for_update

        def record_lock_enter(lock):
            component = lock.repository.component
            if component is not None:
                events.append(("repo_lock", component.pk))
            return original_lock_enter(lock)

        def record_get_for_update(*args, **kwargs):
            events.append(("row_lock", kwargs["pk"]))
            return original_get_for_update(*args, **kwargs)

        with (
            patch.object(
                RepositoryLock,
                "__enter__",
                autospec=True,
                side_effect=record_lock_enter,
            ),
            patch.object(
                ComponentQuerySet,
                "get_for_update",
                autospec=True,
                side_effect=record_get_for_update,
            ),
        ):
            response = self.client.post(
                reverse("rename", kwargs=self.kw_component),
                {
                    "project": self.project.pk,
                    "slug": "repo-locked-rename",
                    "name": self.component.name,
                },
            )

        self.assertRedirects(response, "/projects/test/repo-locked-rename/")
        self.assertLess(
            events.index(("repo_lock", self.component.pk)),
            events.index(("row_lock", self.component.pk)),
            "Component repository lock should be acquired before the row lock",
        )

    def test_rename_project(self) -> None:
        # Remove stale dir from previous tests
        target = os.path.join(data_dir("vcs"), "xxxx")
        if os.path.exists(target):
            remove_tree(target)
        self.make_manager()
        self.assertContains(
            self.client.get(self.project.get_absolute_url()), "#organize"
        )
        response = self.client.post(
            reverse("rename", kwargs={"path": self.project.get_url_path()}),
            {"slug": "xxxx", "name": self.project.name},
        )
        self.assertRedirects(response, "/projects/xxxx/")
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.slug, "xxxx")
        self.assertEqual(
            project.change_set.get(action=ActionEvents.RENAME_PROJECT).user, self.user
        )
        for component in project.component_set.iterator():
            self.assertIsNotNone(component.repository.last_remote_revision)
            response = self.client.get(component.get_absolute_url())
            self.assertContains(response, "/projects/xxxx/")

        # Test rename redirect in middleware
        response = self.client.get(self.project.get_absolute_url())
        self.assertRedirects(response, project.get_absolute_url(), status_code=301)

    def test_rename_project_conflict(self) -> None:
        # Test rename conflict
        self.make_manager()
        Project.objects.create(name="Other project", slug="other")
        response = self.client.post(
            reverse("rename", kwargs={"path": self.project.get_url_path()}),
            {"slug": "other", "name": self.project.name},
            follow=True,
        )
        self.assertContains(response, "Project with this URL slug already exists.")

    def test_rename_component_conflict(self) -> None:
        # Test rename conflict
        self.make_manager()
        self.create_link_existing()
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {"project": self.project.pk, "slug": "test2", "name": self.component.name},
            follow=True,
        )
        self.assertContains(
            response,
            "Component or category with the same URL slug already exists at this level.",
        )


class AnnouncementPermissionTestCase(ViewTestCase):
    data: ClassVar[dict[str, str]] = {
        "message": "Announcement testing",
        "severity": "warning",
    }
    outbox = 0

    def set_user_permissions(self) -> None:
        group = Group.objects.create(
            name="Coordinators",
            defining_project=self.project,
            language_selection=SELECTION_ALL,
        )
        group.roles.add(Role.objects.get(name="Translation coordinator"))
        group.projects.add(self.project)
        group.user_set.add(self.user)

    def perform_test(self, url) -> None:
        response = self.client.post(url, self.data, follow=True)
        self.assertEqual(response.status_code, 403)

        self.set_user_permissions()

        # Add second user to receive notifications
        self.project.add_user(self.anotheruser, "Administration")
        czech = Language.objects.get(code="cs")
        self.anotheruser.profile.languages.add(czech)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, self.data, follow=True)
        self.assertContains(response, self.data["message"])
        self.assertEqual(len(mail.outbox), self.outbox)

    def test_translation(self) -> None:
        url = reverse("announcement", kwargs=self.kw_translation)
        self.perform_test(url)

    def test_component(self) -> None:
        url = reverse("announcement", kwargs=self.kw_component)
        self.perform_test(url)

    def test_project(self) -> None:
        url = reverse("announcement", kwargs={"path": self.project.get_url_path()})
        self.perform_test(url)

    def test_project_language(self) -> None:
        czech = Language.objects.get(code="cs")
        project_language = ProjectLanguage(project=self.project, language=czech)
        url = reverse("announcement", kwargs={"path": project_language.get_url_path()})
        self.perform_test(url)
        announcement = Announcement.objects.get(message=self.data["message"])
        self.assertEqual(announcement.project, self.project)
        self.assertEqual(announcement.language, czech)
        self.assertIsNone(announcement.category)
        self.assertIsNone(announcement.component)

    def test_category(self) -> None:
        category = Category(
            project=self.project, name="Test Category", slug="test-category"
        )
        category.save()
        url = reverse("announcement", kwargs={"path": category.get_url_path()})
        self.perform_test(url)
        announcement = Announcement.objects.get(message=self.data["message"])
        self.assertEqual(announcement.category, category)
        self.assertIsNone(announcement.project)

    def test_category_language(self) -> None:
        parent = self.create_category(self.project)
        category = self.create_category(self.project, category=parent)
        self.component.category = category
        self.component.save(update_fields=["category"])
        obj = CategoryLanguage(category, Language.objects.get(code="cs"))
        url = reverse("announcement", kwargs={"path": obj.get_url_path()})

        response = self.client.get(obj.get_absolute_url())
        self.assertNotContains(response, 'data-bs-target="#announcement"')
        self.assertIsNone(response.context["announcement_form"])
        self.perform_test(url)

        announcement = Announcement.objects.get(message=self.data["message"])
        self.assertEqual(announcement.category, category)
        self.assertEqual(announcement.language, obj.language)
        self.assertIsNone(announcement.project)
        self.assertIsNone(announcement.component)
        Announcement.objects.create(
            category=parent, language=obj.language, message="Inherited announcement"
        )
        Announcement.objects.create(
            project=self.project, message="Project announcement"
        )
        Announcement.objects.create(
            category=category,
            language=Language.objects.get(code="de"),
            message="Other language announcement",
        )
        response = self.client.get(obj.get_absolute_url())
        self.assertContains(response, 'data-bs-target="#announcement"')
        self.assertIsNotNone(response.context["announcement_form"])
        banners = fromstring(response.content).find_class("announcement")
        self.assertEqual(len(banners), 3)
        for banner, message in zip(
            banners,
            (self.data["message"], "Inherited announcement", "Project announcement"),
            strict=True,
        ):
            self.assertIn(message, banner.text_content())

    def test_category_language_invalid(self) -> None:
        self.set_user_permissions()
        parent = self.create_category(self.project)
        category = self.create_category(self.project, category=parent)
        self.component.category = category
        self.component.save(update_fields=["category"])
        obj = CategoryLanguage(category, Language.objects.get(code="cs"))
        url = reverse("announcement", kwargs={"path": obj.get_url_path()})

        response = self.client.post(url, {"severity": "warning"})

        self.assertRedirects(response, f"{obj.get_absolute_url()}#announcement")
        self.assertFalse(Announcement.objects.exists())

    def test_category_language_limited_permissions(self) -> None:
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save(update_fields=["category"])
        czech = Language.objects.get(code="cs")
        group = Group.objects.create(
            name="Czech announcement coordinators",
            defining_project=self.project,
            language_selection=SELECTION_MANUAL,
        )
        group.roles.add(Role.objects.get(name="Translation coordinator"))
        group.projects.add(self.project)
        group.languages.add(czech)
        group.user_set.add(self.user)

        for language in (Language.objects.get(code="de"), czech):
            with self.subTest(language=language):
                obj = CategoryLanguage(category, language)
                response = self.client.get(obj.get_absolute_url())
                self.assertEqual(
                    response.context["announcement_form"] is not None,
                    language == czech,
                )
                response = self.client.post(
                    reverse("announcement", kwargs={"path": obj.get_url_path()}),
                    {"message": "Scoped permission test", "severity": "info"},
                )
                if language == czech:
                    self.assertRedirects(response, obj.get_absolute_url())
                else:
                    self.assertEqual(response.status_code, 403)
                    self.assertFalse(Announcement.objects.exists())

    def test_delete_announcement(self) -> None:
        second_component = self.create_link_existing()

        announcement = Announcement.objects.create(
            message="test component",
            component=self.component,
            project=self.project,
        )
        second_announcement = Announcement.objects.create(
            message="test second announcement",
            component=second_component,
            project=self.project,
        )
        project_announcement = Announcement.objects.create(
            message="test project announcement",
            project=self.project,
        )
        category = Category.objects.create(
            project=self.project, name="Test Category", slug="test-category"
        )
        category_announcement = Announcement.objects.create(
            message="test category announcement",
            category=category,
        )

        group = Group.objects.create(
            name="Component deleters",
            defining_project=self.project,
            project_selection=SELECTION_MANUAL,
            language_selection=SELECTION_ALL,
        )
        group.roles.add(Role.objects.get(name="Translation coordinator"))
        group.components.add(self.component)
        self.user.groups.add(group)

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": announcement.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Announcement.objects.filter(pk=announcement.pk).count(), 0)

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": second_announcement.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            Announcement.objects.filter(pk=second_announcement.pk).count(), 1
        )

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": project_announcement.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            Announcement.objects.filter(pk=project_announcement.pk).count(), 1
        )

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": category_announcement.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            Announcement.objects.filter(pk=category_announcement.pk).count(), 1
        )

        group.project_selection = SELECTION_ALL
        group.components.clear()
        group.save()
        self.user.clear_permissions_cache()

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": second_announcement.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Announcement.objects.filter(pk=second_announcement.pk).count(), 0
        )

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": project_announcement.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Announcement.objects.filter(pk=project_announcement.pk).count(), 0
        )

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": category_announcement.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Announcement.objects.filter(pk=category_announcement.pk).count(), 0
        )
        self.assertEqual(Announcement.objects.count(), 0)

    def test_delete_global_announcement(self) -> None:
        announcement = Announcement.objects.create(message="test global")

        group = Group.objects.create(
            name="Project deleters",
            defining_project=self.project,
            language_selection=SELECTION_ALL,
        )
        group.roles.add(Role.objects.get(name="Translation coordinator"))
        group.projects.add(self.project)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        self.client.post(reverse("announcement-delete", kwargs={"pk": announcement.pk}))
        self.assertEqual(Announcement.objects.count(), 1)

        self.user.is_superuser = True
        self.user.save()
        self.user.clear_permissions_cache()

        self.client.post(reverse("announcement-delete", kwargs={"pk": announcement.pk}))
        self.assertEqual(Announcement.objects.count(), 0)

    def test_language_announcement(self) -> None:
        czech = Language.objects.get(code="cs")
        announcement = Announcement.objects.create(
            language=czech, message="test language"
        )

        response = self.client.get(
            reverse("show_language", kwargs={"lang": czech.code})
        )
        self.assertContains(response, "test language")

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": announcement.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Announcement.objects.count(), 1)

        self.user.is_superuser = True
        self.user.save()
        self.user.clear_permissions_cache()

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": announcement.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Announcement.objects.count(), 0)


class CategoryLanguageAnnouncementTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.target_project = self.create_project("Shared", "shared")
        self.parent = self.create_category(self.target_project)
        self.category = self.create_category(self.target_project, category=self.parent)
        ComponentLink.objects.create(
            component=self.component,
            project=self.target_project,
            category=self.category,
        )
        self.czech = Language.objects.get(code="cs")
        self.german = Language.objects.get(code="de")
        self.group = Group.objects.create(
            name="Category announcement coordinators",
            defining_project=self.target_project,
            language_selection=SELECTION_MANUAL,
        )
        self.group.roles.add(Role.objects.get(name="Translation coordinator"))
        self.group.projects.add(self.target_project)
        self.group.languages.add(self.czech)
        self.group.user_set.add(self.user)

    def test_shared_category_permissions(self) -> None:
        obj = CategoryLanguage(self.category, self.czech)
        self.assertFalse(obj.has_action_translations)
        self.assertTrue(obj.translation_set)
        response = self.client.get(obj.get_absolute_url())
        self.assertContains(response, 'data-bs-target="#announcement"')
        self.assertIsNotNone(response.context["announcement_form"])

        response = self.client.post(
            reverse("announcement", kwargs={"path": obj.get_url_path()}),
            {"message": "Shared category announcement", "severity": "info"},
            follow=True,
        )
        self.assertRedirects(response, obj.get_absolute_url())
        self.assertContains(response, "Shared category announcement")
        announcement = Announcement.objects.get(message="Shared category announcement")
        self.assertEqual(announcement.category, self.category)
        self.assertEqual(announcement.language, self.czech)

        # Source-project rights do not grant authority over a linking category.
        self.group.projects.set([self.project])
        self.user.clear_permissions_cache()
        response = self.client.get(obj.get_absolute_url())
        self.assertIsNone(response.context["announcement_form"])
        response = self.client.post(
            reverse("announcement", kwargs={"path": obj.get_url_path()}),
            {"message": "Unauthorized announcement", "severity": "info"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Announcement.objects.filter(message="Unauthorized announcement").exists()
        )
        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": announcement.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Announcement.objects.filter(pk=announcement.pk).exists())

    def test_delete_language_limits(self) -> None:
        owned_category = self.create_category(self.project)
        self.component.category = owned_category
        self.component.save(update_fields=["category"])
        self.group.projects.add(self.project)
        membership = TeamMembership.objects.get(user=self.user, group=self.group)

        for limit in ("team", "membership"):
            if limit == "membership":
                self.group.language_selection = SELECTION_ALL
                self.group.save(update_fields=["language_selection"])
                membership.limit_languages.add(self.czech)
            for category in (owned_category, self.category):
                for language in (self.german, self.czech):
                    with self.subTest(
                        limit=limit, category=category, language=language
                    ):
                        self.user.clear_permissions_cache()
                        obj = CategoryLanguage(category, language)
                        announcement = Announcement.objects.create(
                            category=category,
                            language=language,
                            message="Scoped deletion",
                        )
                        url = reverse(
                            "announcement-delete", kwargs={"pk": announcement.pk}
                        )
                        response = self.client.get(obj.get_absolute_url())
                        self.assertEqual(
                            response.context["announcement_form"] is not None,
                            language == self.czech,
                        )
                        if language == self.czech:
                            self.assertContains(response, f'data-action="{url}"')
                        else:
                            self.assertNotContains(response, f'data-action="{url}"')
                        response = self.client.post(url)
                        self.assertEqual(
                            response.status_code, 200 if language == self.czech else 403
                        )
                        self.assertEqual(
                            Announcement.objects.filter(pk=announcement.pk).exists(),
                            language != self.czech,
                        )

    def test_delete_after_last_translation_unlinked(self) -> None:
        announcements = [
            Announcement.objects.create(
                category=self.category,
                language=language,
                message="Orphaned announcement",
            )
            for language in (self.czech, self.german)
        ]
        ComponentLink.objects.filter(category=self.category).delete()
        obj = CategoryLanguage(self.category, self.czech)
        self.assertFalse(obj.translation_set)

        response = self.client.get(obj.get_absolute_url())
        self.assertIsNone(response.context["announcement_form"])
        response = self.client.post(
            reverse("announcement", kwargs={"path": obj.get_url_path()}),
            {"message": "Empty category announcement", "severity": "info"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Announcement.objects.filter(message="Empty category announcement").exists()
        )

        for language, announcement in zip(
            (self.czech, self.german), announcements, strict=True
        ):
            with self.subTest(language=language):
                url = reverse("announcement-delete", kwargs={"pk": announcement.pk})
                obj = CategoryLanguage(self.category, language)
                response = self.client.get(obj.get_absolute_url())
                if language == self.czech:
                    self.assertContains(response, f'data-action="{url}"')
                else:
                    self.assertNotContains(response, f'data-action="{url}"')
                response = self.client.post(url)
                allowed = language == self.czech
                self.assertEqual(response.status_code, 200 if allowed else 403)
                self.assertEqual(
                    Announcement.objects.filter(pk=announcement.pk).exists(),
                    not allowed,
                )

    def test_linked_translation_announcements(self) -> None:
        for category in (self.parent, self.category):
            for language in (None, self.czech, self.german):
                Announcement.objects.create(
                    category=category,
                    language=language,
                    message=f"Linked category {category.pk} {language}",
                )
        expected = [
            f"Linked category {category.pk} {language}"
            for category in (self.parent, self.category)
            for language in (None, self.czech)
        ]
        self.assertCountEqual(
            Announcement.objects.context_filter(
                component=self.component, language=self.czech
            ).values_list("message", flat=True),
            expected,
        )
        translation = self.component.translation_set.get(language=self.czech)
        response = self.client.get(translation.get_absolute_url())
        banners = fromstring(response.content).find_class("announcement")
        self.assertEqual(len(banners), len(expected))
        for banner, message in zip(banners, expected, strict=True):
            self.assertIn(message, banner.text_content())

        # A link from a private project must not expose its announcements to
        # users who can only access the original component.
        self.target_project.access_control = Project.ACCESS_PRIVATE
        self.target_project.save(update_fields=["access_control"])
        self.group.user_set.remove(self.user)
        self.user.clear_permissions_cache()
        response = self.client.get(translation.get_absolute_url())
        self.assertFalse(fromstring(response.content).find_class("announcement"))

        self.group.user_set.add(self.user)
        self.user.clear_permissions_cache()
        response = self.client.get(translation.get_absolute_url())
        self.assertEqual(
            len(fromstring(response.content).find_class("announcement")), len(expected)
        )


class AnnouncementTest(AnnouncementPermissionTestCase):
    def set_user_permissions(self) -> None:
        self.make_manager()

    def test_delete(self) -> None:
        self.test_project()
        message = Announcement.objects.all()[0]
        self.client.post(reverse("announcement-delete", kwargs={"pk": message.pk}))
        self.assertEqual(Announcement.objects.count(), 0)

    def test_delete_deny(self) -> None:
        message = Announcement.objects.create(message="test")
        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": message.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Announcement.objects.count(), 1)

    def test_delete_hides_private_announcement(self) -> None:
        private_project = self.create_project(
            name="Private announcement",
            slug="private-announcement",
            access_control=Project.ACCESS_PRIVATE,
        )
        private_component = self.create_po(
            project=private_project, name="private-announcement"
        )
        announcement = Announcement.objects.create(
            project=private_project,
            component=private_component,
            message="Hidden announcement",
        )

        response = self.client.post(
            reverse("announcement-delete", kwargs={"pk": announcement.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Announcement.objects.count(), 1)


class AnnouncementNotifyTest(AnnouncementTest):
    data: ClassVar[dict[str, str]] = {
        "message": "Announcement testing",
        "severity": "warning",
        "notify": "1",
    }
    outbox = 1
