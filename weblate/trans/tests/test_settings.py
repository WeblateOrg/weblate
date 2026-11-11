# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for settings management."""

from __future__ import annotations

import json
from importlib import import_module
from typing import TYPE_CHECKING, cast
from unittest.mock import patch
from urllib.parse import urlencode

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import Client
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice
from filelock import FileLock

from weblate.accounts.utils import SESSION_SENSITIVE_FACTOR_GRANT
from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, Permission, Role
from weblate.checks.models import Check
from weblate.machinery.models import MachineryInstallation
from weblate.trans import defaults
from weblate.trans.actions import ActionEvents
from weblate.trans.file_format_params import get_effective_params_for_file_format
from weblate.trans.forms import (
    CategorySettingsForm,
    ComponentSettingsForm,
    ProjectMoveForm,
    ProjectSettingsForm,
)
from weblate.trans.models import (
    Category,
    CommitPolicyChoices,
    Component,
    ContributorAgreement,
    PendingUnitChange,
    Project,
    Translation,
    Unit,
    WorkflowSetting,
)
from weblate.trans.models.component import ComponentQuerySet
from weblate.trans.tests.test_views import ReusableViewTestCase
from weblate.trans.tests.utils import create_test_billing
from weblate.utils.change_origin import acting_user_context
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.render import (
    validate_render_addon,
    validate_render_commit,
    validate_render_component,
)
from weblate.utils.tests.network import mock_dns
from weblate.utils.views import get_form_data
from weblate.vcs.base import RepositoryLock
from weblate.vcs.github import GitHubInstallation
from weblate.vcs.models import VCS_REGISTRY
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from django.http import HttpResponse


class ComponentRestrictedVerificationTest(ReusableViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        session = self.client.session
        session.pop(SESSION_SENSITIVE_FACTOR_GRANT, None)
        session.save()
        self.project.add_user(self.user, "Administration")
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.api_url = reverse(
            "api:component-detail",
            kwargs={"project__slug": self.project.slug, "slug": self.component.slug},
        )
        self.settings_url = reverse(
            "settings", kwargs={"path": self.component.get_url_path()}
        )

    def assert_restricted(self, restricted: bool) -> None:
        self.component.refresh_from_db()
        self.assertEqual(self.component.restricted, restricted)
        self.assertEqual(
            Client().get(self.component.get_absolute_url()).status_code,
            404 if restricted else 200,
        )

    def verify_credentials(self, next_url: str) -> None:
        response = self.client.post(
            reverse("first-factor-verify"),
            {"target": "sensitive", "next": next_url, "password": "testpassword"},
        )
        self.assertEqual(response.status_code, 302)

    def api_patch(self, payload: dict, **kwargs) -> HttpResponse:
        return self.client.patch(
            self.api_url,
            json.dumps(payload),
            content_type="application/json",
            **kwargs,
        )

    def test_api_removal_requires_verification(self) -> None:
        response = self.api_patch({"restricted": False})
        self.assertEqual(response.status_code, 403, response.content)
        self.assert_restricted(True)

        self.verify_credentials(self.api_url)
        response = self.api_patch({"restricted": False})
        self.assertEqual(response.status_code, 200, response.content)
        self.assert_restricted(False)

    def test_api_enabling_requires_verification(self) -> None:
        self.component.restricted = False
        self.component.save(update_fields=["restricted"])
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])

        response = self.api_patch({"restricted": True})
        self.assertEqual(response.status_code, 403, response.content)
        self.assert_restricted(False)

    def test_api_form_put_requires_verification(self) -> None:
        """Omitting a boolean from a form-encoded PUT clears it."""
        payload = urlencode(
            {
                "name": self.component.name,
                "slug": self.component.slug,
                "vcs": self.component.vcs,
                "repo": self.component.repo,
                "branch": self.component.branch,
                "filemask": self.component.filemask,
                "file_format": self.component.file_format,
                "new_lang": self.component.new_lang,
                "new_base": self.component.new_base,
            }
        )
        content_type = "application/x-www-form-urlencoded"

        response = self.client.put(self.api_url, payload, content_type=content_type)
        self.assertEqual(response.status_code, 403, response.content)
        self.assert_restricted(True)

        self.verify_credentials(self.api_url)
        response = self.client.put(self.api_url, payload, content_type=content_type)
        self.assertEqual(response.status_code, 200, response.content)
        self.assert_restricted(False)

    def test_api_unchanged_value_skips_verification(self) -> None:
        response = self.api_patch({"restricted": True, "priority": 80})
        self.assertEqual(response.status_code, 200, response.content)
        self.component.refresh_from_db()
        self.assertEqual(self.component.priority, 80)
        self.assert_restricted(True)

    def test_api_token_skips_verification(self) -> None:
        response = self.api_patch(
            {"restricted": False},
            HTTP_AUTHORIZATION=f"Token {self.user.auth_token.key}",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assert_restricted(False)

    def assert_create_requires_verification(self, payload: dict) -> None:
        url = reverse("api:project-components", kwargs={"slug": self.project.slug})
        payload = {"name": "Copy", "slug": "copy", "restricted": False, **payload}
        data = json.dumps(payload)

        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(self.project.component_set.filter(slug="copy").exists())

        self.verify_credentials(url)
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)

    def test_api_from_component_requires_verification(self) -> None:
        self.assert_create_requires_verification(
            {"from_component": f"{self.project.slug}/{self.component.slug}"}
        )

    def test_api_repo_link_requires_verification(self) -> None:
        self.assert_create_requires_verification(
            {
                "repo": self.component.get_repo_link_url(),
                "vcs": self.component.vcs,
                "filemask": self.component.filemask,
                "file_format": self.component.file_format,
                "new_lang": "none",
            }
        )

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_api_restricted_copy_skips_verification(self) -> None:
        response = self.client.post(
            reverse("api:project-components", kwargs={"slug": self.project.slug}),
            json.dumps(
                {
                    "name": "Copy",
                    "slug": "copy",
                    "repo": self.component.get_repo_link_url(),
                    "vcs": self.component.vcs,
                    "filemask": self.component.filemask,
                    "file_format": self.component.file_format,
                    "new_lang": "none",
                    "restricted": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_two_factor_account_requires_second_factor(self) -> None:
        TOTPDevice.objects.create(user=self.user, name="Test")

        response = self.api_patch({"restricted": False})
        self.assertEqual(response.status_code, 403, response.content)
        self.assert_restricted(True)

        response = self.client.get(self.settings_url)
        data = get_form_data(response.context["form"].initial)
        data.pop("restricted")
        response = self.client.post(self.settings_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith(
                reverse("2fa-login", kwargs={"backend": "totp"}),
            )
        )
        self.assert_restricted(True)

    def test_settings_enabling_requires_verification(self) -> None:
        self.component.restricted = False
        self.component.save(update_fields=["restricted"])
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        response = self.client.get(self.settings_url)
        data = get_form_data(response.context["form"].initial)
        data["restricted"] = True

        response = self.client.post(self.settings_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("first-factor-verify")))
        self.assert_restricted(False)

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_browser_repo_link_requires_verification(self) -> None:
        self.assert_browser_repo_link_requires_verification()

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_browser_repo_link_with_unrestricted_config_requires_verification(
        self,
    ) -> None:
        source = self.create_link_existing(restricted=False)
        self.assert_browser_repo_link_requires_verification(source_component=source.pk)

    def assert_browser_repo_link_requires_verification(self, **kwargs) -> None:
        url = reverse("create-component-vcs")
        params = {
            "name": "Copy",
            "slug": "copy",
            "project": self.project.pk,
            "vcs": self.component.vcs,
            "repo": self.component.get_repo_link_url(),
            "file_format": "po",
            "filemask": "po/*.po",
            "new_base": "po/project.pot",
            "new_lang": "add",
            "language_regex": "^[^.]+$",
            "source_language": self.component.source_language.pk,
            **kwargs,
        }

        response = self.client.post(url, params)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("first-factor-verify")))
        self.assertFalse(self.project.component_set.filter(slug="copy").exists())

        self.verify_credentials(url)
        response = self.client.post(url, params)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.project.component_set.filter(slug="copy").exists())

    def get_admin_form(self, url: str) -> dict:
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        response = self.client.get(url)
        return {**get_form_data(response.context["adminform"].form.initial), "_save": 1}

    def test_admin_component_requires_verification(self) -> None:
        url = reverse("admin:trans_component_change", args=(self.component.pk,))
        data = self.get_admin_form(url)
        data.pop("restricted")

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("first-factor-verify")))
        self.assert_restricted(True)

        self.verify_credentials(url)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assert_restricted(False)

    def test_api_verification_precedes_repository_validation(self) -> None:
        """Model validation can switch the branch of the live checkout."""
        with patch.object(Component, "clean") as clean:
            response = self.api_patch({"restricted": False, "branch": "translations"})
        self.assertEqual(response.status_code, 403, response.content)
        clean.assert_not_called()
        self.component.refresh_from_db()
        self.assertEqual(self.component.branch, "main")
        self.assert_restricted(True)

    def test_settings_verification_precedes_repository_validation(self) -> None:
        response = self.client.get(self.settings_url)
        data = get_form_data(response.context["form"].initial)
        data.pop("restricted")
        data["branch"] = "translations"

        with patch.object(Component, "clean") as clean:
            response = self.client.post(self.settings_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("first-factor-verify")))
        clean.assert_not_called()
        self.assert_restricted(True)

    def test_admin_verification_precedes_repository_validation(self) -> None:
        url = reverse("admin:trans_component_change", args=(self.component.pk,))
        data = self.get_admin_form(url)
        data.pop("restricted")
        data["branch"] = "translations"

        with patch.object(Component, "clean") as clean:
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("first-factor-verify")))
        clean.assert_not_called()
        self.assert_restricted(True)

    def test_admin_project_requires_verification(self) -> None:
        url = reverse("admin:trans_project_change", args=(self.project.pk,))
        data = self.get_admin_form(url)
        data["access_control"] = Project.ACCESS_PRIVATE

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("first-factor-verify")))
        self.project.refresh_from_db()
        self.assertEqual(self.project.access_control, Project.ACCESS_PUBLIC)

    def test_api_project_form_put_requires_verification(self) -> None:
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        Project.objects.filter(pk=self.project.pk).update(public_sharing=True)
        url = reverse("api:project-detail", kwargs={"slug": self.project.slug})
        payload = urlencode(
            {
                "name": self.project.name,
                "slug": self.project.slug,
                "web": self.project.web,
            }
        )
        content_type = "application/x-www-form-urlencoded"

        response = self.client.put(url, payload, content_type=content_type)
        self.assertEqual(response.status_code, 403, response.content)
        self.project.refresh_from_db()
        self.assertTrue(self.project.public_sharing)

        self.verify_credentials(url)
        response = self.client.put(url, payload, content_type=content_type)
        self.assertEqual(response.status_code, 200, response.content)
        self.project.refresh_from_db()
        self.assertFalse(self.project.public_sharing)

    def test_settings_removal_requires_verification(self) -> None:
        response = self.client.get(self.settings_url)
        data = get_form_data(response.context["form"].initial)
        data.pop("restricted")

        response = self.client.post(self.settings_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("first-factor-verify")))
        self.assert_restricted(True)

        self.verify_credentials(self.settings_url)
        response = self.client.post(self.settings_url, data)
        self.assertRedirects(response, self.settings_url)
        self.assert_restricted(False)

    def test_settings_unchanged_value_skips_verification(self) -> None:
        response = self.client.get(self.settings_url)
        data = get_form_data(response.context["form"].initial)
        data["priority"] = 80

        response = self.client.post(self.settings_url, data)
        self.assertRedirects(response, self.settings_url)
        self.component.refresh_from_db()
        self.assertEqual(self.component.priority, 80)
        self.assert_restricted(True)


