# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory, TestCase
from social_core.backends.keycloak import KeycloakOAuth2
from social_core.exceptions import AuthConfigurationError
from social_core.pipeline.user import sync_groups
from social_django.models import DjangoStorage

from weblate.accounts.models import AuditLog
from weblate.accounts.strategy import WeblateStrategy
from weblate.auth.models import Group, TeamMembership, User
from weblate.lang.models import Language


class ExternalGroupSyncTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("group-sync", "group-sync@example.com")
        request = RequestFactory().get("/")
        request.user = self.user
        SessionMiddleware(lambda _request: HttpResponse()).process_request(request)
        self.strategy = WeblateStrategy(DjangoStorage, request)
        self.backend = KeycloakOAuth2(self.strategy)
        self.first = Group.objects.create(name="External first")
        self.second = Group.objects.create(name="External second")
        self.unrelated = Group.objects.create(name="Unrelated")
        self.mapping = {"first": [self.first.pk], "second": [self.second.pk]}

    def synchronize(self, groups: list[str] | None, **kwargs: object) -> None:
        with self.settings(SOCIAL_AUTH_KEYCLOAK_GROUPS_MAP=self.mapping):
            self.strategy.sync_user_groups(
                self.user, groups, backend=self.backend, response={}, **kwargs
            )

    def test_sync_is_audited_and_preserves_unrelated_memberships(self) -> None:
        self.user.groups.add(self.second, self.unrelated)
        for _ in range(2):
            self.synchronize(["first", "unknown"], weblate_action="activation")
        self.assertTrue(self.user.groups.filter(pk=self.first.pk).exists())
        self.assertFalse(self.user.groups.filter(pk=self.second.pk).exists())
        self.assertTrue(self.user.groups.filter(pk=self.unrelated.pk).exists())
        self.assertEqual(
            AuditLog.objects.filter(
                user=self.user,
                activity="sitewide-team-add",
                params__team=self.first.name,
            ).count(),
            1,
        )
        self.assertEqual(
            AuditLog.objects.filter(
                user=self.user,
                activity="sitewide-team-remove",
                params__team=self.second.name,
            ).count(),
            1,
        )
        self.synchronize([])
        self.assertFalse(self.user.groups.filter(pk=self.first.pk).exists())
        self.assertTrue(self.user.groups.filter(pk=self.unrelated.pk).exists())

    def test_existing_language_limits_survive_and_cache_is_cleared(self) -> None:
        self.user.groups.add(self.first)
        membership = TeamMembership.objects.get(user=self.user, group=self.first)
        language = Language.objects.get(code="cs")
        membership.limit_languages.add(language)
        self.user.__dict__["cached_memberships"] = []
        self.synchronize(["first", "second"])
        self.assertEqual(list(membership.limit_languages.all()), [language])
        self.assertNotIn("cached_memberships", self.user.__dict__)

    def test_missing_target_does_not_modify_memberships(self) -> None:
        self.user.groups.add(self.first)
        self.mapping["missing"] = [self.second.pk + 100000]
        with self.assertRaises(AuthConfigurationError):
            self.synchronize([])
        self.assertTrue(self.user.groups.filter(pk=self.first.pk).exists())

    def test_missing_extraction_and_competing_owner_fail(self) -> None:
        with self.assertRaises(AuthConfigurationError):
            self.synchronize(None)
        with (
            self.settings(
                AUTHENTICATION_BACKENDS=(
                    "social_core.backends.keycloak.KeycloakOAuth2",
                    "social_core.backends.gitlab.GitLabOAuth2",
                ),
                SOCIAL_AUTH_GITLAB_GROUPS_MAP={"other": [self.first.pk]},
            ),
            self.assertRaises(AuthConfigurationError),
        ):
            self.synchronize(["first"])
        self.assertFalse(self.user.groups.filter(pk=self.first.pk).exists())

    def test_reset_removal_and_interrupted_pipeline_do_not_sync(self) -> None:
        self.user.groups.add(self.first)
        for action in ("reset", "remove"):
            self.synchronize([], weblate_action=action)
        self.assertTrue(self.user.groups.filter(pk=self.first.pk).exists())
        for checkpoint in (
            "weblate.accounts.pipeline.second_factor",
            "weblate.legal.pipeline.tos_confirm",
        ):
            with (
                patch.object(self.strategy, "sync_user_groups") as hook,
                patch(checkpoint, return_value=HttpResponseRedirect("/check")),
            ):
                result = self.backend.run_pipeline(
                    [checkpoint, "social_core.pipeline.user.sync_groups"],
                    user=self.user,
                    response={},
                    groups=[],
                )
                assert isinstance(result, HttpResponseRedirect)
                self.assertEqual(result.url, "/check")
                hook.assert_not_called()

    def test_sync_step_delegates_after_checks(self) -> None:
        with self.settings(SOCIAL_AUTH_KEYCLOAK_GROUPS_MAP=self.mapping):
            sync_groups(
                self.strategy,
                self.backend,
                {},
                user=self.user,
                groups=["first"],
                weblate_action="activation",
            )
        self.assertTrue(self.user.groups.filter(pk=self.first.pk).exists())
