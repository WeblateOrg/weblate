# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for settings management."""

from unittest.mock import patch

from django.test.utils import modify_settings, override_settings
from django.urls import reverse

from weblate.checks.models import Check
from weblate.trans.actions import ActionEvents
from weblate.trans.forms import ComponentSettingsForm
from weblate.trans.models import CommitPolicyChoices, Component, Project, Unit
from weblate.trans.models.component import ComponentQuerySet
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import create_test_billing
from weblate.utils.views import get_form_data


class SettingsTest(ViewTestCase):
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
            {"workflow-enable": 1, "workflow-suggestion_autoaccept": 0},
            follow=True,
        )
        self.assertContains(response, "Settings saved")
        self.assertIsNotNone(
            Project.objects.get(pk=self.project.pk)
            .project_languages[self.translation.language]
            .workflow_settings
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
        billing.projects.add(self.project)

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
        self.assertEqual(change.get_details_display(), "Protected")

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
        data = get_form_data(response.context["form"].initial)
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

    def test_linked_component_repository_settings_show_effective_values(self) -> None:
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
            name="Settings linked", slug="settings-linked", filemask="po/*.po"
        )
        linked_component.push_on_commit = False
        linked_component.commit_pending_age = 1
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
        form = response.context["form"]

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
        self.assertFalse(linked_component.push_on_commit)
        self.assertEqual(linked_component.commit_pending_age, 1)
        self.assertTrue(linked_component.auto_lock_error)

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
