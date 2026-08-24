# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


"""Tests for version control parameters."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import reverse

from weblate.lang.models import get_default_lang
from weblate.trans.models import Component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.views import get_form_data
from weblate.vcs.models import VCS_REGISTRY
from weblate.vcs.params import (
    VCS_PARAMS,
    CreateMergeRequest,
    GitForcePush,
    MergeRequestAutomerge,
    MergeRequestMergeMethod,
    get_default_params_for_vcs,
    get_params_for_vcs,
    get_vcs_param_for_name,
    strip_unused_vcs_params,
)


class VCSParamsRegistryTest(SimpleTestCase):
    def test_git_scope(self) -> None:
        names = {param.name for param in get_params_for_vcs("git")}
        self.assertEqual(names, {"git_force_push"})

    def test_github_scope(self) -> None:
        names = {param.name for param in get_params_for_vcs("github")}
        self.assertEqual(
            names,
            {
                "create_merge_request",
                "merge_request_automerge",
                "merge_request_merge_method",
            },
        )

    def test_mercurial_has_no_params(self) -> None:
        self.assertEqual(get_params_for_vcs("mercurial"), [])

    def test_defaults(self) -> None:
        self.assertEqual(get_default_params_for_vcs("git"), {"git_force_push": False})
        self.assertEqual(
            get_default_params_for_vcs("github"),
            {
                "create_merge_request": True,
                "merge_request_automerge": False,
                "merge_request_merge_method": "merge",
            },
        )

    def test_strip_unused(self) -> None:
        params = {"git_force_push": True, "merge_request_automerge": True}
        self.assertEqual(
            strip_unused_vcs_params("git", dict(params)),  # type: ignore[arg-type]
            {"git_force_push": True},
        )
        self.assertEqual(
            strip_unused_vcs_params("github", dict(params)),  # type: ignore[arg-type]
            {"merge_request_automerge": True},
        )

    def test_get_param_for_name(self) -> None:
        self.assertEqual(
            get_vcs_param_for_name("git_force_push").name, "git_force_push"
        )
        with self.assertRaises(ValueError):
            get_vcs_param_for_name("does_not_exist")

    def test_unique_names(self) -> None:
        names = [param.name for param in VCS_PARAMS]
        self.assertEqual(len(names), len(set(names)))

    def test_scope_follows_vcs_backends_setting(self) -> None:
        """The cached backend list has to be invalidated by setting overrides."""
        original = set(CreateMergeRequest.get_scopes())
        self.assertIn("github", original)
        with override_settings(
            VCS_BACKENDS=(
                "weblate.vcs.git.GitRepository",
                "weblate.vcs.git.GiteaRepository",
            )
        ):
            self.assertEqual(set(CreateMergeRequest.get_scopes()), {"gitea"})
        self.assertEqual(set(CreateMergeRequest.get_scopes()), original)

    def test_choice_value_outside_choices_falls_back(self) -> None:
        # A non-required choice field cleans a missing value to an empty
        # string, which must never reach the hosting API.
        self.assertEqual(
            MergeRequestMergeMethod.get_value({"merge_request_merge_method": ""}),
            "merge",
        )
        self.assertEqual(
            MergeRequestMergeMethod.get_value({"merge_request_merge_method": "bogus"}),
            "merge",
        )
        self.assertEqual(
            MergeRequestMergeMethod.get_value({"merge_request_merge_method": "squash"}),
            "squash",
        )

    def test_boolean_values_are_cleaned_by_field(self) -> None:
        self.assertIs(GitForcePush.get_value({"git_force_push": "false"}), False)
        self.assertIs(GitForcePush.get_value({"git_force_push": "true"}), True)
        self.assertIs(
            MergeRequestAutomerge.get_value({"merge_request_automerge": "false"}),
            False,
        )


class ComponentVCSParamsTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

    def test_default_is_empty(self) -> None:
        self.assertEqual(self.component.vcs_params, {})

    def test_unknown_param_rejected(self) -> None:
        self.component.vcs_params = {"does_not_exist": True}
        with self.assertRaises(ValidationError):
            self.component.full_clean(exclude=["repo"])

    def test_param_not_applicable_to_vcs(self) -> None:
        self.component.vcs_params = {"merge_request_automerge": True}
        with self.assertRaises(ValidationError) as context:
            self.component.clean()
        self.assertIn("vcs_params", context.exception.message_dict)

    def test_direct_push_needs_credentials(self) -> None:
        self.component.vcs = "github"
        self.component.repo = "https://github.com/WeblateOrg/test.git"
        self.component.push = ""
        self.component.vcs_params = {"create_merge_request": False}
        with self.assertRaises(ValidationError) as context:
            self.component.clean_vcs_params()
        self.assertIn("vcs_params", context.exception.message_dict)

    def test_direct_push_accepts_ssh_repository(self) -> None:
        self.component.vcs = "github"
        self.component.repo = "git@github.com:WeblateOrg/test.git"
        self.component.push = ""
        self.component.vcs_params = {"create_merge_request": False}
        self.component.clean_vcs_params()

    def test_direct_push_accepts_push_url_with_credentials(self) -> None:
        self.component.vcs = "github"
        self.component.repo = "https://github.com/WeblateOrg/test.git"
        self.component.push = "https://user:token@github.com/WeblateOrg/test.git"
        self.component.vcs_params = {"create_merge_request": False}
        self.component.clean_vcs_params()

    @override_settings(
        GITHUB_CREDENTIALS={"api.github.com": {"username": "test", "token": "token"}}
    )
    def test_direct_push_accepts_translated_branch(self) -> None:
        VCS_REGISTRY.clear_cache()
        self.addCleanup(VCS_REGISTRY.clear_cache)
        self.component.vcs = "github"
        self.component.repo = "https://github.com/WeblateOrg/test.git"
        self.component.push = "https://user:token@github.com/WeblateOrg/test.git"
        self.component.branch = "main"
        self.component.push_branch = ""
        self.component.vcs_params = {"create_merge_request": False}
        self.component.clean_push_branch_settings()

        self.component.push_branch = self.component.branch
        self.component.clean_push_branch_settings()

    def test_merge_requests_on_needs_no_push_url(self) -> None:
        self.component.vcs = "github"
        self.component.repo = "https://github.com/WeblateOrg/test.git"
        self.component.push = ""
        self.component.vcs_params = {"create_merge_request": True}
        self.component.clean_vcs_params()

    def test_settings_form_round_trip(self) -> None:
        url = reverse("settings", kwargs={"path": self.component.get_url_path()})
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data["vcs_params_git_force_push"] = "on"
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Settings saved")
        self.component.refresh_from_db()
        self.assertIs(self.component.vcs_params["git_force_push"], True)

    def test_settings_form_strips_inapplicable(self) -> None:
        url = reverse("settings", kwargs={"path": self.component.get_url_path()})
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        # Belongs to GitHub backends, the component uses plain Git
        data["vcs_params_merge_request_automerge"] = "on"
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Settings saved")
        self.component.refresh_from_db()
        self.assertNotIn("merge_request_automerge", self.component.vcs_params)

    def test_create_component_with_params(self) -> None:
        params = {
            "name": "New Component With VCS Params",
            "slug": "new-component-with-vcs-params",
            "project": self.project.pk,
            "vcs": "git",
            "repo": self.component.get_repo_link_url(),
            "file_format": "po",
            "filemask": "po/*.po",
            "new_base": "po/project.pot",
            "new_lang": "add",
            "language_regex": "^[^.]+$",
            "source_language": get_default_lang(),
            "vcs_params_git_force_push": "on",
        }
        with override_settings(CREATE_GLOSSARIES=False):
            response = self.client.post(reverse("create-component-vcs"), params)
        self.assertEqual(response.status_code, 302)
        component = Component.objects.get(slug="new-component-with-vcs-params")
        self.assertIs(component.vcs_params["git_force_push"], True)
