# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for saved searches."""

from __future__ import annotations

from typing import TYPE_CHECKING

from crispy_forms.utils import render_crispy_form
from django.urls import reverse

from weblate.trans.forms import AutoForm, BulkEditForm, DownloadForm
from weblate.trans.models import Project, SavedSearch
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.search import MAX_SEARCH_QUERY_LENGTH

if TYPE_CHECKING:
    from weblate.auth.models import User


class SavedSearchTestCase(FixtureTestCase):
    def create_project_search(
        self, project: Project | None = None, **kwargs: str
    ) -> SavedSearch:
        kwargs.setdefault("name", "Project search")
        kwargs.setdefault("query", "priority:>100")
        return SavedSearch.objects.create(project=project or self.project, **kwargs)

    def create_user_search(
        self, user: User | None = None, **kwargs: str
    ) -> SavedSearch:
        kwargs.setdefault("name", "My search")
        kwargs.setdefault("query", "state:<translated")
        return SavedSearch.objects.create(user=user or self.user, **kwargs)


class ProjectSavedSearchTest(SavedSearchTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.list_url = reverse("project-saved-searches", kwargs=self.kw_project)

    def test_permission(self) -> None:
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            self.list_url, {"name": "Search", "query": "state:<translated"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(SavedSearch.objects.exists())

    def test_create(self) -> None:
        self.make_manager()
        response = self.client.post(
            self.list_url,
            {
                "name": "Important",
                "query": "priority:>100",
                "description": "Strings to translate first",
            },
            follow=True,
        )
        self.assertRedirects(response, self.list_url)
        self.assertContains(response, "Important")
        saved_search = SavedSearch.objects.get()
        self.assertEqual(saved_search.project, self.project)
        self.assertIsNone(saved_search.user)

    def test_create_duplicate(self) -> None:
        self.make_manager()
        self.create_project_search(name="Important")
        # The same name in user scope does not conflict
        self.create_user_search(name="Important")
        response = self.client.post(
            self.list_url, {"name": "Important", "query": "state:<translated"}
        )
        self.assertContains(response, "A saved search with this name already exists.")
        self.assertEqual(SavedSearch.objects.count(), 2)

    def test_create_invalid_query(self) -> None:
        self.make_manager()
        response = self.client.post(
            self.list_url, {"name": "Broken", "query": "invalidfield:x"}
        )
        self.assertContains(response, "Could not parse query string")
        self.assertFalse(SavedSearch.objects.exists())

    def test_edit(self) -> None:
        self.make_manager()
        saved_search = self.create_project_search()
        response = self.client.post(
            reverse(
                "project-saved-search-edit",
                kwargs={"project": self.project.slug, "pk": saved_search.pk},
            ),
            {"name": "Renamed", "query": "state:approved"},
        )
        self.assertRedirects(response, self.list_url)
        saved_search.refresh_from_db()
        self.assertEqual(saved_search.name, "Renamed")
        self.assertEqual(saved_search.query, "state:approved")

    def test_edit_user_search(self) -> None:
        self.make_manager()
        saved_search = self.create_user_search()
        response = self.client.get(
            reverse(
                "project-saved-search-edit",
                kwargs={"project": self.project.slug, "pk": saved_search.pk},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_delete(self) -> None:
        saved_search = self.create_project_search()
        delete_url = reverse(
            "project-saved-search-delete",
            kwargs={"project": self.project.slug, "pk": saved_search.pk},
        )
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(SavedSearch.objects.exists())

        self.make_manager()
        response = self.client.post(delete_url)
        self.assertRedirects(response, self.list_url)
        self.assertFalse(SavedSearch.objects.exists())


class UserSavedSearchTest(SavedSearchTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.create_url = reverse("saved-search-create")
        self.profile_url = reverse("profile")
        self.list_url = f"{self.profile_url}#searches"

    def test_create(self) -> None:
        response = self.client.post(
            self.create_url, {"name": "Mine", "query": "state:<translated"}
        )
        self.assertRedirects(response, self.list_url)
        saved_search = SavedSearch.objects.get()
        self.assertEqual(saved_search.user, self.user)
        self.assertIsNone(saved_search.project)

    def test_profile_tab(self) -> None:
        self.create_user_search(name="Mine")
        response = self.client.get(self.profile_url)
        self.assertContains(response, 'id="profile-tab-searches"')
        self.assertContains(response, "Mine")
        self.assertContains(
            response,
            f'href="{self.create_url}?next=%2Faccounts%2Fprofile%2F%23searches"',
        )

    def test_prefill(self) -> None:
        response = self.client.get(self.create_url, {"q": "has:comment"})
        self.assertContains(response, "has:comment")

    def test_create_duplicate(self) -> None:
        self.create_user_search(name="Mine")
        # The same name of another user does not conflict
        other = self.anotheruser
        self.create_user_search(user=other, name="Other")
        response = self.client.post(
            self.create_url, {"name": "Mine", "query": "state:approved"}
        )
        self.assertContains(response, "A saved search with this name already exists.")
        response = self.client.post(
            self.create_url, {"name": "Other", "query": "state:approved"}
        )
        self.assertRedirects(response, self.list_url)

    def test_isolation(self) -> None:
        other = self.anotheruser
        saved_search = self.create_user_search(user=other, name="Not mine")
        response = self.client.get(self.profile_url)
        self.assertNotContains(response, "Not mine")
        response = self.client.get(
            reverse("saved-search-edit", kwargs={"pk": saved_search.pk})
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse("saved-search-delete", kwargs={"pk": saved_search.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(SavedSearch.objects.filter(pk=saved_search.pk).exists())

    def test_edit_delete(self) -> None:
        saved_search = self.create_user_search()
        response = self.client.post(
            reverse("saved-search-edit", kwargs={"pk": saved_search.pk}),
            {"name": "Renamed", "query": "state:approved"},
        )
        self.assertRedirects(response, self.list_url)
        saved_search.refresh_from_db()
        self.assertEqual(saved_search.name, "Renamed")

        response = self.client.post(
            reverse("saved-search-delete", kwargs={"pk": saved_search.pk})
        )
        self.assertRedirects(response, self.list_url)
        self.assertFalse(SavedSearch.objects.exists())

    def test_anonymous(self) -> None:
        self.client.logout()
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 302)


class SavedSearchCreateTest(SavedSearchTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.create_url = reverse("saved-search-create")
        self.next_url = reverse("translate", kwargs=self.kw_translation)

    def test_user_scope(self) -> None:
        response = self.client.get(
            self.create_url, {"q": "has:comment", "project": self.project.slug}
        )
        self.assertContains(response, "has:comment")
        # Project scope is not offered without permission
        self.assertNotContains(response, "Everybody in project")

        response = self.client.post(
            self.create_url,
            {
                "name": "Comments",
                "query": "has:comment",
                "project": self.project.slug,
                "scope": "project",
                "next": self.next_url,
            },
        )
        self.assertRedirects(response, self.next_url)
        saved_search = SavedSearch.objects.get()
        self.assertEqual(saved_search.user, self.user)
        self.assertIsNone(saved_search.project)

    def test_rejects_long_query(self) -> None:
        response = self.client.post(
            self.create_url,
            {"name": "Long", "query": "x" * (MAX_SEARCH_QUERY_LENGTH + 1)},
        )
        self.assertContains(response, "Ensure this value has at most 2048 characters")
        self.assertFalse(SavedSearch.objects.exists())

    def test_project_scope(self) -> None:
        self.make_manager()
        response = self.client.get(
            self.create_url, {"q": "has:comment", "project": self.project.slug}
        )
        self.assertContains(response, "Everybody in project")

        response = self.client.post(
            self.create_url,
            {
                "name": "Comments",
                "query": "has:comment",
                "project": self.project.slug,
                "scope": "project",
                "next": self.next_url,
            },
        )
        self.assertRedirects(response, self.next_url)
        saved_search = SavedSearch.objects.get()
        self.assertEqual(saved_search.project, self.project)
        self.assertIsNone(saved_search.user)

    def test_unsafe_next(self) -> None:
        response = self.client.post(
            self.create_url,
            {
                "name": "Comments",
                "query": "has:comment",
                "next": "https://example.com/",
            },
        )
        self.assertRedirects(response, f"{reverse('profile')}#searches")


class SavedSearchDropdownTest(SavedSearchTestCase):
    def test_translate(self) -> None:
        self.create_project_search(name="Project filter")
        self.create_user_search(name="Personal filter")
        response = self.client.get(reverse("translate", kwargs=self.kw_translation))
        self.assertContains(response, "Project searches")
        self.assertContains(response, "Project filter")
        self.assertContains(response, "My searches")
        self.assertContains(response, "Personal filter")
        self.assertContains(response, "data-save-search")
        self.assertContains(response, f'data-project="{self.project.slug}"')

    def test_other_scopes_hidden(self) -> None:
        other_project = Project.objects.create(name="Other", slug="other")
        self.create_project_search(project=other_project, name="Foreign filter")
        self.create_user_search(user=self.anotheruser, name="Foreign user")
        response = self.client.get(reverse("search", kwargs=self.kw_project_path))
        self.assertNotContains(response, "Foreign filter")
        self.assertNotContains(response, "Foreign user")
        self.assertNotContains(response, "Project searches")

    def test_site_search(self) -> None:
        self.create_project_search(name="Project filter")
        self.create_user_search(name="Personal filter")
        response = self.client.get(reverse("search"))
        # No project scope for site-wide search
        self.assertNotContains(response, "Project filter")
        self.assertContains(response, "Personal filter")

    def test_anonymous(self) -> None:
        self.create_project_search(name="Project filter")
        self.client.logout()
        response = self.client.get(reverse("search", kwargs=self.kw_project_path))
        self.assertContains(response, "Project filter")
        self.assertNotContains(response, "data-save-search")

    def test_operation_forms(self) -> None:
        self.create_project_search(name="Project filter")
        self.create_user_search(name="Personal filter")
        forms = {
            "download": DownloadForm(self.translation, user=self.user),
            "auto": AutoForm(self.component, user=self.user),
            "bulk": BulkEditForm(self.user, self.translation, project=self.project),
        }
        for name, form in forms.items():
            with self.subTest(form=name):
                html = render_crispy_form(form)
                self.assertIn("Project filter", html)
                self.assertIn("Personal filter", html)
                self.assertNotIn("data-save-search", html)

    def test_operation_forms_without_user(self) -> None:
        self.create_project_search(name="Project filter")
        self.create_user_search(name="Personal filter")
        html = render_crispy_form(
            BulkEditForm(None, self.component, project=self.project)
        )
        self.assertIn("Project filter", html)
        self.assertNotIn("Personal filter", html)
