# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for check views."""

from django.urls import reverse

from weblate.checks.models import Check
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.workspaces.models import Workspace


class ChecksViewTest(FixtureTestCase):
    """Testing of check views."""

    def test_browse(self) -> None:
        response = self.client.get(reverse("checks"))
        self.assertContains(response, "/same/")

        response = self.client.get(reverse("checks"), kwargs={"path": ("-", "-", "de")})
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse("checks"), kwargs={"path": self.project.get_url_path()}
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse("checks"), kwargs={"path": self.component.get_url_path()}
        )
        self.assertContains(response, "/same/")

    def test_check(self) -> None:
        response = self.client.get(reverse("checks", kwargs={"name": "same"}))
        self.assertContains(response, "/same/")

        response = self.client.get(reverse("checks", kwargs={"name": "ellipsis"}))
        self.assertContains(response, "checks.html#check-ellipsis")

        response = self.client.get(reverse("checks", kwargs={"name": "not-existing"}))
        self.assertEqual(response.status_code, 404)

        self.client.get(
            reverse("checks", kwargs={"name": "same"}),
            {"project": self.project.slug},
        )

    def test_project(self) -> None:
        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": self.project.get_url_path()},
            )
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": self.project.get_url_path()},
            ),
            {"lang": "cs"},
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "ellipsis", "path": self.project.get_url_path()},
            )
        )
        self.assertContains(response, "checks.html#check-ellipsis")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "non-existing", "path": self.project.get_url_path()},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_workspace(self) -> None:
        workspace = Workspace.objects.create(name="Checks workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])

        response = self.client.get(
            reverse("checks", kwargs={"path": workspace.get_url_path()})
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": workspace.get_url_path()},
            )
        )
        self.assertContains(response, "/same/")
        self.assertContains(response, self.project.name)

        response = self.client.get(
            reverse(
                "checks",
                kwargs={
                    "name": "non-existing",
                    "path": workspace.get_url_path(),
                },
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_workspace_restricted_component(self) -> None:
        workspace = Workspace.objects.create(name="Restricted checks workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.user.clear_permissions_cache()

        self.assertTrue(Check.objects.filter(name="same").exists())

        response = self.client.get(
            reverse("checks", kwargs={"path": workspace.get_url_path()})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/same/", status_code=200)

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": workspace.get_url_path()},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse(
                "checks",
                kwargs={"name": "same", "path": self.project.get_url_path()},
            ),
            status_code=200,
        )

    def test_restricted_component_hidden_in_existing_scopes(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.user.clear_permissions_cache()
        language = self.translation.language
        project_language_path = [*self.project.get_url_path(), "-", language.code]

        project_check_url = reverse(
            "checks",
            kwargs={"name": "same", "path": self.project.get_url_path()},
        )
        language_check_url = reverse(
            "checks",
            kwargs={"name": "same", "path": language.get_url_path()},
        )
        project_language_check_url = reverse(
            "checks",
            kwargs={"name": "same", "path": project_language_path},
        )
        translation_check_url = reverse(
            "checks",
            kwargs={"name": "same", "path": self.translation.get_url_path()},
        )

        self.assertTrue(Check.objects.filter(name="same").exists())

        response = self.client.get(
            reverse("checks", kwargs={"path": self.project.get_url_path()})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, project_check_url, status_code=200)

        response = self.client.get(reverse("checks", kwargs={"name": "same"}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, project_check_url, status_code=200)

        response = self.client.get(
            reverse("checks", kwargs={"path": language.get_url_path()})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, language_check_url, status_code=200)

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": language.get_url_path()},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, project_language_check_url, status_code=200)

        response = self.client.get(
            reverse("checks", kwargs={"path": project_language_path})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, project_language_check_url, status_code=200)

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": project_language_path},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, translation_check_url, status_code=200)

    def test_component(self) -> None:
        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": self.component.get_url_path()},
            )
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={
                    "name": "multiple_failures",
                    "path": self.component.get_url_path(),
                },
            )
        )
        self.assertContains(response, "/multiple_failures/")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "non-existing", "path": self.component.get_url_path()},
            )
        )
        self.assertEqual(response.status_code, 404)
