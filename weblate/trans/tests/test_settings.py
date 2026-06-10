# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for settings management."""

from importlib import import_module
from typing import cast
from unittest.mock import patch

from django.apps import apps
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from filelock import FileLock

from weblate.auth.models import Group, Permission, Role
from weblate.checks.models import Check
from weblate.trans import defaults
from weblate.trans.actions import ActionEvents
from weblate.trans.forms import (
    CategorySettingsForm,
    ComponentSettingsForm,
    ProjectSettingsForm,
)
from weblate.trans.models import (
    Category,
    CommitPolicyChoices,
    Component,
    ContributorAgreement,
    Project,
    Translation,
    Unit,
)
from weblate.trans.models.component import ComponentQuerySet
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import create_test_billing
from weblate.utils.render import (
    validate_render_addon,
    validate_render_commit,
    validate_render_component,
)
from weblate.utils.views import get_form_data
from weblate.vcs.base import RepositoryLock
from weblate.workspaces.models import Workspace


class SettingsTest(ViewTestCase):
    def test_default_message_templates_render(self) -> None:
        validators = (
            (defaults.DEFAULT_COMMIT_MESSAGE, validate_render_commit),
            (defaults.DEFAULT_ADD_MESSAGE, validate_render_commit),
            (defaults.DEFAULT_DELETE_MESSAGE, validate_render_commit),
            (defaults.DEFAULT_MERGE_MESSAGE, validate_render_component),
            (defaults.DEFAULT_ADDON_MESSAGE, validate_render_addon),
            (defaults.DEFAULT_PULL_MESSAGE, validate_render_addon),
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
        for field in ("commit_message",):
            self.assertIn(field, component.get_deferred_fields())
            self.assertIn(field, component.project.get_deferred_fields())
            self.assertIn(field, component.project.workspace.get_deferred_fields())
            if component.category_id:
                self.assertIn(field, component.category.get_deferred_fields())
        for field in ("agreement",):
            self.assertNotIn(field, component.get_deferred_fields())
            self.assertNotIn(field, component.project.get_deferred_fields())
            self.assertNotIn(field, component.project.workspace.get_deferred_fields())
            if component.category_id:
                self.assertNotIn(field, component.category.get_deferred_fields())
        self.assertNotIn("check_flags", component.get_deferred_fields())
        self.assertNotIn("check_flags", component.project.get_deferred_fields())
        self.assertNotIn(
            "check_flags", component.project.workspace.get_deferred_fields()
        )
        if component.category_id:
            self.assertNotIn("check_flags", component.category.get_deferred_fields())

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
        self.assertIsNotNone(unit_id)
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
        self.assertEqual(change.get_details_display(), "Protected")

    def test_project_audit_settings(self) -> None:
        self.project.acting_user = self.user
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.enforced_2fa = True
        self.project.translation_review = True
        self.project.source_review = True
        self.project.commit_policy = CommitPolicyChoices.WITHOUT_NEEDS_EDITING
        self.project.enable_hooks = False
        self.project.use_shared_tm = False
        self.project.contribute_shared_tm = False
        self.project.check_flags = "strict-same"
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
            review_change.get_details_display(),
            'Enable reviews changed from "disabled" to "enabled".',
        )
        self.assertEqual(
            policy_change.get_details_display(),
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
        self.user.clear_cache()

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
            change.get_details_display(),
            'Project moved from "Current workspace" to "Target workspace".',
        )

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
        self.user.clear_cache()

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
        self.user.clear_cache()

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

    def test_component_inherited_required_license_validates(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.project.license = "MIT"
        self.project.save(update_fields=["license"])
        self.component.license = ""
        self.component.inherit_license = True
        self.component.save(update_fields=["license", "inherit_license"])

        field = Component._meta.get_field("license")  # noqa: SLF001
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
        self.component.acting_user = self.user
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
            restricted_change.get_details_display(),
            'Restricted component changed from "disabled" to "enabled".',
        )
        self.assertEqual(
            new_lang_change.get_details_display(),
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
