# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for creating projects and models."""

from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext, modify_settings, override_settings
from django.urls import reverse
from translation_finder import DiscoveryResult

from weblate.lang.models import Language, get_default_lang
from weblate.trans.actions import ActionEvents
from weblate.trans.forms import ComponentCreateForm
from weblate.trans.models import Component, Project
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import (
    create_another_user,
    create_test_billing,
    get_test_file,
)
from weblate.trans.views.create import CreateComponentSelection
from weblate.utils.views import get_form_data
from weblate.vcs.base import RepositoryLock
from weblate.vcs.git import GitRepository
from weblate.vcs.models import VCS_REGISTRY
from weblate.workspaces.models import WORKSPACE_PROJECT_CREATORS_GROUP, Workspace

if TYPE_CHECKING:
    from translation_finder.discovery.result import ResultDict

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
        self.client_create_project(False, workspace=0)
        self.client_create_project(True, workspace=billing.workspace_id)

        # No more billings left
        self.client_create_project(
            reverse("create-project"),
            name="p2",
            slug="p2",
            workspace=billing.workspace_id,
        )

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_create_project_billing_project_creator(self) -> None:
        billing = create_test_billing(self.user)
        project_creator = create_another_user(suffix="-creator")
        project_creator.add_team(
            None,
            billing.workspace.setup_groups()[WORKSPACE_PROJECT_CREATORS_GROUP],
        )
        self.client.login(username=project_creator.username, password="testpassword")

        self.assert_create_project(True)
        self.client_create_project(True, workspace=billing.workspace_id)

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

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_project_asks_for_license(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        response = self.client.get(reverse("create-project"))

        self.assertContains(response, 'name="license"')

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_project_sets_blank_workspace_license(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        workspace = Workspace.objects.create(name="Blank license workspace")

        self.client_create_project(
            True,
            name="Workspace License Project",
            slug="workspace-license-project",
            workspace=workspace.pk,
            license="MIT",
        )

        project = Project.objects.get(slug="workspace-license-project")
        workspace.refresh_from_db()
        self.assertEqual(workspace.license, "MIT")
        self.assertTrue(project.inherit_license)
        self.assertEqual(project.license, "MIT")
        self.assertEqual(project.get_effective_setting("license"), "MIT")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_project_without_workspace_edit_keeps_license_explicit(self) -> None:
        workspace = Workspace.objects.create(name="Project creator license workspace")
        project_creator = create_another_user(suffix="-workspace-license")
        project_creator.add_team(
            None, workspace.setup_groups()[WORKSPACE_PROJECT_CREATORS_GROUP]
        )
        self.client.login(username=project_creator.username, password="testpassword")

        self.client_create_project(
            True,
            name="Project Creator License Project",
            slug="project-creator-license-project",
            workspace=workspace.pk,
            license="MIT",
        )

        project = Project.objects.get(slug="project-creator-license-project")
        workspace.refresh_from_db()
        self.assertEqual(workspace.license, "")
        self.assertFalse(project.inherit_license)
        self.assertEqual(project.license, "MIT")
        self.assertEqual(project.get_effective_setting("license"), "MIT")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_project_keeps_different_workspace_license_explicit(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        workspace = Workspace.objects.create(
            name="Existing license workspace", license="GPL-3.0-or-later"
        )

        self.client_create_project(
            True,
            name="Explicit License Project",
            slug="explicit-license-project",
            workspace=workspace.pk,
            license="MIT",
        )

        project = Project.objects.get(slug="explicit-license-project")
        workspace.refresh_from_db()
        self.assertEqual(workspace.license, "GPL-3.0-or-later")
        self.assertFalse(project.inherit_license)
        self.assertEqual(project.license, "MIT")
        self.assertEqual(project.get_effective_setting("license"), "MIT")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_project_inherits_matching_workspace_license(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        workspace = Workspace.objects.create(
            name="Matching license workspace", license="MIT"
        )

        self.client_create_project(
            True,
            name="Inherited License Project",
            slug="inherited-license-project",
            workspace=workspace.pk,
            license="MIT",
        )

        project = Project.objects.get(slug="inherited-license-project")
        workspace.refresh_from_db()
        self.assertEqual(workspace.license, "MIT")
        self.assertTrue(project.inherit_license)
        self.assertEqual(project.license, "MIT")
        self.assertEqual(project.get_effective_setting("license"), "MIT")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_standalone_project_keeps_license_explicit(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        self.client_create_project(
            True,
            name="Standalone License Project",
            slug="standalone-license-project",
            license="MIT",
        )

        project = Project.objects.get(slug="standalone-license-project")
        self.assertFalse(project.inherit_license)
        self.assertEqual(project.license, "MIT")
        self.assertEqual(project.get_effective_setting("license"), "MIT")

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
        billing.add_project(self.project)
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
    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_create_linked_component_skips_repository_lock(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        with patch.object(
            RepositoryLock,
            "__enter__",
            autospec=True,
            side_effect=AssertionError(
                "Linked component creation should not lock the repository"
            ),
        ):
            self.client_create_component(True)

        component = Component.objects.get(slug="create-component")
        self.assertTrue(component.is_repo_link)

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_create_git_component_keeps_repository_lock(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        project = Project.objects.create(name="Other", slug="other")

        original_lock_enter = RepositoryLock.__enter__

        def record_lock_enter(lock):
            return original_lock_enter(lock)

        with patch.object(
            RepositoryLock,
            "__enter__",
            autospec=True,
            side_effect=record_lock_enter,
        ) as lock_enter:
            self.client_create_component(
                True,
                project=project.pk,
                repo=self.component.repo,
                branch=self.component.branch,
            )

        lock_enter.assert_called()
        component = Component.objects.get(slug="create-component")
        self.assertFalse(component.is_repo_link)

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
    def test_create_component_preselects_github_app_vcs(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        # Simulate a worker whose VCS registry was loaded before any App existed.
        VCS_REGISTRY.__dict__.pop("data", None)
        try:
            response = self.client.get(
                reverse("create-component-vcs"),
                {
                    "repo": "https://github.com/test-org/repo1.git",
                    "branch": "main",
                    "vcs": "github-app",
                    "project": self.project.pk,
                },
            )
            form = response.context["form"]
            self.assertEqual(
                form["repo"].value(), "https://github.com/test-org/repo1.git"
            )
            self.assertEqual(form["branch"].value(), "main")
            self.assertEqual(form["vcs"].value(), "github-app")
            self.assertIn("github-app", dict(form.fields["vcs"].choices))
        finally:
            VCS_REGISTRY.__dict__.pop("data", None)

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_wizard_discovery_file_format_params(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        source_component = self.create_java(name="source-java", project=self.project)

        discovery = DiscoveryResult(
            cast(
                "ResultDict",
                {
                    "file_format": "properties",
                    "filemask": "java/swing_messages_*.properties",
                    "template": "java/swing_messages.properties",
                    "file_format_params": {
                        "properties_encoding": "utf-8",
                        "strings_encoding": "utf-16",
                    },
                    "language_regex": "^(?!en$).+$",
                },
            )
        )
        discovery.meta = {"priority": 1000, "origin": None}
        create_url = (
            f"{reverse('create-component-vcs')}?source_component={source_component.pk}"
        )
        params = {
            "name": "Create Component With Discovery Params",
            "slug": "create-component-with-discovery-params",
            "project": self.project.pk,
            "vcs": "git",
            "repo": self.component.repo,
            "source_language": get_default_lang(),
        }

        with (
            patch("weblate.trans.forms.discover", return_value=[discovery]),
            override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES),
        ):
            response = self.client.post(create_url, params)
        self.assertContains(response, "Choose translation files to import")
        self.assertContains(response, "java/swing_messages_*.properties")
        self.assertNotContains(response, "properties_encoding")
        self.assertNotContains(response, "strings_encoding")

        params["discovery"] = "0"
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(create_url, params)
        self.assertContains(
            response,
            "You will be able to edit more options in the component settings after creating it.",
        )
        data = get_form_data(response.context["form"].initial)
        self.assertEqual(data["file_format"], "properties")
        self.assertEqual(
            data["file_format_params"],
            {"properties_encoding": "utf-8"},
        )
        self.assertEqual(data["language_regex"], "^(?!en$).+$")

        file_format_params = cast("dict[str, str]", data.pop("file_format_params"))
        data.update(
            {
                f"file_format_params_{key}": value
                for key, value in file_format_params.items()
            }
        )
        data["project"] = self.project.pk
        data["source_language"] = get_default_lang()
        data["new_base"] = ""
        data["new_lang"] = "contact"
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(create_url, data)
        self.assertEqual(response.status_code, 302)

        component = Component.objects.get(slug="create-component-with-discovery-params")
        self.assertEqual(component.file_format_params["properties_encoding"], "utf-8")
        self.assertNotIn("strings_encoding", component.file_format_params)

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_detected_license_disables_inheritance(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        self.project.license = "GPL-3.0-or-later"
        self.project.save(update_fields=["license"])

        params = {
            "name": "Create Component With Detected License",
            "slug": "create-component-with-detected-license",
            "project": self.project.pk,
            "vcs": "git",
            "repo": self.component.repo,
            "source_language": get_default_lang(),
        }

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(reverse("create-component-vcs"), params)
        self.assertContains(response, "Choose translation files to import")

        params["discovery"] = "4"
        with (
            patch("weblate.trans.views.create.detect_license", return_value="MIT"),
            override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES),
        ):
            response = self.client.post(reverse("create-component-vcs"), params)
        self.assertContains(response, "Detected license as MIT")

        data = get_form_data(response.context["form"].initial)
        self.assertEqual(data["license"], "MIT")
        self.assertEqual(data["detected_license"], "MIT")
        data["project"] = self.project.pk
        data["source_language"] = get_default_lang()
        data["new_lang"] = "add"
        data["new_base"] = "po/project.pot"
        data["language_regex"] = "^[^.]+$"

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(reverse("create-component-vcs"), data)
        self.assertEqual(response.status_code, 302)

        component = Component.objects.get(slug="create-component-with-detected-license")
        self.assertEqual(component.license, "MIT")
        self.assertFalse(component.inherit_license)
        self.assertEqual(component.effective_license, "MIT")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_detected_license_matching_parent_inherits(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        self.project.license = "MIT"
        self.project.save(update_fields=["license"])

        params = {
            "name": "Create Component With Inherited Detected License",
            "slug": "create-component-with-inherited-detected-license",
            "project": self.project.pk,
            "vcs": "git",
            "repo": self.component.repo,
            "source_language": get_default_lang(),
        }

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(reverse("create-component-vcs"), params)
        self.assertContains(response, "Choose translation files to import")

        params["discovery"] = "4"
        with (
            patch("weblate.trans.views.create.detect_license", return_value="MIT"),
            override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES),
        ):
            response = self.client.post(reverse("create-component-vcs"), params)
        self.assertContains(response, "Detected license as MIT")

        form = response.context["form"]
        self.assertTrue(form.fields["license"].disabled)
        self.assertEqual(
            form.fields["license"].widget.attrs["data-inherited-value"], "MIT"
        )
        self.assertTrue(form["inherit_license"].value())

        data = {field: form[field].value() or "" for field in form.fields}
        data.pop("license")
        data["project"] = self.project.pk
        data["source_language"] = get_default_lang()
        data["new_lang"] = "add"
        data["new_base"] = "po/project.pot"
        data["language_regex"] = "^[^.]+$"

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(reverse("create-component-vcs"), data)
        self.assertEqual(response.status_code, 302)

        component = Component.objects.get(
            slug="create-component-with-inherited-detected-license"
        )
        self.assertTrue(component.inherit_license)
        self.assertEqual(component.effective_license, "MIT")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_can_inherit_defaults(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        self.project.license = "GPL-3.0-or-later"
        self.project.new_lang = "none"
        self.project.language_code_style = "posix"
        self.project.save(update_fields=["license", "new_lang", "language_code_style"])

        params = {
            "name": "Create Component With Inheritance",
            "slug": "create-component-with-inheritance",
            "project": self.project.pk,
            "vcs": "git",
            "repo": self.component.get_repo_link_url(),
            "file_format": "po",
            "filemask": "po/*.po",
            "new_base": "po/project.pot",
            "inherit_new_lang": "on",
            "inherit_license": "on",
            "inherit_language_code_style": "on",
            "language_regex": "^[^.]+$",
            "source_language": get_default_lang(),
        }
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(reverse("create-component-vcs"), params)
        self.assertEqual(response.status_code, 302)

        component = Component.objects.get(slug="create-component-with-inheritance")
        self.assertTrue(component.inherit_new_lang)
        self.assertEqual(component.effective_new_lang, "none")
        self.assertTrue(component.inherit_license)
        self.assertEqual(component.effective_license, "GPL-3.0-or-later")
        self.assertTrue(component.inherit_language_code_style)
        self.assertEqual(component.effective_language_code_style, "posix")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_explicit_defaults_disable_inheritance(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        self.project.new_lang = "none"
        self.project.license = "GPL-3.0-or-later"
        self.project.language_code_style = "posix"
        self.project.save(update_fields=["new_lang", "license", "language_code_style"])

        self.client_create_component(True, license="", language_code_style="")

        component = Component.objects.get(slug="create-component")
        self.assertFalse(component.inherit_new_lang)
        self.assertEqual(component.effective_new_lang, "add")
        self.assertFalse(component.inherit_license)
        self.assertEqual(component.effective_license, "")
        self.assertFalse(component.inherit_language_code_style)
        self.assertEqual(component.effective_language_code_style, "")

    def test_create_component_blank_parent_license_is_editable(self) -> None:
        form = ComponentCreateForm(
            self.get_request(), initial={"project": self.project.pk}
        )

        self.assertFalse(form.fields["license"].disabled)
        self.assertFalse(form["inherit_license"].value())

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_blank_parent_preserves_selected_license(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        self.project.license = ""
        self.project.save(update_fields=["license"])

        self.client_create_component(True, license="GPL-3.0-or-later")

        component = Component.objects.get(slug="create-component")
        self.assertFalse(component.inherit_license)
        self.assertEqual(component.license, "GPL-3.0-or-later")
        self.assertEqual(component.effective_license, "GPL-3.0-or-later")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_blank_workspace_preserves_selected_license(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        self.project.workspace = Workspace.objects.create(name="Blank workspace")
        self.project.inherit_license = True
        self.project.license = ""
        self.project.workspace.license = ""
        self.project.workspace.save(update_fields=["license"])
        self.project.save(update_fields=["workspace", "inherit_license", "license"])

        self.client_create_component(True, license="GPL-3.0-or-later")

        component = Component.objects.get(slug="create-component")
        self.assertFalse(component.inherit_license)
        self.assertEqual(component.license, "GPL-3.0-or-later")
        self.assertEqual(component.effective_license, "GPL-3.0-or-later")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_component_existing(self) -> None:
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
        self.project.license = "MIT"
        self.project.new_lang = "none"
        self.project.language_code_style = "posix"
        self.project.save(update_fields=["license", "new_lang", "language_code_style"])
        Component.objects.filter(pk=self.component.pk).update(
            license="GPL-3.0-or-later",
            inherit_license=True,
            new_lang="add",
            inherit_new_lang=True,
            language_code_style="",
            inherit_language_code_style=False,
            inherit_agreement=True,
        )
        self.component.refresh_from_db()

        response = self.client.get(
            f"{reverse('create-component')}?component={self.component.pk}#existing",
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
        discovery_url = response.request["PATH_INFO"]
        if query_string := response.request["QUERY_STRING"]:
            discovery_url = f"{discovery_url}?{query_string}"

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(
                discovery_url,
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
        form = response.context["form"]
        self.assertTrue(form.fields["license"].disabled)
        self.assertEqual(
            form.fields["license"].widget.attrs["data-override-value"],
            "GPL-3.0-or-later",
        )
        self.assertTrue(form.fields["new_lang"].disabled)
        self.assertFalse(form.fields["language_code_style"].disabled)

        data = {field: form[field].value() or "" for field in form.fields}
        data.pop("inherit_license")
        data["license"] = "LGPL-3.0-or-later"
        data.pop("new_lang")
        create_url = response.request["PATH_INFO"]
        if query_string := response.request["QUERY_STRING"]:
            create_url = f"{create_url}?{query_string}"
        with (
            override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(
                create_url,
                data,
                follow=True,
            )
        new_component = Component.objects.get(name="Create Component From Existing")
        response = self.client.get(new_component.get_absolute_url(), follow=True)
        self.assertContains(response, "Diagnostics")
        self.assertContains(response, "Test/Create Component From Existing @ Weblate")

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
        self.assertEqual(
            new_component.inherit_agreement, self.component.inherit_agreement
        )
        self.assertFalse(new_component.inherit_license)
        self.assertEqual(new_component.license, "LGPL-3.0-or-later")
        self.assertEqual(new_component.effective_license, "LGPL-3.0-or-later")
        self.assertTrue(new_component.inherit_new_lang)
        self.assertEqual(new_component.new_lang, "add")
        self.assertEqual(new_component.effective_new_lang, "none")
        self.assertFalse(new_component.inherit_language_code_style)
        self.assertEqual(new_component.effective_language_code_style, "")

        change = new_component.change_set.get(action=ActionEvents.CREATE_COMPONENT)
        self.assertEqual(change.details["origin"], "vcs")

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_create_component_rejects_inaccessible_source_component(self) -> None:
        billing = create_test_billing(self.user)
        billing.add_project(self.project)
        self.project.add_user(self.user, "Administration")

        private_project = self.create_project(
            name="Private source",
            slug="private-source",
            access_control=Project.ACCESS_PRIVATE,
        )
        private_component = self.create_po(
            project=private_project, name="Private source"
        )
        private_component.file_format_params = {"po_line_wrap": "-1"}
        private_component.save(update_fields=["file_format_params"])

        request = self.factory.get("/", {"source_component": str(private_component.pk)})
        request.user = self.user
        form = ComponentCreateForm(
            request,
            initial={"project": self.project.pk, "file_format": "po"},
        )
        self.assertNotEqual(
            form.initial.get("file_format_params", {}).get("po_line_wrap"), "-1"
        )

        response = self.client.get(
            f"{reverse('create-component')}?component={private_component.pk}#existing"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, private_component.name)

        response = self.client_create_component(
            False, source_component=private_component.pk
        )
        self.assertIn("source_component", response.context["form"].errors)
        self.assertFalse(Component.objects.filter(slug="create-component").exists())

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
            )

        component = Component.objects.get(slug="create-component")
        self.assertRedirects(
            response,
            reverse("show_progress", kwargs={"path": component.get_url_path()}),
            fetch_redirect_response=False,
        )
        change = component.change_set.get(action=ActionEvents.CREATE_COMPONENT)
        self.assertEqual(change.details["origin"], "branch")

    def test_component_branch_data_uses_bulk_existing_branch_lookup(self) -> None:
        repo_a = "https://example.com/repo-a.git"
        repo_b = "https://example.com/repo-b.git"
        Component.objects.filter(pk=self.component.pk).update(repo=repo_a)
        self.component.refresh_from_db()
        second = self.create_po(project=self.project, name="Second")
        third = self.create_android(project=self.project, name="Third")
        Component.objects.filter(pk=second.pk).update(repo=repo_a, branch="stable")
        Component.objects.filter(pk=third.pk).update(repo=repo_b)

        view = CreateComponentSelection()
        view.components = Component.objects.filter(
            pk__in=(self.component.pk, second.pk, third.pk)
        ).order_project()

        with (
            patch(
                "weblate.vcs.git.GitRepository.list_remote_branches",
                return_value=["main", "stable", "feature", "new"],
            ) as list_remote_branches,
            CaptureQueriesContext(connection) as queries,
        ):
            branch_data = view.branch_data

        self.assertEqual(list_remote_branches.call_count, 2)
        self.assertEqual(branch_data[self.component.pk], ["feature", "new"])
        self.assertEqual(branch_data[second.pk], ["feature", "new"])
        self.assertEqual(branch_data[third.pk], ["stable", "feature", "new"])

        component_queries = "\n".join(
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "trans_component"' in query["sql"]
        )
        self.assertEqual(
            component_queries.count('"trans_component"."repo" IN'),
            1,
            component_queries,
        )
        self.assertNotIn('"trans_component"."repo" =', component_queries)

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
    @override_settings(COMPONENT_ZIP_UPLOAD_MAX_SIZE=1)
    def test_create_zip_too_big(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(
                reverse("create-component-zip"),
                {
                    "zipfile": SimpleUploadedFile(
                        "translations.zip", b"xx", content_type="application/zip"
                    ),
                    "name": "Create Component",
                    "slug": "create-component",
                    "project": self.project.pk,
                    "source_language": get_default_lang(),
                },
            )
        self.assertContains(response, "Uploaded ZIP file is too big.")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_zip(self) -> None:
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            self.user.is_superuser = True
            self.user.save()
            with (
                open(TEST_ZIP, "rb") as handle,
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

            form = response.context["form"]
            params = {field: form[field].value() or "" for field in form.fields}
            params.pop("inherit_new_lang")
            params["new_lang"] = "none"
            response = self.client.post(
                reverse("create-component-zip"), params, follow=True
            )
            self.assertContains(response, "Test/Create Component")

            component = Component.objects.get(slug="create-component")
            change = component.change_set.get(action=ActionEvents.CREATE_COMPONENT)
            self.assertEqual(change.details["origin"], "zip")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_create_doc(self) -> None:
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
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

            form = response.context["form"]
            params = {field: form[field].value() or "" for field in form.fields}
            # TODO: Template editing not supported with HTML, but it is automatically selected
            del params["edit_template"]
            response = self.client.post(
                reverse("create-component-doc"), params, follow=True
            )
            self.assertContains(response, "Test/Create Component")

            component = Component.objects.get(slug="create-component")
            change = component.change_set.get(action=ActionEvents.CREATE_COMPONENT)
            self.assertEqual(change.details["origin"], "document")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    @override_settings(TRANSLATION_UPLOAD_MAX_SIZE=1)
    def test_create_doc_too_big(self) -> None:
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            self.user.is_superuser = True
            self.user.save()
            response = self.client.post(
                reverse("create-component-doc"),
                {
                    "docfile": SimpleUploadedFile("cs.html", b"xx"),
                    "name": "Create Component",
                    "slug": "create-component",
                    "project": self.project.pk,
                    "source_language": get_default_lang(),
                },
            )

        self.assertContains(response, "Uploaded translation file is too big.")

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

        with (
            open(TEST_PO, encoding="utf-8") as handle,
            override_settings(CREATE_GLOSSARIES=False),
        ):
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

        component = Component.objects.get(slug="create-component")
        change = component.change_set.get(action=ActionEvents.CREATE_COMPONENT)
        self.assertEqual(change.details["origin"], "scratch")

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

        component = Component.objects.get(slug="create-component")
        change = component.change_set.get(action=ActionEvents.CREATE_COMPONENT)
        self.assertEqual(change.details["origin"], "scratch")

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

        component = Component.objects.get(slug="create-component")
        change = component.change_set.get(action=ActionEvents.CREATE_COMPONENT)
        self.assertEqual(change.details["origin"], "scratch")
        self.assertIn("scratch", change.get_details_display())