class SettingsTest(ReusableViewTestCase):
    def test_saving_settings_reports_legacy_duplicate_repair(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.project.component_set.update(license="MIT")
        duplicate = Group.objects.bulk_create(
            [Group(name="Administration", defining_project=self.project, internal=True)]
        )[0]
        url = reverse("settings", kwargs={"path": self.project.get_url_path()})
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Settings saved")
        self.assertContains(
            response, "Team Administration was renamed to Administration (2)"
        )
        duplicate.refresh_from_db()
        self.assertEqual(duplicate.name, "Administration (2)")
        self.assertFalse(duplicate.internal)

    def test_enabling_reviews_warns_about_custom_team_rename(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.project.component_set.update(license="MIT")
        custom = Group.objects.create(name="Review", defining_project=self.project)
        url = reverse("settings", kwargs={"path": self.project.get_url_path()})
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data["translation_review"] = True
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Settings saved")
        self.assertContains(response, "Team Review was renamed to Review (2)")
        custom.refresh_from_db()
        self.assertEqual(custom.name, "Review (2)")
        self.assertTrue(self.project.defined_groups.get(name="Review").internal)

    def test_public_sharing_permission(self) -> None:
        form = ProjectSettingsForm(self.get_request(), instance=self.project)
        self.assertTrue(form.fields["public_sharing"].disabled)

        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.user.clear_permissions_cache()
        form = ProjectSettingsForm(self.get_request(), instance=self.project)
        self.assertFalse(form.fields["public_sharing"].disabled)

    def test_shared_memory_contribution_warning(self) -> None:
        form = ProjectSettingsForm(self.get_request(), instance=self.project)

        self.assertIn(
            "Project access control does not restrict this shared data.",
            form.fields["contribute_shared_tm"].help_text,
        )
        self.project.add_user(self.user, "Administration")
        response = self.client.get(
            reverse("settings", kwargs={"path": self.project.get_url_path()})
        )
        self.assertContains(
            response, "Project access control does not restrict this shared data."
        )

    @override_settings(OFFER_HOSTING=True)
    def test_hosted_shared_memory_contribution_warning(self) -> None:
        form = ProjectSettingsForm(self.get_request(), instance=self.project)

        self.assertTrue(form.fields["contribute_shared_tm"].widget.is_hidden)
        self.assertIn(
            "regardless of project access control",
            form.fields["use_shared_tm"].help_text,
        )
        self.project.add_user(self.user, "Administration")
        response = self.client.get(
            reverse("settings", kwargs={"path": self.project.get_url_path()})
        )
        self.assertContains(response, "regardless of project access control")

    @override_settings(OFFER_HOSTING=True)
    def test_hosted_restricted_component_rejects_shared_memory(self) -> None:
        self.component.restricted = True
        self.project.use_shared_tm = True

        with self.assertRaisesMessage(
            ValidationError,
            "A component can not be restricted while its project uses shared translation memory.",
        ):
            self.component.clean_model_settings()

    @override_settings(OFFER_HOSTING=True)
    def test_hosted_shared_memory_rejects_restricted_component(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(restricted=True)
        self.project.use_shared_tm = True

        with self.assertRaisesMessage(
            ValidationError,
            "Shared translation memory can not be enabled while the project has restricted components.",
        ):
            self.project.clean()

    @override_settings(OFFER_HOSTING=True)
    def test_hosted_shared_memory_allows_unrestricted_component_edit(self) -> None:
        self.create_link_existing(restricted=True)
        Project.objects.filter(pk=self.project.pk).update(use_shared_tm=True)
        component = Component.objects.get(pk=self.component.pk)

        component.clean_model_settings()

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_restricted_component_permission_denial(self) -> None:
        role = Role.objects.create(name="Project component settings")
        role.permissions.add(Permission.objects.get(codename="component.edit"))
        group = Group.objects.create(name="Project component editors")
        group.roles.add(role)
        group.projects.add(self.project)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertTrue(self.user.has_perm("component.edit", self.component))
        self.assertFalse(self.user.has_perm("project.edit", self.project))

        form = ComponentSettingsForm(self.get_request(), instance=self.component)

        field = form.fields["restricted"]
        self.assertTrue(field.disabled)
        self.assertFalse(field.widget.is_hidden)
        self.assertEqual(
            field.help_text,
            "You need explicit access to this component before enabling restricted access; otherwise, you would lock yourself out.",
        )

        data = get_form_data(form.initial)
        data["restricted"] = True
        form = ComponentSettingsForm(self.get_request(), data, instance=self.component)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["restricted"])

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_project_admin_can_enable_restricted_component(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.user.clear_permissions_cache()
        self.assertNotIn(self.component.pk, self.user.component_permissions)

        form = ComponentSettingsForm(self.get_request(), instance=self.component)
        self.assertFalse(form.fields["restricted"].disabled)
        self.assertFalse(form.fields["restricted"].widget.is_hidden)

        data = get_form_data(form.initial)
        data["restricted"] = True
        form = ComponentSettingsForm(self.get_request(), data, instance=self.component)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["restricted"])

    def test_default_message_templates_render(self) -> None:
        validators = (
            (defaults.DEFAULT_COMMIT_MESSAGE, validate_render_commit),
            (defaults.DEFAULT_ADD_MESSAGE, validate_render_commit),
            (defaults.DEFAULT_DELETE_MESSAGE, validate_render_commit),
            (defaults.DEFAULT_MERGE_MESSAGE, validate_render_component),
            (defaults.DEFAULT_ADDON_MESSAGE, validate_render_addon),
            (defaults.DEFAULT_PULL_MESSAGE, validate_render_component),
        )
        for template, validator in validators:
            with self.subTest(template=template):
                validator(template)

    def consolidate_inherited_settings(self) -> None:
        migration = import_module(
            "weblate.trans.migrations.0084_consolidate_inherited_settings"
        )
        migration.consolidate_inherited_settings(apps, None)

    def consolidate_workspace_inherited_settings(self) -> None:
        migration = import_module(
            "weblate.trans.migrations.0084_consolidate_inherited_settings"
        )
        migration.consolidate_workspace_settings(apps, None)

    def consolidate_category_inherited_settings(self) -> None:
        migration = import_module(
            "weblate.trans.migrations.0087_consolidate_category_inherited_settings"
        )
        migration.consolidate_category_settings(apps, None)

    def repair_license_inheritance(self) -> None:
        migration = import_module(
            "weblate.trans.migrations.0089_repair_license_inheritance"
        )
        migration.repair_license_inheritance(apps, None)

    def assert_huge_inherited_settings_deferred(self, component: Component) -> None:
        workspace = component.project.workspace
        assert workspace is not None
        category = component.category
        if component.category_id:
            assert category is not None
        for field in ("commit_message",):
            self.assertIn(field, component.get_deferred_fields())
            self.assertIn(field, component.project.get_deferred_fields())
            self.assertIn(field, workspace.get_deferred_fields())
            if category is not None:
                self.assertIn(field, category.get_deferred_fields())
        for field in ("agreement",):
            self.assertNotIn(field, component.get_deferred_fields())
            self.assertNotIn(field, component.project.get_deferred_fields())
            self.assertNotIn(field, workspace.get_deferred_fields())
            if category is not None:
                self.assertNotIn(field, category.get_deferred_fields())
        self.assertNotIn("check_flags", component.get_deferred_fields())
        self.assertNotIn("check_flags", component.project.get_deferred_fields())
        self.assertNotIn("check_flags", workspace.get_deferred_fields())
        if category is not None:
            self.assertNotIn("check_flags", category.get_deferred_fields())

    def test_defer_huge_inherited_settings(self) -> None:
        workspace = Workspace.objects.create(name="Settings workspace")
        Project.objects.filter(pk=self.project.pk).update(workspace=workspace)
        category = Category.objects.create(
            name="Settings category", slug="settings-category", project=self.project
        )
        Component.objects.filter(pk=self.component.pk).update(category=category)

        component = Component.objects.filter(pk=self.component.pk).prefetch().get()
        self.assert_huge_inherited_settings_deferred(component)

        translation = (
            Translation.objects.filter(pk=self.translation.pk).prefetch().get()
        )
        self.assert_huge_inherited_settings_deferred(translation.component)

        unit_id = self.translation.unit_set.values_list("pk", flat=True).first()
        assert unit_id is not None
        unit = Unit.objects.filter(pk=unit_id).prefetch().get()
        self.assert_huge_inherited_settings_deferred(unit.translation.component)

    def test_inherited_component_settings(self) -> None:
        workspace = Workspace.objects.create(
            name="Settings workspace",
            license="MIT",
            new_lang="none",
            check_flags="safe-html",
            commit_message="Workspace commit",
        )
        self.project.license = "GPL-3.0-or-later"
        self.project.save()
        self.project.workspace = workspace
        self.project.inherit_license = True
        self.project.inherit_new_lang = True
        self.project.inherit_commit_message = True
        self.project.check_flags = "strict-same"
        self.project.save()

        self.component.inherit_license = True
        self.component.inherit_new_lang = True
        self.component.inherit_commit_message = True
        self.component.check_flags = "ignore-same"
        self.component.save()

        component = Component.objects.select_related(
            "project", "project__workspace"
        ).get(pk=self.component.pk)
        self.assertEqual(component.effective_license, "MIT")
        self.assertEqual(component.effective_new_lang, "none")
        self.assertEqual(component.effective_commit_message, "Workspace commit")
        self.assertEqual(
            set(component.all_flags), {"safe-html", "strict-same", "ignore-same"}
        )

    def test_clean_fields_inherited_settings(self) -> None:
        workspace = Workspace.objects.create(
            name="Validation workspace", license="CC-BY-SA-4.0"
        )
        self.project.workspace = workspace
        self.project.inherit_license = True
        self.project.save(update_fields=["workspace", "inherit_license"])
        category = Category.objects.create(
            name="Validation",
            slug="validation",
            project=self.project,
            commit_message="Inherited commit",
            inherit_commit_message=False,
            secondary_language=self.component.source_language,
            inherit_secondary_language=False,
        )
        self.component.category = category
        self.component.license = ""
        self.component.inherit_license = True
        self.component.commit_message = ""
        self.component.inherit_commit_message = True
        self.component.agreement = "Stored agreement"
        self.component.inherit_agreement = True
        self.component.secondary_language = None
        self.component.inherit_secondary_language = True

        self.component.clean_fields()

        self.assertEqual(self.component.license, "")
        self.assertEqual(self.component.commit_message, "")
        self.assertEqual(self.component.agreement, "Stored agreement")
        self.assertIsNone(self.component.secondary_language_id)
        self.assertEqual(self.component.effective_license, "CC-BY-SA-4.0")
        self.assertEqual(self.component.effective_commit_message, "Inherited commit")
        self.assertEqual(
            self.component.effective_secondary_language, self.component.source_language
        )

    def test_clean_fields_inherited_errors_and_exclusions(self) -> None:
        self.component.project.license = "invalid-license"
        self.component.license = "MIT"
        self.component.inherit_license = True
        self.component.project.commit_message = ""
        self.component.commit_message = "Stored commit"
        self.component.inherit_commit_message = True
        self.component.name = ""

        with self.assertRaises(ValidationError) as raised:
            self.component.clean_fields()
        self.assertEqual(
            set(raised.exception.message_dict), {"name", "license", "commit_message"}
        )
        self.assertEqual(self.component.license, "MIT")
        self.assertEqual(self.component.commit_message, "Stored commit")

        excluded = {"name", "license", "commit_message"}
        self.component.clean_fields(exclude=excluded)
        self.assertEqual(excluded, {"name", "license", "commit_message"})

        self.component.inherit_license = False
        self.component.inherit_commit_message = False
        self.component.clean_fields(exclude={"name"})
        self.component.commit_message = ""
        with self.assertRaises(ValidationError) as raised:
            self.component.clean_fields(exclude={"name"})
        self.assertEqual(set(raised.exception.message_dict), {"commit_message"})

    def test_clean_fields_missing_parent(self) -> None:
        component = Component()
        with self.assertRaises(ValidationError) as raised:
            component.clean_fields()
        self.assertIn("project", raised.exception.message_dict)

    def test_existing_language_policy_inheritance(self) -> None:
        workspace = Workspace.objects.create(
            name="Policy workspace", new_lang="existing"
        )
        self.project.workspace = workspace
        self.project.inherit_new_lang = True
        self.project.save()
        category = Category.objects.create(
            name="Policy", slug="policy", project=self.project
        )
        self.component.category = category
        self.component.inherit_new_lang = True
        self.component.save()
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.effective_new_lang, "existing")
        component.inherit_new_lang = False
        component.new_lang = "contact"
        component.save()
        self.assertEqual(component.effective_new_lang, "contact")

    def test_inherited_setting_widget_state(self) -> None:
        self.project.license = "MIT"
        self.project.save()
        Component.objects.filter(pk=self.component.pk).update(
            license="GPL-3.0-or-later", inherit_license=True
        )
        self.component.refresh_from_db()

        form = ComponentSettingsForm(self.get_request(), instance=self.component)

        self.assertTrue(form.fields["license"].disabled)
        self.assertEqual(form.initial["license"], "MIT")
        self.assertEqual(
            form.fields["license"].widget.attrs["data-inherited-value"], "MIT"
        )
        self.assertEqual(
            form.fields["license"].widget.attrs["data-override-value"],
            "GPL-3.0-or-later",
        )

        data = get_form_data(form.initial)
        data.pop("inherit_license")
        data["license"] = "GPL-3.0-or-later"
        form = ComponentSettingsForm(
            self.get_request(),
            data,
            instance=self.component,
        )

        self.assertFalse(form.fields["license"].disabled)

    def test_inherited_setting_form_rendering(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.project.license = "MIT"
        self.project.save()
        Component.objects.filter(pk=self.component.pk).update(inherit_license=True)
        self.component.refresh_from_db()

        response = self.client.get(reverse("settings", kwargs=self.kw_component))

        self.assertContains(response, 'data-inherited-setting="license"')
        self.assertContains(response, 'data-inherited-value="MIT"')
        self.assertContains(response, "Inherited value is shown")
        self.assertContains(response, 'name="license"')
        self.assertContains(response, "disabled")

    @override_settings(DEFAULT_COMMIT_MESSAGE="Site default commit")
    def test_message_setting_site_default_widget_state(self) -> None:
        category = Category.objects.create(
            name="Site defaults category",
            slug="site-defaults-category",
            project=self.project,
        )

        for form in (
            ProjectSettingsForm(self.get_request(), instance=self.project),
            CategorySettingsForm(self.get_request(), instance=category),
            ComponentSettingsForm(self.get_request(), instance=self.component),
        ):
            with self.subTest(form=form.__class__.__name__):
                self.assertEqual(
                    form.fields["commit_message"].widget.attrs[
                        "data-site-default-value"
                    ],
                    "Site default commit",
                )

    @override_settings(DEFAULT_COMMIT_MESSAGE="Site default commit")
    def test_message_setting_site_default_form_rendering(self) -> None:
        self.project.add_user(self.user, "Administration")

        response = self.client.get(reverse("settings", kwargs=self.kw_component))

        self.assertContains(response, 'data-site-default-value="Site default commit"')
        self.assertContains(response, "Restore site default")

    def test_workspace_less_project_has_no_inheritance_wrapper(self) -> None:
        self.assertIsNone(self.project.workspace_id)

        form = ProjectSettingsForm(self.get_request(), instance=self.project)
        self.assertTrue(form.fields["inherit_license"].widget.is_hidden)

        self.project.add_user(self.user, "Administration")
        response = self.client.get(
            reverse("settings", kwargs={"path": self.project.get_url_path()})
        )

        self.assertContains(response, 'name="license"')
        self.assertNotContains(response, 'data-inherited-setting="license"')

    @override_settings(OFFER_HOSTING=True)
    def test_hosted_project_settings_mirror_workspace_tm_contribution(self) -> None:
        form = ProjectSettingsForm(self.get_request(), instance=self.project)
        self.assertTrue(form.fields["contribute_shared_tm"].widget.is_hidden)
        self.assertTrue(form.fields["contribute_workspace_tm"].widget.is_hidden)

        data = get_form_data(form.initial)
        data["use_shared_tm"] = False
        data["contribute_shared_tm"] = True
        data["use_workspace_tm"] = True
        data["contribute_workspace_tm"] = False
        form = ProjectSettingsForm(
            self.get_request(),
            data,
            instance=self.project,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["contribute_shared_tm"])
        self.assertTrue(form.cleaned_data["contribute_workspace_tm"])

    def test_checked_inherited_setting_preserves_override(self) -> None:
        self.project.license = "MIT"
        self.project.save()
        Component.objects.filter(pk=self.component.pk).update(
            license="GPL-3.0-or-later", inherit_license=True
        )
        self.component.refresh_from_db()

        form = ComponentSettingsForm(self.get_request(), instance=self.component)
        data = get_form_data(form.initial)
        data.pop("license")

        form = ComponentSettingsForm(
            self.get_request(),
            data,
            instance=self.component,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        component = Component.objects.get(pk=self.component.pk)
        self.assertTrue(component.inherit_license)
        self.assertEqual(component.license, "GPL-3.0-or-later")
        self.assertEqual(component.effective_license, "MIT")

    def test_unchecked_inherited_setting_saves_posted_value(self) -> None:
        self.project.license = "GPL-3.0-or-later"
        self.project.save()
        Component.objects.filter(pk=self.component.pk).update(
            license="MIT", inherit_license=True
        )
        self.component.refresh_from_db()

        form = ComponentSettingsForm(self.get_request(), instance=self.component)
        data = get_form_data(form.initial)
        data.pop("inherit_license")
        data["license"] = "MIT"

        form = ComponentSettingsForm(
            self.get_request(),
            data,
            instance=self.component,
        )
        self.assertFalse(form.fields["license"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        component = Component.objects.get(pk=self.component.pk)
        self.assertFalse(component.inherit_license)
        self.assertEqual(component.effective_license, "MIT")

    def test_newly_checked_inherited_setting_preserves_override(self) -> None:
        self.project.license = "MIT"
        self.project.save()
        self.component.license = "GPL-3.0-or-later"
        self.component.inherit_license = False
        self.component.save()

        form = ComponentSettingsForm(self.get_request(), instance=self.component)
        data = get_form_data(form.initial)
        data["inherit_license"] = "on"
        data.pop("license")

        form = ComponentSettingsForm(
            self.get_request(),
            data,
            instance=self.component,
        )
        self.assertTrue(form.fields["license"].disabled)
        self.assertEqual(form.initial["license"], "MIT")
        self.assertEqual(
            form.fields["license"].widget.attrs["data-inherited-value"], "MIT"
        )
        self.assertEqual(
            form.fields["license"].widget.attrs["data-override-value"],
            "GPL-3.0-or-later",
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        component = Component.objects.get(pk=self.component.pk)
        self.assertTrue(component.inherit_license)
        self.assertEqual(component.license, "GPL-3.0-or-later")
        self.assertEqual(component.effective_license, "MIT")

    def test_scratch_component_explicit_settings_disable_inheritance(self) -> None:
        workspace = Workspace.objects.create(
            name="Settings workspace",
            license="MIT",
        )
        self.project.workspace = workspace
        self.project.inherit_license = True
        self.project.save()

        component = self.project.scratch_create_component(
            "Scratch",
            "scratch",
            self.component.source_language,
            "tbx",
            has_template=False,
            license="GPL-3.0-or-later",
            acting_user=self.user,
        )

        self.assertFalse(component.inherit_license)
        self.assertEqual(component.effective_license, "GPL-3.0-or-later")

    def test_inherited_category_settings(self) -> None:
        workspace = Workspace.objects.create(
            name="Settings workspace",
            license="MIT",
            check_flags="safe-html",
        )
        self.project.workspace = workspace
        self.project.inherit_license = True
        self.project.check_flags = "strict-same"
        self.project.save()
        category = Category.objects.create(
            name="Parent category",
            slug="parent-category",
            project=self.project,
            commit_message="Category commit",
            inherit_commit_message=False,
            check_flags="xml-text",
        )
        child = Category.objects.create(
            name="Child category",
            slug="child-category",
            project=self.project,
            category=category,
            check_flags="python-format",
        )
        self.component.category = child
        self.component.inherit_license = True
        self.component.inherit_commit_message = True
        self.component.check_flags = "ignore-same"
        self.component.save()

        component = Component.objects.select_related(
            "project",
            "project__workspace",
            "category",
            "category__category",
        ).get(pk=self.component.pk)

        self.assertEqual(component.effective_license, "MIT")
        self.assertEqual(component.effective_commit_message, "Category commit")
        self.assertEqual(
            set(component.all_flags),
            {
                "safe-html",
                "strict-same",
                "xml-text",
                "python-format",
                "ignore-same",
            },
        )

    def test_category_consolidation_folds_matching_blank_setting(self) -> None:
        category = Category.objects.create(
            name="Settings category", slug="settings-category", project=self.project
        )
        Component.objects.filter(pk=self.component.pk).update(
            category=category,
            agreement="",
            inherit_agreement=False,
        )

        self.consolidate_category_inherited_settings()

        category.refresh_from_db()
        component = Component.objects.get(pk=self.component.pk)
        self.assertTrue(category.inherit_agreement)
        self.assertEqual(category.agreement, "")
        self.assertTrue(component.inherit_agreement)
        self.assertEqual(component.effective_agreement, "")

    def test_category_consolidation_folds_matching_parent_setting(self) -> None:
        category = Category.objects.create(
            name="Settings category", slug="settings-category", project=self.project
        )
        Component.objects.filter(pk=self.component.pk).update(
            category=category,
            new_lang=self.project.new_lang,
            inherit_new_lang=False,
        )

        self.consolidate_category_inherited_settings()

        category.refresh_from_db()
        component = Component.objects.get(pk=self.component.pk)
        self.assertTrue(category.inherit_new_lang)
        self.assertEqual(category.new_lang, self.project.new_lang)
        self.assertTrue(component.inherit_new_lang)
        self.assertEqual(component.effective_new_lang, self.project.new_lang)

    def test_category_consolidation_keeps_different_parent_override(self) -> None:
        self.project.new_lang = "none"
        self.project.save(update_fields=["new_lang"])
        category = Category.objects.create(
            name="Settings category", slug="settings-category", project=self.project
        )
        Component.objects.filter(pk=self.component.pk).update(
            category=category,
            new_lang="add",
            inherit_new_lang=False,
        )

        self.consolidate_category_inherited_settings()

        category.refresh_from_db()
        component = Component.objects.get(pk=self.component.pk)
        self.assertFalse(category.inherit_new_lang)
        self.assertEqual(category.new_lang, "add")
        self.assertTrue(component.inherit_new_lang)
        self.assertEqual(component.effective_new_lang, "add")

    def test_category_consolidation_promotes_acceptance_to_inherited_owner(
        self,
    ) -> None:
        self.project.agreement = "Project agreement"
        self.project.save(update_fields=["agreement"])
        second_component = self.create_po(name="Second", project=self.project)
        category = Category.objects.create(
            name="Settings category", slug="settings-category", project=self.project
        )
        Component.objects.filter(
            pk__in=[self.component.pk, second_component.pk]
        ).update(
            category=category,
            agreement=self.project.agreement,
            inherit_agreement=False,
        )
        self.component.refresh_from_db()
        second_component.refresh_from_db()
        ContributorAgreement.objects.create(self.user, self.component)

        self.consolidate_category_inherited_settings()

        category.refresh_from_db()
        component = Component.objects.get(pk=self.component.pk)
        self.assertTrue(category.inherit_agreement)
        self.assertTrue(component.inherit_agreement)
        self.assertTrue(
            ContributorAgreement.objects.filter(
                user=self.user, project=self.project
            ).exists()
        )
        self.assertFalse(
            ContributorAgreement.objects.filter(
                user=self.user, category=category
            ).exists()
        )
        self.assertTrue(ContributorAgreement.objects.has_agreed(self.user, component))
        second_component = Component.objects.get(pk=second_component.pk)
        self.assertTrue(
            ContributorAgreement.objects.has_agreed(self.user, second_component)
        )

    def test_component_consolidation_promotes_partial_acceptance(self) -> None:
        second_component = self.create_po(name="Second", project=self.project)
        Component.objects.filter(
            pk__in=[self.component.pk, second_component.pk]
        ).update(
            agreement="Project agreement",
            inherit_agreement=False,
        )
        self.component.refresh_from_db()
        second_component.refresh_from_db()
        ContributorAgreement.objects.create(self.user, self.component)

        self.consolidate_inherited_settings()

        self.project.refresh_from_db()
        component = Component.objects.get(pk=self.component.pk)
        second_component = Component.objects.get(pk=second_component.pk)
        self.assertEqual(self.project.agreement, "Project agreement")
        self.assertTrue(component.inherit_agreement)
        self.assertTrue(second_component.inherit_agreement)
        self.assertTrue(
            ContributorAgreement.objects.filter(
                user=self.user, project=self.project
            ).exists()
        )
        self.assertTrue(ContributorAgreement.objects.has_agreed(self.user, component))
        self.assertTrue(
            ContributorAgreement.objects.has_agreed(self.user, second_component)
        )

    def test_workspace_consolidation_promotes_partial_acceptance(self) -> None:
        workspace = Workspace.objects.create(name="Settings workspace")
        second_project = self.create_project(
            name="Second project",
            slug="second-project",
            workspace=workspace,
            agreement="Workspace agreement",
            inherit_agreement=False,
        )
        Project.objects.filter(pk=self.project.pk).update(
            workspace=workspace,
            agreement="Workspace agreement",
            inherit_agreement=False,
        )
        self.project.refresh_from_db()
        ContributorAgreement.objects.create(user=self.user, project=self.project)

        self.consolidate_workspace_inherited_settings()

        workspace.refresh_from_db()
        self.project.refresh_from_db()
        second_project.refresh_from_db()
        self.assertEqual(workspace.agreement, "Workspace agreement")
        self.assertTrue(self.project.inherit_agreement)
        self.assertTrue(second_project.inherit_agreement)
        self.assertTrue(
            ContributorAgreement.objects.filter(
                user=self.user, workspace=workspace
            ).exists()
        )

    def test_license_repair_uses_most_common_component_license(self) -> None:
        second_component = self.create_po(name="license-second", project=self.project)
        third_component = self.create_po(name="license-third", project=self.project)
        Project.objects.filter(pk=self.project.pk).update(
            license="proprietary", inherit_license=True
        )
        Component.objects.filter(
            pk__in=[self.component.pk, second_component.pk]
        ).update(license="MIT", inherit_license=False)
        Component.objects.filter(pk=third_component.pk).update(
            license="GPL-3.0-or-later", inherit_license=False
        )

        self.repair_license_inheritance()

        self.project.refresh_from_db()
        self.assertEqual(self.project.license, "MIT")
        self.assertFalse(self.project.inherit_license)

    def test_license_repair_tie_uses_earliest_component_license(self) -> None:
        second_component = self.create_po(name="license-second", project=self.project)
        Project.objects.filter(pk=self.project.pk).update(
            license="proprietary", inherit_license=True
        )
        Component.objects.filter(pk=self.component.pk).update(
            license="GPL-3.0-or-later", inherit_license=False
        )
        Component.objects.filter(pk=second_component.pk).update(
            license="MIT", inherit_license=False
        )

        self.repair_license_inheritance()

        self.project.refresh_from_db()
        self.assertEqual(self.project.license, "GPL-3.0-or-later")
        self.assertFalse(self.project.inherit_license)

    def test_license_repair_ignores_inherited_component_license(self) -> None:
        second_component = self.create_po(name="license-second", project=self.project)
        Project.objects.filter(pk=self.project.pk).update(
            license="proprietary", inherit_license=True
        )
        Component.objects.filter(pk=self.component.pk).update(
            license="MIT", inherit_license=False
        )
        Component.objects.filter(pk=second_component.pk).update(
            license="GPL-3.0-or-later", inherit_license=True
        )

        self.repair_license_inheritance()

        self.project.refresh_from_db()
        self.assertEqual(self.project.license, "MIT")
        self.assertFalse(self.project.inherit_license)

    def test_license_repair_backfills_workspace_from_corrected_project(self) -> None:
        workspace = Workspace.objects.create(
            name="License repair workspace", license="proprietary"
        )
        second_project = self.create_project(
            name="License repair second project",
            slug="license-repair-second-project",
            workspace=workspace,
            license="GPL-3.0-or-later",
            inherit_license=False,
        )
        Project.objects.filter(pk=self.project.pk).update(
            workspace=workspace, license="proprietary", inherit_license=True
        )
        Component.objects.filter(pk=self.component.pk).update(
            license="MIT", inherit_license=False
        )

        self.repair_license_inheritance()

        self.project.refresh_from_db()
        second_project.refresh_from_db()
        workspace.refresh_from_db()
        self.assertEqual(self.project.license, "MIT")
        self.assertFalse(self.project.inherit_license)
        self.assertEqual(second_project.license, "GPL-3.0-or-later")
        self.assertEqual(workspace.license, "MIT")

    def test_license_repair_keeps_workspace_license_with_inheriting_project(
        self,
    ) -> None:
        workspace = Workspace.objects.create(
            name="License repair workspace", license="proprietary"
        )
        second_project = self.create_project(
            name="License repair second project",
            slug="license-repair-second-project",
            workspace=workspace,
            license="GPL-3.0-or-later",
            inherit_license=True,
        )
        Project.objects.filter(pk=self.project.pk).update(
            workspace=workspace, license="MIT", inherit_license=True
        )

        self.repair_license_inheritance()

        self.project.refresh_from_db()
        second_project.refresh_from_db()
        workspace.refresh_from_db()
        self.assertEqual(workspace.license, "proprietary")
        self.assertTrue(self.project.inherit_license)
        self.assertTrue(second_project.inherit_license)
        self.assertEqual(self.project.license, "MIT")
        self.assertEqual(second_project.license, "GPL-3.0-or-later")

    def test_license_repair_keeps_explicit_workspace_license(self) -> None:
        workspace = Workspace.objects.create(
            name="License repair workspace", license="GPL-3.0-or-later"
        )
        Project.objects.filter(pk=self.project.pk).update(
            workspace=workspace, license="proprietary", inherit_license=True
        )
        Component.objects.filter(pk=self.component.pk).update(
            license="MIT", inherit_license=False
        )

        self.repair_license_inheritance()

        self.project.refresh_from_db()
        workspace.refresh_from_db()
        self.assertEqual(self.project.license, "MIT")
        self.assertFalse(self.project.inherit_license)
        self.assertEqual(workspace.license, "GPL-3.0-or-later")

    def test_profile_agreement_links_open_agreement_view(self) -> None:
        workspace = Workspace.objects.create(
            name="Settings workspace", agreement="Workspace agreement"
        )
        Project.objects.filter(pk=self.project.pk).update(
            workspace=workspace,
            agreement="Project agreement",
            inherit_agreement=False,
        )
        self.project.refresh_from_db()
        category = Category.objects.create(
            name="Settings category",
            slug="settings-category",
            project=self.project,
            agreement="Category agreement",
            inherit_agreement=False,
        )

        ContributorAgreement.objects.create(user=self.user, workspace=workspace)
        ContributorAgreement.objects.create(user=self.user, project=self.project)
        ContributorAgreement.objects.create(user=self.user, category=category)

        profile = self.client.get(reverse("profile"))
        for obj, text in (
            (workspace, "Workspace agreement"),
            (self.project, "Project agreement"),
            (category, "Category agreement"),
        ):
            url = reverse("contributor-agreement", kwargs={"path": obj.get_url_path()})
            self.assertContains(profile, url)
            response = self.client.get(url)
            self.assertContains(response, text)

    def test_project_agreement_confirm_uses_effective_owner(self) -> None:
        workspace = Workspace.objects.create(
            name="Settings workspace", agreement="Workspace agreement"
        )
        Project.objects.filter(pk=self.project.pk).update(
            workspace=workspace,
            agreement="",
            inherit_agreement=True,
        )
        self.component.inherit_agreement = True
        self.component.save(update_fields=["inherit_agreement"])
        self.project.refresh_from_db()

        url = reverse(
            "contributor-agreement", kwargs={"path": self.project.get_url_path()}
        )
        response = self.client.post(url, {"confirm": "on"}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ContributorAgreement.objects.filter(
                user=self.user, workspace=workspace
            ).exists()
        )
        self.assertFalse(
            ContributorAgreement.objects.filter(
                user=self.user, project=self.project
            ).exists()
        )
        self.assertTrue(
            ContributorAgreement.objects.has_agreed(self.user, self.component)
        )

    def test_category_agreement_confirm_uses_effective_owner(self) -> None:
        parent = Category.objects.create(
            name="Parent settings category",
            slug="parent-settings-category",
            project=self.project,
            agreement="Parent agreement",
            inherit_agreement=False,
        )
        child = Category.objects.create(
            name="Child settings category",
            slug="child-settings-category",
            project=self.project,
            category=parent,
            agreement="",
            inherit_agreement=True,
        )
        self.component.category = child
        self.component.inherit_agreement = True
        self.component.save(update_fields=["category", "inherit_agreement"])

        url = reverse("contributor-agreement", kwargs={"path": child.get_url_path()})
        response = self.client.post(url, {"confirm": "on"}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ContributorAgreement.objects.filter(
                user=self.user, category=parent
            ).exists()
        )
        self.assertFalse(
            ContributorAgreement.objects.filter(user=self.user, category=child).exists()
        )
        self.assertTrue(
            ContributorAgreement.objects.has_agreed(self.user, self.component)
        )

    def test_component_setting_change_disables_inheritance(self) -> None:
        self.project.license = "MIT"
        self.project.save()
        self.component.inherit_license = True
        self.component.save()

        self.component.license = "GPL-3.0-or-later"
        self.component.save()

        component = Component.objects.get(pk=self.component.pk)
        self.assertFalse(component.inherit_license)
        self.assertEqual(component.effective_license, "GPL-3.0-or-later")

    def test_project_setting_change_disables_inheritance(self) -> None:
        workspace = Workspace.objects.create(name="Settings workspace", license="MIT")
        self.project.workspace = workspace
        self.project.inherit_license = True
        self.project.save()

        self.project.license = "GPL-3.0-or-later"
        self.project.save()

        project = Project.objects.get(pk=self.project.pk)
        self.assertFalse(project.inherit_license)
        self.assertEqual(project.get_effective_setting("license"), "GPL-3.0-or-later")

    def test_category_setting_change_disables_inheritance(self) -> None:
        category = Category.objects.create(
            name="Settings category", slug="settings-category", project=self.project
        )
        category.inherit_license = True
        category.save()

        category.license = "GPL-3.0-or-later"
        category.save()

        category = Category.objects.get(pk=category.pk)
        self.assertFalse(category.inherit_license)
        self.assertEqual(category.get_effective_setting("license"), "GPL-3.0-or-later")

    def test_inherited_agreement_acceptance_uses_owner_scope(self) -> None:
        self.project.agreement = "Project agreement"
        self.project.save()
        self.component.inherit_agreement = True
        self.component.save()

        ContributorAgreement.objects.create(self.user, self.component)

        agreement = ContributorAgreement.objects.get(user=self.user)
        self.assertIsNone(agreement.component_id)
        self.assertEqual(agreement.project_id, self.project.pk)
        self.assertTrue(
            ContributorAgreement.objects.has_agreed(self.user, self.component)
        )

    def test_category_agreement_acceptance_uses_owner_scope(self) -> None:
        category = Category.objects.create(
            name="Settings category",
            slug="settings-category",
            project=self.project,
            agreement="Category agreement",
            inherit_agreement=False,
        )
        self.component.category = category
        self.component.inherit_agreement = True
        self.component.save()

        ContributorAgreement.objects.create(self.user, self.component)

        agreement = ContributorAgreement.objects.get(user=self.user)
        self.assertIsNone(agreement.component_id)
        self.assertIsNone(agreement.project_id)
        self.assertEqual(agreement.category_id, category.pk)
        self.assertTrue(
            ContributorAgreement.objects.has_agreed(self.user, self.component)
        )

    def test_project_denied(self) -> None:
        url = reverse("settings", kwargs={"path": self.project.get_url_path()})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_project(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.project.component_set.update(license="MIT")
        url = reverse("settings", kwargs={"path": self.project.get_url_path()})
        response = self.client.get(url)
        self.assertContains(response, "Settings")
        data = get_form_data(response.context["form"].initial)
        data["web"] = "https://example.com/test/"
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Settings saved")
        self.assertEqual(
            Project.objects.get(pk=self.project.pk).web, "https://example.com/test/"
        )

    def test_project_language_denied(self) -> None:
        projlang = self.project.project_languages[self.translation.language]
        url = reverse("settings", kwargs={"path": projlang.get_url_path()})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_project_language_component_admin_denied(self) -> None:
        group = Group.objects.create(
            name="Component admins", language_selection=SELECTION_ALL
        )
        group.roles.add(Role.objects.get(name="Administration"))
        group.components.add(self.component)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        project_language = self.project.project_languages[self.translation.language]
        self.assertTrue(self.user.has_perm("component.edit", self.component))
        self.assertFalse(self.user.has_perm("project.edit", self.project))
        self.assertFalse(self.user.has_perm("project.edit", project_language))

        url = reverse("settings", kwargs={"path": project_language.get_url_path()})
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.post(
                url,
                {"workflow-enable": 1, "workflow-restrict_direct_editing": 1},
            ).status_code,
            404,
        )
        self.assertFalse(
            WorkflowSetting.objects.filter(
                project=self.project, language=self.translation.language
            ).exists()
        )

    def test_project_language(self) -> None:
        projlang = self.project.project_languages[self.translation.language]
        self.assertIsNone(projlang.workflow_settings)
        self.project.add_user(self.user, "Administration")
        self.project.component_set.update(license="MIT")
        url = reverse("settings", kwargs={"path": projlang.get_url_path()})
        response = self.client.get(url)
        self.assertContains(response, "Settings")
        response = self.client.post(
            url,
            {
                "workflow-enable": 1,
                "workflow-restrict_direct_editing": 1,
                "workflow-suggestion_autoaccept": 0,
            },
            follow=True,
        )
        self.assertContains(response, "Settings saved")
        workflow_settings = (
            Project.objects.get(pk=self.project.pk)
            .project_languages[self.translation.language]
            .workflow_settings
        )
        self.assertIsNotNone(workflow_settings)
        self.assertTrue(workflow_settings.restrict_direct_editing)
        self.assertTrue(
            WorkflowSetting.objects.filter(
                project=self.project,
                language=self.translation.language,
                restrict_direct_editing=True,
            ).exists()
        )
        response = self.client.post(
            url, {"workflow-suggestion_autoaccept": 0}, follow=True
        )
        self.assertContains(response, "Settings saved")
        self.assertIsNone(
            Project.objects.get(pk=self.project.pk)
            .project_languages[self.translation.language]
            .workflow_settings
        )

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    @override_settings(LICENSE_REQUIRED=True)
    def test_change_access(self) -> None:
        self.project.add_user(self.user, "Administration")
        url = reverse("settings", kwargs={"path": self.project.get_url_path()})

        # Get initial form data
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data["access_control"] = Project.ACCESS_PROTECTED

        # No permissions
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "error_1_id_access_control")

        # Allow editing by creating billing plan
        billing = create_test_billing(self.user)
        billing.add_project(self.project)

        # Editing should now work, but components do not have a license
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You must specify a license for these components")

        # Set component license
        self.project.component_set.update(license="MIT")

        # Editing should now work
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, url)

        # Verify change has been done
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.access_control, Project.ACCESS_PROTECTED)
        change = project.change_set.filter(action=ActionEvents.ACCESS_EDIT).get()

        # Check change details display
        self.assertEqual(change.get_details_display(trusted=True), "Protected")

    def test_change_public_sharing(self) -> None:
        self.project.add_user(self.user, "Administration")
        url = reverse("settings", kwargs={"path": self.project.get_url_path()})
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data["public_sharing"] = True

        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, url)
        self.project.refresh_from_db()
        self.assertFalse(self.project.public_sharing)

        billing = create_test_billing(self.user)
        billing.add_project(self.project)
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, url)

        self.project.refresh_from_db()
        self.assertTrue(self.project.public_sharing)

    def test_project_audit_settings(self) -> None:
        self.enterContext(acting_user_context(self.user))
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.public_sharing = True
        self.project.enforced_2fa = True
        self.project.translation_review = True
        self.project.source_review = True
        self.project.commit_policy = CommitPolicyChoices.WITHOUT_NEEDS_EDITING
        self.project.enable_hooks = False
        self.project.use_shared_tm = False
        self.project.contribute_shared_tm = False
        self.project.use_workspace_tm = True
        self.project.contribute_workspace_tm = True
        self.project.check_flags = "strict-same"
        self.project.enforced_checks = ["same"]
        self.project.inherit_enforced_checks = False
        self.project.save()

        access_change = self.project.change_set.get(action=ActionEvents.ACCESS_EDIT)
        self.assertEqual(access_change.user, self.user)
        self.assertEqual(
            access_change.details["access_control"], Project.ACCESS_PRIVATE
        )

        setting_changes = self.project.change_set.filter(
            action=ActionEvents.PROJECT_SETTING_CHANGE
        )
        self.assertEqual(
            {change.details["field"] for change in setting_changes},
            set(Project.AUDIT_SETTINGS),
        )
        self.assertTrue(all(change.user == self.user for change in setting_changes))
        review_change = setting_changes.get(details__field="translation_review")
        policy_change = setting_changes.get(details__field="commit_policy")
        self.assertEqual(
            review_change.get_details_display(trusted=True),
            'Enable reviews changed from "disabled" to "enabled".',
        )
        self.assertEqual(
            policy_change.get_details_display(trusted=True),
            'Translation quality filter changed from "Commit all translations '
            'regardless of quality" to "Skip translations marked as needing editing".',
        )

    def test_project_move(self) -> None:
        self.project.add_user(self.user, "Administration")
        current_workspace = Workspace.objects.create(name="Current workspace")
        target_workspace = Workspace.objects.create(name="Target workspace")
        Project.objects.filter(pk=self.project.pk).update(workspace=current_workspace)
        self.project.refresh_from_db()
        current_workspace.add_owner(self.user)
        target_workspace.add_owner(self.user)
        self.user.clear_permissions_cache()

        response = self.client.get(self.project.get_absolute_url())
        self.assertContains(response, "Move project")
        self.assertFalse(response.context["move_form"].use_uuid_input)

        response = self.client.post(
            reverse("move", kwargs={"path": self.project.get_url_path()}),
            {"workspace": str(target_workspace.pk)},
            follow=True,
        )
        self.assertContains(response, "Project moved.")
        self.project.refresh_from_db()
        self.assertEqual(self.project.workspace_id, target_workspace.pk)
        change = self.project.change_set.get(action=ActionEvents.MOVE_PROJECT)
        self.assertEqual(
            change.get_details_display(trusted=True),
            'Project moved from "Current workspace" to "Target workspace".',
        )

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_project_move_public_plan(self) -> None:
        self.project.add_user(self.user, "Administration")
        source = Workspace.objects.create(name="Source move workspace")
        source.add_owner(self.user)
        billing = create_test_billing(self.user)
        billing.plan.change_access_control = False
        billing.plan.save(update_fields=["change_access_control"])
        self.user.clear_permissions_cache()
        url = reverse("move", kwargs={"path": self.project.get_url_path()})
        for access, restricted in (
            (Project.ACCESS_PRIVATE, False),
            (Project.ACCESS_PROTECTED, False),
            (Project.ACCESS_PUBLIC, True),
            (Project.ACCESS_PUBLIC, False),
        ):
            with self.subTest(access=access, restricted=restricted):
                Project.objects.filter(pk=self.project.pk).update(
                    workspace=source, access_control=access
                )
                self.project.component_set.update(
                    restricted=restricted, license="MIT", inherit_license=False
                )
                response = self.client.post(
                    url, {"workspace": str(billing.workspace_id)}, follow=True
                )
                self.project.refresh_from_db()
                if access == Project.ACCESS_PUBLIC and not restricted:
                    self.assertContains(response, "Project moved.")
                    self.assertEqual(self.project.workspace_id, billing.workspace_id)
                else:
                    self.assertContains(response, "only allows public projects")
                    self.assertEqual(self.project.workspace_id, source.pk)

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_project_move_public_plan_recheck(self) -> None:
        self.project.add_user(self.user, "Administration")
        source = Workspace.objects.create(name="Source plan recheck workspace")
        source.add_owner(self.user)
        Project.objects.filter(pk=self.project.pk).update(
            workspace=source, access_control=Project.ACCESS_PRIVATE
        )
        self.project.component_set.update(license="MIT", inherit_license=False)
        billing = create_test_billing(self.user)
        billing.plan.change_access_control = True
        billing.plan.save(update_fields=["change_access_control"])
        self.user.clear_permissions_cache()
        original = ProjectMoveForm.is_valid

        def restrict_plan(form: ProjectMoveForm) -> bool:
            valid = original(form)
            if valid:
                billing.plan.change_access_control = False
                billing.plan.save(update_fields=["change_access_control"])
            return valid

        with patch.object(ProjectMoveForm, "is_valid", restrict_plan):
            response = self.client.post(
                reverse("move", kwargs={"path": self.project.get_url_path()}),
                {"workspace": str(billing.workspace_id)},
                follow=True,
            )
        self.assertContains(response, "only allows public projects")
        self.project.refresh_from_db()
        self.assertEqual(self.project.workspace_id, source.pk)
        self.assertFalse(
            self.project.change_set.filter(action=ActionEvents.MOVE_PROJECT).exists()
        )

    def test_project_move_reports_machinery_conflicts(self) -> None:
        self.project.add_user(self.user, "Administration")
        target = Workspace.objects.create(name="Target workspace")
        target.add_owner(self.user)
        self.user.clear_permissions_cache()
        MachineryInstallation.objects.filter(
            engine="weblate", project=None, workspace=None
        ).update(enabled=False)
        for engine, slug in (("openai", "shared"), ("weblate", "")):
            with self.subTest(engine=engine):
                local = MachineryInstallation.objects.create(
                    project=self.project, engine=engine, slug=slug
                )
                inherited = MachineryInstallation.objects.create(
                    workspace=target, engine=engine, slug=slug
                )
                response = self.client.post(
                    reverse("move", kwargs={"path": self.project.get_url_path()}),
                    {"workspace": str(target.pk)},
                    follow=True,
                )
                self.assertContains(response, "conflict with the new workspace")
                self.project.refresh_from_db()
                self.assertIsNone(self.project.workspace_id)
                self.assertFalse(
                    self.project.change_set.filter(
                        action=ActionEvents.MOVE_PROJECT
                    ).exists()
                )
                local.delete()
                inherited.delete()

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_project_move_to_billing_workspace_updates_name(self) -> None:
        self.project.add_user(self.user, "Administration")
        current_workspace = Workspace.objects.create(name="Current workspace")
        Project.objects.filter(pk=self.project.pk).update(workspace=current_workspace)
        self.project.refresh_from_db()
        current_workspace.add_owner(self.user)
        billing = create_test_billing(self.user)
        self.user.clear_permissions_cache()

        response = self.client.post(
            reverse("move", kwargs={"path": self.project.get_url_path()}),
            {"workspace": str(billing.workspace_id)},
            follow=True,
        )

        self.assertContains(response, "Project moved.")
        self.project.refresh_from_db()
        billing.workspace.refresh_from_db()
        self.assertEqual(self.project.workspace_id, billing.workspace_id)
        self.assertEqual(billing.workspace.name, self.project.name)

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_project_move_rechecks_billing_after_form_validation(self) -> None:
        self.project.add_user(self.user, "Administration")
        current_workspace = Workspace.objects.create(name="Current move workspace")
        Project.objects.filter(pk=self.project.pk).update(workspace=current_workspace)
        self.project.refresh_from_db()
        current_workspace.add_owner(self.user)
        billing = create_test_billing(self.user)
        self.user.clear_permissions_cache()
        original_is_valid = ProjectMoveForm.is_valid

        def fill_slot(form):
            result = original_is_valid(form)
            if result:
                Project.objects.create(
                    name="Competing browser move project",
                    slug="competing-browser-move-project",
                    workspace_id=billing.workspace_id,
                )
            return result

        with patch.object(ProjectMoveForm, "is_valid", fill_slot):
            response = self.client.post(
                reverse("move", kwargs={"path": self.project.get_url_path()}),
                {"workspace": str(billing.workspace_id)},
                follow=True,
            )
        self.assertContains(response, "No valid billing found or limit exceeded.")
        self.project.refresh_from_db()
        self.assertEqual(self.project.workspace_id, current_workspace.pk)

    def test_project_move_requires_target_add_project(self) -> None:
        self.project.add_user(self.user, "Administration")
        current_workspace = Workspace.objects.create(name="Current workspace")
        target_workspace = Workspace.objects.create(name="Target workspace")
        Project.objects.filter(pk=self.project.pk).update(workspace=current_workspace)
        self.project.refresh_from_db()
        current_workspace.add_owner(self.user)

        role = Role.objects.create(name="Target workspace edit")
        role.permissions.add(Permission.objects.get(codename="workspace.edit"))
        group = Group.objects.create(
            name="Target workspace editors",
            defining_workspace=target_workspace,
        )
        group.roles.add(role)
        self.user.add_team(None, group)
        self.user.clear_permissions_cache()

        response = self.client.get(self.project.get_absolute_url())
        self.assertNotContains(response, "Move project")

        response = self.client.post(
            reverse("move", kwargs={"path": self.project.get_url_path()}),
            {"workspace": str(target_workspace.pk)},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.workspace_id, current_workspace.pk)

    def test_project_move_uuid_input(self) -> None:
        self.project.add_user(self.user, "Administration")
        current_workspace = Workspace.objects.create(name="Current workspace")
        first_workspace = Workspace.objects.create(name="First target")
        second_workspace = Workspace.objects.create(name="Second target")
        Project.objects.filter(pk=self.project.pk).update(workspace=current_workspace)
        self.project.refresh_from_db()
        current_workspace.add_owner(self.user)
        first_workspace.add_owner(self.user)
        second_workspace.add_owner(self.user)
        self.user.clear_permissions_cache()

        with patch("weblate.trans.forms.PROJECT_MOVE_WORKSPACE_SELECT_LIMIT", 1):
            response = self.client.get(self.project.get_absolute_url())
            move_form = response.context["move_form"]
            self.assertTrue(move_form.use_uuid_input)

            response = self.client.post(
                reverse("move", kwargs={"path": self.project.get_url_path()}),
                {"workspace": str(second_workspace.pk)},
                follow=True,
            )
        self.assertContains(response, "Project moved.")
        self.project.refresh_from_db()
        self.assertEqual(self.project.workspace_id, second_workspace.pk)

    def test_commit_policy(self) -> None:
        self.project.add_user(self.user, "Administration")
        url = reverse("settings", kwargs={"path": self.project.get_url_path()})

        self.assertFalse(self.project.translation_review)

        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data["commit_policy"] = CommitPolicyChoices.APPROVED_ONLY
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Approved-only commit policy requires translation reviews to be enabled.",
        )
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.commit_policy, CommitPolicyChoices.ALL)

        data["translation_review"] = True
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, url)
        project = Project.objects.get(pk=self.project.pk)
        self.assertTrue(project.translation_review)

        data["translation_review"] = False
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Translation reviews are required for approved-only commit policy.",
        )
        project = Project.objects.get(pk=self.project.pk)
        self.assertTrue(project.translation_review)

        data["commit_policy"] = CommitPolicyChoices.WITHOUT_NEEDS_EDITING
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, url)
        project = Project.objects.get(pk=self.project.pk)
        self.assertFalse(project.translation_review)
        self.assertEqual(
            project.commit_policy, CommitPolicyChoices.WITHOUT_NEEDS_EDITING
        )

    def test_component_denied(self) -> None:
        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_component(self) -> None:
        self.assertEqual(Check.objects.filter(name="same").count(), 2)
        self.project.add_user(self.user, "Administration")
        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        self.assertContains(response, "Settings")
        data = cast(
            "dict[str, object]", get_form_data(response.context["form"].initial)
        )
        data["license"] = "MIT"
        data["enforced_checks"] = ["same", "duplicate"]
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Settings saved")
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.license, "MIT")
        self.assertEqual(component.enforced_checks, ["same", "duplicate"])
        self.assertEqual(
            component.change_set.get(action=ActionEvents.LICENSE_CHANGE).user,
            self.user,
        )
        self.assertEqual(Check.objects.filter(name="same").count(), 2)
        for unit in Unit.objects.filter(check__name="same"):
            self.assertFalse(
                unit.translated, f"{unit} should not be marked as translated"
            )

    def test_component_repository_locked(self) -> None:
        self.project.add_user(self.user, "Administration")
        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data["license"] = "MIT"
        lock_error = WeblateLockTimeoutError(
            "repository locked", lock=self.component.repository.lock.lock_object
        )

        with patch.object(Component, "locked_for_update", side_effect=lock_error):
            response = self.client.post(url, data, follow=True)

        self.assertRedirects(response, url)
        self.assertContains(
            response,
            "There appears to be an ongoing operation on the repository. "
            "Please try again later.",
        )
        self.component.refresh_from_db()
        self.assertNotEqual(self.component.license, "MIT")

    def test_component_inherited_required_license_validates(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.project.license = "MIT"
        self.project.save(update_fields=["license"])
        self.component.license = ""
        self.component.inherit_license = True
        self.component.save(update_fields=["license", "inherit_license"])

        # ruff: ignore[private-member-access]
        field = Component._meta.get_field("license")
        old_blank = field.blank
        field.blank = False
        try:
            url = reverse("settings", kwargs=self.kw_component)
            response = self.client.get(url)
            data = cast(
                "dict[str, object]", get_form_data(response.context["form"].initial)
            )
            data.pop("license", None)
            response = self.client.post(url, data, follow=True)
        finally:
            field.blank = old_blank

        self.assertContains(response, "Settings saved")
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.license, "")
        self.assertTrue(component.inherit_license)
        self.assertEqual(component.effective_license, "MIT")

    def test_component_audit_settings(self) -> None:
        self.enterContext(acting_user_context(self.user))
        self.component.restricted = True
        self.component.enable_suggestions = False
        self.component.suggestion_voting = True
        self.component.suggestion_autoaccept = 1
        self.component.new_lang = "none"
        self.component.manage_units = True
        self.component.allow_translation_propagation = False
        self.component.contribute_project_tm = False
        self.component.check_flags = "strict-same"
        self.component.enforced_checks = ["same"]
        self.component.save()

        setting_changes = self.component.change_set.filter(
            action=ActionEvents.COMPONENT_SETTING_CHANGE
        )
        self.assertEqual(
            {change.details["field"] for change in setting_changes},
            set(Component.AUDIT_SETTINGS),
        )
        self.assertTrue(all(change.user == self.user for change in setting_changes))
        restricted_change = setting_changes.get(details__field="restricted")
        new_lang_change = setting_changes.get(details__field="new_lang")
        self.assertEqual(
            restricted_change.get_details_display(trusted=True),
            'Restricted component changed from "disabled" to "enabled".',
        )
        self.assertEqual(
            new_lang_change.get_details_display(trusted=True),
            'Adding new translation changed from "Contact maintainers" to '
            '"Disable adding new translations".',
        )

    def test_component_post_locks_component_before_binding_form(self) -> None:
        self.project.add_user(self.user, "Administration")
        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data["license"] = "MIT"

        events: list[tuple[str, int]] = []
        original_get_for_update = ComponentQuerySet.get_for_update
        original_form_init = ComponentSettingsForm.__init__

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
                ComponentSettingsForm,
                "__init__",
                autospec=True,
                side_effect=record_form_init,
            ),
        ):
            response = self.client.post(url, data)

        self.assertRedirects(response, url, fetch_redirect_response=False)
        lock_index = events.index(("lock", self.component.pk))
        form_init_index = events.index(("form_init", self.component.pk))
        self.assertLess(
            lock_index,
            form_init_index,
            "Component row should be locked before the bound settings form is created",
        )

    def test_component_post_acquires_repository_lock_before_row_lock(self) -> None:
        self.project.add_user(self.user, "Administration")
        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data["license"] = "MIT"

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
            response = self.client.post(url, data)

        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.assertLess(
            events.index(("repo_lock", self.component.pk)),
            events.index(("row_lock", self.component.pk)),
            "Component repository lock should be acquired before the row lock",
        )

    def test_component_post_reuses_repository_lock_during_validation(self) -> None:
        self.project.add_user(self.user, "Administration")
        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        # Preserve checkbox values so the submission does not trigger a rescan.
        data.update(
            {
                f"file_format_params_{name}": value
                for name, value in get_effective_params_for_file_format(
                    self.component.file_format, self.component.file_format_params
                ).items()
            }
        )
        data["license"] = "MIT"

        original_clean = Component.clean

        def clean_with_fresh_repository_lock(instance):
            instance.drop_repository_cache()
            with instance.repository.lock:
                return original_clean(instance)

        with (
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            patch.object(
                Component,
                "clean",
                autospec=True,
                side_effect=clean_with_fresh_repository_lock,
            ),
            patch.object(FileLock, "acquire", autospec=True) as acquire,
            patch.object(FileLock, "release", autospec=True) as release,
        ):
            response = self.client.post(url, data)

        self.assertRedirects(response, url, fetch_redirect_response=False)
        acquire.assert_called_once()
        self.assertEqual(
            sum(
                call.kwargs.get("force", False) is False
                for call in release.call_args_list
            ),
            1,
        )

    def test_linked_component_reuses_repository_lock_during_setup_commit(self) -> None:
        linked_component = self.create_link_existing(
            name="Settings linked lock", slug="settings-linked-lock"
        )
        new_target = self.create_po(name="settings-new-target", project=self.project)
        source_language_id = linked_component.source_language_id
        assert source_language_id is not None
        translation = (
            linked_component.translation_set.exclude(filename="")
            .exclude(language_id=source_language_id)
            .first()
        )
        if translation is None:
            self.fail("Expected a linked component translation with a filename.")
        unit = translation.unit_set.first()
        if unit is None:
            self.fail("Expected at least one linked component unit.")
        PendingUnitChange.store_unit_change(unit=unit, author=self.user)

        self.component.drop_repository_cache()
        linked_component.drop_repository_cache()
        if linked_component.linked_component is not None:
            linked_component.linked_component.drop_repository_cache()

        with (
            override_settings(CELERY_TASK_ALWAYS_EAGER=False),
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            patch.object(Component, "queue_background_task", autospec=True),
            patch.object(
                Translation, "_commit_pending", autospec=True, return_value=False
            ) as commit_pending,
            patch.object(FileLock, "acquire", autospec=True) as acquire,
            patch.object(FileLock, "release", autospec=True) as release,
            linked_component.locked_for_update() as locked_component,
        ):
            locked_component.repo = new_target.get_repo_link_url()
            locked_component.edit_template = False
            locked_component.save()

        commit_pending.assert_called_once()
        acquire.assert_called_once()
        self.assertEqual(
            sum(
                call.kwargs.get("force", False) is False
                for call in release.call_args_list
            ),
            1,
        )

    def test_linked_component_repository_settings_show_effective_values(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.component.push_on_commit = True
        self.component.commit_pending_age = 12
        self.component.auto_lock_error = False
        self.component.vcs_params = {"git_force_push": True}
        self.component.save(
            update_fields=[
                "vcs_params",
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        linked_component = self.create_link_existing(
            name="Settings linked", slug="settings-linked", filemask="po/*.po"
        )
        linked_component.push_on_commit = False
        linked_component.commit_pending_age = 1
        linked_component.auto_lock_error = True
        linked_component.vcs_params = {"git_force_push": False}
        linked_component.save(
            update_fields=[
                "vcs_params",
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )

        url = reverse("settings", kwargs={"path": linked_component.get_url_path()})
        response = self.client.get(url)
        self.assertContains(response, "Settings")
        form = response.context["form"]

        self.assertTrue(form.fields["vcs_params"].disabled)
        self.assertEqual(form.initial["vcs_params"], {"git_force_push": True})
        self.assertTrue(form.fields["push_on_commit"].disabled)
        self.assertTrue(form.initial["push_on_commit"])
        self.assertTrue(form.fields["commit_pending_age"].disabled)
        self.assertEqual(form.initial["commit_pending_age"], 12)
        self.assertTrue(form.fields["auto_lock_error"].disabled)
        self.assertFalse(form.initial["auto_lock_error"])

        data = get_form_data(form.initial)
        data["name"] = "Settings linked renamed"
        data["push_on_commit"] = ""
        data["commit_pending_age"] = 1
        data["auto_lock_error"] = 1
        form = ComponentSettingsForm(
            self.get_request(),
            data,
            instance=linked_component,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        linked_component.refresh_from_db()
        self.assertEqual(linked_component.name, "Settings linked renamed")
        self.assertEqual(linked_component.vcs_params, {"git_force_push": False})
        self.assertFalse(linked_component.push_on_commit)
        self.assertEqual(linked_component.commit_pending_age, 1)
        self.assertTrue(linked_component.auto_lock_error)

    def test_component_settings_do_not_expose_private_link_target(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.component.commit_pending_age = 11
        self.component.save(update_fields=["commit_pending_age"])
        private_project = self.create_project(
            name="Private settings",
            slug="private-settings",
            access_control=Project.ACCESS_PRIVATE,
        )
        private_component = self.create_po(
            project=private_project, name="Private settings"
        )
        private_component.commit_pending_age = 37
        private_component.push_on_commit = True
        private_component.auto_lock_error = True
        private_component.vcs_params = {"merge_request_assignee": "private-assignee"}
        private_component.save(
            update_fields=[
                "commit_pending_age",
                "push_on_commit",
                "auto_lock_error",
                "vcs_params",
            ]
        )
        self.assertFalse(self.user.can_access_component(private_component))

        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        errors = []
        for repo in (
            private_component.get_repo_link_url(),
            "weblate://private-settings/missing",
        ):
            with self.subTest(repo=repo):
                data["repo"] = repo
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 200)
                form = response.context["form"]
                self.assertIn("repo", form.errors)
                errors.append(form.errors)
                self.assertEqual(form.initial["commit_pending_age"], 11)
                self.assertFalse(form.fields["commit_pending_age"].disabled)
                self.assertFalse(form.initial["push_on_commit"])
                self.assertNotContains(response, "private-assignee")
                self.assertNotContains(response, 'name="commit_pending_age" value="37"')

        self.assertEqual(errors[0], errors[1])
        self.component.refresh_from_db()
        self.assertEqual(self.component.commit_pending_age, 11)
        self.assertFalse(self.component.push_on_commit)
        self.assertIsNone(self.component.linked_component_id)

    def test_component_settings_hide_inaccessible_existing_link_target(self) -> None:
        self.project.add_user(self.user, "Administration")
        private_project = self.create_project(
            name="Private linked settings",
            slug="private-linked-settings",
            access_control=Project.ACCESS_PRIVATE,
        )
        private_component = self.create_po(
            project=private_project, name="Private linked settings"
        )
        private_component.commit_pending_age = 37
        private_component.vcs_params = {"merge_request_assignee": "private-assignee"}
        private_component.save(update_fields=["commit_pending_age", "vcs_params"])
        linked_component = self.create_link_existing(
            name="Settings child", slug="settings-child"
        )
        Component.objects.filter(pk=linked_component.pk).update(
            repo=private_component.get_repo_link_url(),
            linked_component=private_component,
            commit_pending_age=11,
        )

        url = reverse("settings", kwargs={"path": linked_component.get_url_path()})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial["commit_pending_age"], 11)
        self.assertFalse(form.fields["commit_pending_age"].disabled)
        self.assertNotContains(response, "private-assignee")
        self.assertNotContains(response, 'name="commit_pending_age" value="37"')

    @mock_dns("github.com", "example.com")
    def test_github_app_component_settings_lock_push_settings(self) -> None:
        self.project.add_user(self.user, "Administration")
        workspace = Workspace.objects.create(name="GitHub App settings")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=workspace,
            repositories=[{"full_name": "test-org/repo"}],
        )
        self.component.vcs = "github-app"
        self.component.repo = "https://github.com/test-org/repo.git"
        self.component.push = "https://example.com/other/repo.git"
        self.component.push_branch = "translations"
        self.component.save(update_fields=["vcs", "repo", "push", "push_branch"])

        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        self.assertContains(response, "Settings")
        form = response.context["form"]

        for field in ("vcs", "repo", "push", "push_branch"):
            self.assertTrue(form.fields[field].disabled)
        self.assertEqual(form.initial["push"], "")
        self.assertEqual(form.initial["push_branch"], "")

        data = get_form_data(form.initial)
        data["push"] = "https://example.com/other/repo.git"
        data["push_branch"] = "translations"
        form = ComponentSettingsForm(
            self.get_request(),
            data,
            instance=self.component,
        )
        with patch.object(Component, "validate_repository_access", return_value=None):
            self.assertTrue(form.is_valid(), form.errors)
            form.save()

        self.component.refresh_from_db()
        self.assertEqual(self.component.push, "")
        self.assertEqual(self.component.push_branch, "")

    def test_component_settings_reject_manual_github_app_vcs(self) -> None:
        self.project.add_user(self.user, "Administration")

        VCS_REGISTRY.clear_cache()
        form = ComponentSettingsForm(self.get_request(), instance=self.component)

        self.assertNotIn("github-app", dict(form.fields["vcs"].choices))

        data = get_form_data(form.initial)
        data["vcs"] = "github-app"
        data["repo"] = "https://github.com/test-org/repo.git"
        form = ComponentSettingsForm(
            self.get_request(),
            data,
            instance=self.component,
        )

        with patch.object(Component, "validate_repository_access", return_value=None):
            self.assertFalse(form.is_valid())
        self.assertIn("vcs", form.errors)

    def test_component_settings_drop_repository_setting_overrides_on_link(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.component.push_on_commit = False
        self.component.commit_pending_age = 1
        self.component.auto_lock_error = True
        self.component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        linked_component = self.create_po(
            name="settings-link-target",
            project=self.project,
        )
        linked_component.push_on_commit = True
        linked_component.commit_pending_age = 12
        linked_component.auto_lock_error = False
        linked_component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )

        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        self.assertContains(response, "Settings")

        data = get_form_data(response.context["form"].initial)
        data["repo"] = linked_component.get_repo_link_url()
        data["branch"] = ""
        data["push"] = ""
        data["push_branch"] = ""
        data["push_on_commit"] = 1
        data["commit_pending_age"] = 12
        data["auto_lock_error"] = ""

        form = ComponentSettingsForm(
            self.get_request(),
            data,
            instance=self.component,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.component.refresh_from_db()
        self.assertEqual(self.component.linked_component_id, linked_component.pk)
        self.assertFalse(self.component.push_on_commit)
        self.assertEqual(self.component.commit_pending_age, 1)
        self.assertTrue(self.component.auto_lock_error)

    def test_linked_component_settings_can_unlink_with_repository_settings(
        self,
    ) -> None:
        self.project.add_user(self.user, "Administration")
        self.component.push_on_commit = True
        self.component.commit_pending_age = 12
        self.component.auto_lock_error = False
        self.component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        linked_component = self.create_link_existing(
            name="Settings linked unlink",
            slug="settings-linked-unlink",
            filemask="po/*.po",
        )
        linked_component.push_on_commit = False
        linked_component.commit_pending_age = 17
        linked_component.auto_lock_error = True
        linked_component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )

        url = reverse("settings", kwargs={"path": linked_component.get_url_path()})
        response = self.client.get(url)
        self.assertContains(response, "Settings")
        self.assertTrue(response.context["form"].fields["push_on_commit"].disabled)

        data = get_form_data(response.context["form"].initial)
        data["repo"] = self.component.repo
        data["branch"] = self.component.branch
        data["push"] = self.component.push
        del data["push_on_commit"]
        del data["commit_pending_age"]
        del data["auto_lock_error"]

        form = ComponentSettingsForm(
            self.get_request(),
            data,
            instance=linked_component,
        )
        self.assertFalse(form.fields["push_on_commit"].disabled)
        self.assertFalse(form.fields["commit_pending_age"].disabled)
        self.assertFalse(form.fields["auto_lock_error"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        linked_component.refresh_from_db()
        self.assertIsNone(linked_component.linked_component_id)
        self.assertEqual(linked_component.repo, self.component.repo)
        self.assertEqual(linked_component.branch, self.component.branch)
        self.assertEqual(linked_component.push, self.component.push)
        self.assertFalse(linked_component.push_on_commit)
        self.assertEqual(linked_component.commit_pending_age, 17)
        self.assertTrue(linked_component.auto_lock_error)


class WorkspaceTMDefaultsTest(ReusableViewTestCase):
    """Workspace translation memory defaults taken from the settings."""

    def test_project_field_defaults_follow_setting(self) -> None:
        # ruff: ignore[private-member-access]
        use_default = Project._meta.get_field("use_workspace_tm").default
        # ruff: ignore[private-member-access]
        contribute_default = Project._meta.get_field("contribute_workspace_tm").default
        self.assertEqual(use_default, settings.DEFAULT_WORKSPACE_TM)
        self.assertEqual(contribute_default, settings.DEFAULT_WORKSPACE_TM)

    @override_settings(OFFER_HOSTING=True, DEFAULT_WORKSPACE_TM=True)
    def test_hosted_contribution_follows_enabled_default(self) -> None:
        data: dict[str, bool] = {}
        Project.apply_hosted_tm_contribution(data)
        self.assertTrue(data["contribute_workspace_tm"])

    @override_settings(OFFER_HOSTING=True, DEFAULT_WORKSPACE_TM=True)
    def test_hosted_explicit_setting_overrides_default(self) -> None:
        data: dict[str, bool] = {"use_workspace_tm": False}
        Project.apply_hosted_tm_contribution(data)
        self.assertFalse(data["contribute_workspace_tm"])
