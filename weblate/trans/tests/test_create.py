#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Test for creating projects and models."""


from django.test.utils import modify_settings
from django.urls import reverse

from weblate.lang.models import get_default_lang
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import create_test_billing, get_test_file
from weblate.vcs.git import GitRepository

TEST_ZIP = get_test_file("translations.zip")
TEST_INVALID_ZIP = get_test_file("invalid.zip")
TEST_HTML = get_test_file("cs.html")


class CreateTest(ViewTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Global setup to configure git committer
        GitRepository.global_setup()

    def assert_create_project(self, result):
        response = self.client.get(reverse("create-project"))
        match = "not have permission to create project"
        if result:
            self.assertNotContains(response, match)
        else:
            self.assertContains(response, match)

    def client_create_project(self, result, **kwargs):
        params = {
            "name": "Create Project",
            "slug": "create-project",
            "web": "https://weblate.org/",
        }
        params.update(kwargs)
        response = self.client.post(reverse("create-project"), params)
        if isinstance(result, str):
            self.assertRedirects(response, result)
        elif result:
            self.assertEqual(response.status_code, 302)
        else:
            self.assertEqual(response.status_code, 200)
        return response

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_create_project_billing(self):
        # No permissions without billing
        self.assert_create_project(False)
        self.client_create_project(reverse("create-project"))

        # Create empty billing
        billing = create_test_billing(self.user)
        self.assert_create_project(True)

        # Create one project
        self.client_create_project(False, billing=0)
        self.client_create_project(True, billing=billing.pk)

        # No more billings left
        self.client_create_project(
            reverse("create-project"), name="p2", slug="p2", billing=billing.pk
        )

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_project_admin(self):
        # No permissions without superuser
        self.assert_create_project(False)
        self.client_create_project(reverse("create-project"))

        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        # Now can create
        self.assert_create_project(True)
        self.client_create_project(True)
        self.client_create_project(True, name="p2", slug="p2")

    def assert_create_component(self, result):
        response = self.client.get(reverse("create-component-vcs"))
        match = "not have permission to create component"
        if result:
            self.assertNotContains(response, match)
        else:
            self.assertContains(response, match)

    def client_create_component(self, result, **kwargs):
        params = {
            "name": "Create Component",
            "slug": "create-component",
            "project": self.project.pk,
            "vcs": "git",
            "repo": self.component.get_repo_link_url(),
            "file_format": "po",
            "filemask": "po/*.po",
            "new_base": "po/project.pot",
            "new_lang": "add",
            "language_regex": "^[^.]+$",
            "source_language": get_default_lang(),
        }
        params.update(kwargs)
        response = self.client.post(reverse("create-component-vcs"), params)
        if result:
            self.assertEqual(response.status_code, 302)
        else:
            self.assertEqual(response.status_code, 200)
        return response

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_create_component_billing(self):
        # No permissions without billing
        self.assert_create_component(False)
        self.client_create_component(False)

        # Create billing and add permissions
        billing = create_test_billing(self.user)
        billing.projects.add(self.project)
        self.project.add_user(self.user, "@Administration")
        self.assert_create_component(True)

        # Create two components
        self.client_create_component(True)
        self.client_create_component(True, name="c2", slug="c2")

        # Restrict plan to test nothing more can be created
        billing.plan.limit_strings = 1
        billing.plan.save()

        self.client_create_component(False, name="c3", slug="c3")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_admin(self):
        # No permissions without superuser
        self.assert_create_component(False)
        self.client_create_component(False)

        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        # Now can create
        self.assert_create_component(True)
        self.client_create_component(True)
        self.client_create_component(True, name="c2", slug="c2")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_wizard(self):
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        # First step
        params = {
            "name": "Create Component",
            "slug": "create-component",
            "project": self.project.pk,
            "vcs": "git",
            "repo": self.component.repo,
            "source_language": get_default_lang(),
        }
        response = self.client.post(reverse("create-component-vcs"), params)
        self.assertContains(response, self.component.get_repo_link_url())
        self.assertContains(response, "po/*.po")

        # Display form
        params["discovery"] = "4"
        response = self.client.post(reverse("create-component-vcs"), params)
        self.assertContains(response, self.component.get_repo_link_url())
        self.assertContains(response, "po/*.po")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_existing(self):
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(
            reverse("create-component"),
            {
                "origin": "existing",
                "name": "Create Component",
                "slug": "create-component",
                "component": self.component.pk,
            },
            follow=True,
        )
        self.assertContains(response, self.component.get_repo_link_url())

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_branch_fail(self):
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(
            reverse("create-component"),
            {
                "origin": "branch",
                "name": "Create Component",
                "slug": "create-component",
                "component": self.component.pk,
                "branch": "translations",
            },
            follow=True,
        )
        self.assertContains(response, "The filemask did not match any files")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_branch(self):
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        component = self.create_android(
            project=self.project, name="Android", slug="android"
        )

        response = self.client.post(
            reverse("create-component"),
            {
                "origin": "branch",
                "name": "Create Component",
                "slug": "create-component",
                "component": component.pk,
                "branch": "translations",
            },
            follow=True,
        )
        self.assertContains(response, "Return to the component")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_invalid_zip(self):
        self.user.is_superuser = True
        self.user.save()
        with open(TEST_INVALID_ZIP, "rb") as handle:
            response = self.client.post(
                reverse("create-component-zip"),
                {
                    "zipfile": handle,
                    "name": "Create Component",
                    "slug": "create-component",
                    "project": self.project.pk,
                    "source_language": get_default_lang(),
                },
            )
        self.assertContains(response, "Failed to parse uploaded ZIP file.")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_zip(self):
        self.user.is_superuser = True
        self.user.save()
        with open(TEST_ZIP, "rb") as handle:
            response = self.client.post(
                reverse("create-component-zip"),
                {
                    "zipfile": handle,
                    "name": "Create Component",
                    "slug": "create-component",
                    "project": self.project.pk,
                    "source_language": get_default_lang(),
                },
            )
        self.assertContains(response, "*.po")

        response = self.client.post(
            reverse("create-component-zip"),
            {
                "name": "Create Component",
                "slug": "create-component",
                "project": self.project.pk,
                "vcs": "local",
                "repo": "local:",
                "discovery": "0",
                "source_language": get_default_lang(),
            },
        )
        self.assertContains(response, "Adding new translation")
        self.assertContains(response, "*.po")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_doc(self):
        self.user.is_superuser = True
        self.user.save()
        with open(TEST_HTML, "rb") as handle:
            response = self.client.post(
                reverse("create-component-doc"),
                {
                    "docfile": handle,
                    "name": "Create Component",
                    "slug": "create-component",
                    "project": self.project.pk,
                    "source_language": get_default_lang(),
                },
            )
        self.assertContains(response, "*.html")

        response = self.client.post(
            reverse("create-component-doc"),
            {
                "name": "Create Component",
                "slug": "create-component",
                "project": self.project.pk,
                "vcs": "local",
                "repo": "local:",
                "discovery": "0",
                "source_language": get_default_lang(),
            },
        )
        self.assertContains(response, "Adding new translation")
        self.assertContains(response, "*.html")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_scratch(self):
        def create():
            return self.client.post(
                reverse("create-component"),
                {
                    "origin": "scratch",
                    "name": "Create Component",
                    "slug": "create-component",
                    "project": self.project.pk,
                    "file_format": "po-mono",
                    "source_language": get_default_lang(),
                },
                follow=True,
            )

        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        response = create()
        self.assertContains(response, "Test/Create Component")

        response = create()
        self.assertContains(response, "Entry by the same name already exists.")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_scratch_android(self):
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(
            reverse("create-component"),
            {
                "origin": "scratch",
                "name": "Create Component",
                "slug": "create-component",
                "project": self.project.pk,
                "file_format": "aresource",
                "source_language": get_default_lang(),
            },
            follow=True,
        )
        self.assertContains(response, "Test/Create Component")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_scratch_bilingual(self):
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(
            reverse("create-component"),
            {
                "origin": "scratch",
                "name": "Create Component",
                "slug": "create-component",
                "project": self.project.pk,
                "file_format": "po",
                "source_language": get_default_lang(),
            },
            follow=True,
        )
        self.assertContains(response, "Test/Create Component")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_scratch_strings(self):
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(
            reverse("create-component"),
            {
                "origin": "scratch",
                "name": "Create Component",
                "slug": "create-component",
                "project": self.project.pk,
                "file_format": "strings",
                "source_language": get_default_lang(),
            },
            follow=True,
        )
        self.assertContains(response, "Test/Create Component")
