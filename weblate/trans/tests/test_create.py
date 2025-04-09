# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for creating projects and models."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.utils import modify_settings, override_settings
from django.urls import reverse

from weblate.lang.models import Language, get_default_lang
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import create_test_billing, get_test_file
from weblate.vcs.git import GitRepository

TEST_ZIP = get_test_file("translations.zip")
TEST_HTML = get_test_file("cs.html")
TEST_PO = get_test_file("cs.po")


class CreateTest(ViewTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # Global setup to configure git committer
        GitRepository.global_setup()

    def assert_create_project(self, result) -> None:
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
    def test_create_project_billing(self) -> None:
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
    def test_create_project_admin(self) -> None:
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

    def assert_create_component(self, result) -> None:
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
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(reverse("create-component-vcs"), params)
        if result:
            self.assertEqual(response.status_code, 302)
        else:
            self.assertEqual(response.status_code, 200)
        return response

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_create_component_billing(self) -> None:
        # No permissions without billing
        self.assert_create_component(False)
        self.client_create_component(False)

        # Create billing and add permissions
        billing = create_test_billing(self.user)
        billing.projects.add(self.project)
        self.project.add_user(self.user, "Administration")
        self.assert_create_component(True)

        # Create two components
        self.client_create_component(True)
        self.client_create_component(True, name="c2", slug="c2")

        # Restrict plan to test nothing more can be created
        billing.plan.limit_strings = 1
        billing.plan.save()

        self.client_create_component(False, name="c3", slug="c3")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_admin(self) -> None:
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
    def test_create_component_wizard(self) -> None:
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
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(reverse("create-component-vcs"), params)
        self.assertContains(response, self.component.get_repo_link_url())
        self.assertContains(response, "po/*.po")

        # Display form
        params["discovery"] = "4"
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(reverse("create-component-vcs"), params)
        self.assertContains(response, self.component.get_repo_link_url())
        self.assertContains(response, "po/*.po")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_existing(self) -> None:
        from weblate.trans.models import Component

        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        self.component.agreement = "test agreement"
        self.component.merge_style = "merge"
        self.component.commit_message = "test commit_message"
        self.component.add_message = "test add_message"
        self.component.delete_message = "test delete_message"
        self.component.merge_message = "test merge_message"
        self.component.addon_message = "test addon_message"
        self.component.pull_message = "test pull_message"
        self.component.save()

        response = self.client.get(
            reverse("create-component") + f"?component={self.component.pk}#existing",
            follow=True,
        )
        # init step
        self.assertContains(response, "Create component")

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(
                reverse("create-component"),
                {
                    "origin": "existing",
                    "name": "Create Component From Existing",
                    "slug": "create-component-from-existing",
                    "component": self.component.pk,
                    "is_glossary": self.component.is_glossary,
                },
                follow=True,
            )

        self.assertContains(response, self.component.get_repo_link_url())

        # discovery step
        self.assertContains(response, "Choose translation files to import")

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(
                reverse("create-component-vcs")
                + f"?source_component={self.component.pk}#existing,",
                {
                    "name": "Create Component From Existing",
                    "slug": "create-component-from-existing",
                    "is_glossary": self.component.is_glossary,
                    "project": self.component.project_id,
                    "vcs": self.component.vcs,
                    "repo": self.component.repo,
                    "discovery": 28,  # deep/*/locales/*/LC_MESSAGES/messages.po
                    "source_language": self.component.source_language_id,
                },
                follow=True,
            )
        self.assertContains(
            response,
            "You will be able to edit more options in the component settings after creating it.",
        )

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(
                reverse("create-component-vcs")
                + f"?source_component={self.component.pk}#existing,",
                {
                    "name": "Create Component From Existing",
                    "slug": "create-component-from-existing",
                    "is_glossary": self.component.is_glossary,
                    "project": self.component.project_id,
                    "vcs": self.component.vcs,
                    "repo": self.component.repo,
                    "source_language": self.component.source_language_id,
                    "file_format": "po",
                    "filemask": "deep/*/locales/*/LC_MESSAGES/messages.po",
                    "new_lang": "add",
                    "new_base": "deep/cs/locales/cs/LC_MESSAGES/messages.po",
                    "language_regex": "^[^.]+$",
                    "source_component": self.component.pk,
                },
                follow=True,
            )
        self.assertContains(response, "Community localization checklist")
        self.assertContains(response, "Test/Create Component From Existing @ Weblate")

        new_component = Component.objects.get(name="Create Component From Existing")
        cloned_fields = [
            "agreement",
            "merge_style",
            "commit_message",
            "add_message",
            "delete_message",
            "merge_message",
            "addon_message",
            "pull_message",
        ]
        for field in cloned_fields:
            self.assertEqual(
                getattr(new_component, field), getattr(self.component, field)
            )

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_branch_fail(self) -> None:
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
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
        self.assertContains(response, "The file mask did not match any files")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_branch(self) -> None:
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        component = self.create_android(
            project=self.project, name="Android", slug="android"
        )

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
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
    def test_create_invalid_zip(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(
                reverse("create-component-zip"),
                {
                    "zipfile": SimpleUploadedFile(
                        "invalid.zip", b"x", content_type="application/zip"
                    ),
                    "name": "Create Component",
                    "slug": "create-component",
                    "project": self.project.pk,
                    "source_language": get_default_lang(),
                },
            )
        self.assertContains(response, "Could not parse uploaded ZIP file.")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_zip(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        with (
            open(TEST_ZIP, "rb") as handle,
            override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES),
        ):
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

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
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
    def test_create_doc(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        with (
            open(TEST_HTML, "rb") as handle,
            override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES),
        ):
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

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
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
    def test_create_doc_category(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        category = self.project.category_set.create(name="Kategorie", slug="cat")
        with (
            open(TEST_HTML, "rb") as handle,
            override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES),
        ):
            response = self.client.post(
                reverse("create-component-doc"),
                {
                    "docfile": handle,
                    "category": category.pk,
                    "name": "Create Component",
                    "slug": "create-component",
                    "project": self.project.pk,
                    "source_language": get_default_lang(),
                },
            )
        self.assertContains(response, "*.html")

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(
                reverse("create-component-doc"),
                {
                    "name": "Create Component",
                    "slug": "create-component",
                    "project": self.project.pk,
                    "category": category.pk,
                    "vcs": "local",
                    "repo": "local:",
                    "discovery": "0",
                    "source_language": get_default_lang(),
                },
            )
        self.assertContains(response, "Adding new translation")
        self.assertContains(response, "*.html")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_doc_bilingual(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        with open(TEST_PO) as handle, override_settings(CREATE_GLOSSARIES=False):
            response = self.client.post(
                reverse("create-component-doc"),
                {
                    "docfile": handle,
                    "name": "Bilingual Component From Doc",
                    "slug": "bilingual-component-from-doc",
                    "project": self.project.pk,
                    "source_language": get_default_lang(),
                    "target_language": Language.objects.get(code="cs").id,
                },
            )
        self.assertContains(response, "Choose translation files to import")
        self.assertNotContains(response, "gettext PO file (monolingual)")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_scratch(self) -> None:
        @override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES)
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
        self.assertContains(
            response,
            "Component or category with the same URL slug already exists at this level.",
        )

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_scratch_android(self) -> None:
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
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
    def test_create_scratch_bilingual(self) -> None:
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
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
    def test_create_scratch_strings(self) -> None:
        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
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
