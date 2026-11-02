# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Periodic cleanup of scoped notification subscriptions."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock, patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils.timezone import now

from weblate.accounts.data import NotificationFrequency, NotificationScope
from weblate.accounts.models import Subscription
from weblate.accounts.tasks import (
    cleanup_inaccessible_subscriptions,
    schedule_subscription_cleanup,
    setup_periodic_tasks,
)
from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, Role, TeamMembership, User, UserBlock
from weblate.lang.models import Language
from weblate.trans.models import ComponentList, Project
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.trans.tests.utils import get_test_actor
from weblate.utils.change_origin import acting_user_context


class SubscriptionCleanupTest(FixtureComponentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(acting_user_context(get_test_actor(self)))
        self.user.subscription_set.all().delete()
        self.project_subscription = self.subscribe(NotificationScope.SCOPE_PROJECT)
        self.component_subscription = self.subscribe(NotificationScope.SCOPE_COMPONENT)
        self.unscoped_subscription = self.subscribe(NotificationScope.SCOPE_ALL)

    def subscribe(self, scope: NotificationScope) -> Subscription:
        return self.user.subscription_set.create(
            scope=scope,
            project=self.project if scope == NotificationScope.SCOPE_PROJECT else None,
            component=self.component
            if scope == NotificationScope.SCOPE_COMPONENT
            else None,
            notification="RepositoryNotification",
            frequency=NotificationFrequency.FREQ_INSTANT,
        )

    def clean(self) -> None:
        cleanup_inaccessible_subscriptions([self.user.pk])
        self.assertTrue(
            Subscription.objects.filter(pk=self.unscoped_subscription.pk).exists()
        )

    def assert_scoped(self, *, project: bool, component: bool) -> None:
        self.assertEqual(
            Subscription.objects.filter(pk=self.project_subscription.pk).exists(),
            project,
        )
        self.assertEqual(
            Subscription.objects.filter(pk=self.component_subscription.pk).exists(),
            component,
        )

    def make_private(self) -> None:
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save(update_fields=["access_control"])

    def test_visibility_change_and_idempotency(self) -> None:
        self.clean()
        self.assert_scoped(project=True, component=True)
        self.make_private()
        self.clean()
        self.assert_scoped(project=False, component=False)
        self.clean()

    def test_membership_removal_waits_for_cleanup(self) -> None:
        self.make_private()
        self.project.add_user(self.user, "Translate")
        with (
            patch(
                "weblate.accounts.tasks.cleanup_inaccessible_subscriptions.delay"
            ) as cleanup,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.user.groups.remove(self.project.defined_groups.get(name="Translate"))
        cleanup.assert_not_called()
        self.assert_scoped(project=True, component=True)
        self.clean()
        self.assert_scoped(project=False, component=False)

    def test_component_move(self) -> None:
        target = Project.objects.create(
            name="Private destination",
            slug="private-destination",
            access_control=Project.ACCESS_PRIVATE,
        )
        self.component.project = target
        self.component.save(update_fields=["project"])
        self.clean()
        self.assert_scoped(project=True, component=False)

    def test_component_move_retains_alternative_access(self) -> None:
        target = Project.objects.create(
            name="Private destination",
            slug="private-destination",
            access_control=Project.ACCESS_PRIVATE,
        )
        target.add_user(self.user, "Translate")
        self.component.project = target
        self.component.save(update_fields=["project"])
        self.clean()
        self.assert_scoped(project=True, component=True)

    def test_component_restriction(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.clean()
        self.assert_scoped(project=True, component=False)

    def test_project_manager_retains_restricted_component(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.project.add_user(self.user, "Administration")
        self.project.enforced_2fa = True
        self.project.save(update_fields=["enforced_2fa"])
        self.clean()
        self.assert_scoped(project=True, component=True)

    def test_site_manager_retains_restricted_component(self) -> None:
        self.make_private()
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        group = Group.objects.create(
            name="Site managers",
            project_selection=SELECTION_ALL,
        )
        group.roles.add(Role.objects.get(name="Administration"))
        self.user.groups.add(group)
        self.clean()
        self.assert_scoped(project=True, component=True)

    def test_temporary_block_preserves_subscription_and_authorization(self) -> None:
        self.make_private()
        self.project.add_user(self.user, "Translate")
        UserBlock.objects.create(
            user=self.user, project=self.project, expiry=now() + timedelta(days=1)
        )
        self.user.clear_permissions_cache()
        self.assertFalse(self.user.can_access_project(self.project))
        self.clean()
        self.assert_scoped(project=True, component=True)
        self.assertFalse(self.user.can_access_project(self.project))
        UserBlock.objects.filter(user=self.user, project=self.project).delete()
        self.user.clear_permissions_cache()
        self.assertTrue(self.user.can_access_component(self.component))

    def test_block_does_not_preserve_revoked_entitlement(self) -> None:
        self.make_private()
        UserBlock.objects.create(user=self.user, project=self.project, expiry=None)
        self.clean()
        self.assert_scoped(project=False, component=False)

    def test_team_twofactor_requirement_preserves_subscription(self) -> None:
        self.make_private()
        self.project.add_user(self.user, "Translate")
        group = self.project.defined_groups.get(name="Translate")
        group.enforced_2fa = True
        group.save(update_fields=["enforced_2fa"])
        self.user.clear_permissions_cache()
        self.assertFalse(self.user.can_access_project(self.project))
        self.clean()
        self.assert_scoped(project=True, component=True)
        self.assertFalse(self.user.can_access_project(self.project))
        self.user.groups.remove(group)
        self.clean()
        self.assert_scoped(project=False, component=False)

    def test_team_scope_change(self) -> None:
        self.make_private()
        self.project.add_user(self.user, "Translate")
        group = self.project.defined_groups.get(name="Translate")
        group.projects.clear()
        self.clean()
        self.assert_scoped(project=False, component=False)

    def test_component_list_change(self) -> None:
        self.make_private()
        component_list = ComponentList.objects.create(name="Cleanup", slug="cleanup")
        component_list.components.add(self.component)
        group = Group.objects.create(name="List access")
        group.roles.add(Role.objects.get(name="Translate"))
        group.componentlists.add(component_list)
        self.user.groups.add(group)
        self.clean()
        self.assert_scoped(project=True, component=True)
        component_list.components.clear()
        self.clean()
        self.assert_scoped(project=False, component=False)

    def test_role_removal_revokes_restricted_component_management(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.project.add_user(self.user, "Administration")
        self.clean()
        self.assert_scoped(project=True, component=True)
        self.project.defined_groups.get(name="Administration").roles.clear()
        self.clean()
        self.assert_scoped(project=True, component=False)

    def test_membership_languages_revoke_restricted_component_management(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.project.add_user(self.user, "Administration")
        membership = TeamMembership.objects.get(
            user=self.user, group=self.project.defined_groups.get(name="Administration")
        )
        membership.limit_languages.add(Language.objects.get(code="cs"))
        self.clean()
        self.assert_scoped(project=True, component=False)

    def test_query_count_independent_of_subscription_count(self) -> None:
        with CaptureQueriesContext(connection) as first:
            self.clean()
        Subscription.objects.bulk_create(
            [
                Subscription(
                    user=self.user,
                    scope=NotificationScope.SCOPE_COMPONENT,
                    component=self.component,
                    notification=notification,
                    frequency=NotificationFrequency.FREQ_INSTANT,
                )
                for notification in ("LockNotification", "MergeFailureNotification")
            ]
        )
        with self.assertNumQueries(len(first)):
            self.clean()

    def test_hourly_buckets_and_batches(self) -> None:
        subscribers = [
            User(pk=240000 + index, username=f"cleanup-{index}")
            for index in [*range(24), *(24 * batch for batch in range(1, 201))]
        ]
        User.objects.bulk_create(subscribers)
        Subscription.objects.bulk_create(
            [
                Subscription(
                    user=user,
                    scope=scope,
                    project=self.project
                    if scope == NotificationScope.SCOPE_PROJECT
                    else None,
                    component=self.component
                    if scope == NotificationScope.SCOPE_COMPONENT
                    else None,
                    notification="RepositoryNotification",
                    frequency=NotificationFrequency.FREQ_INSTANT,
                )
                for user in subscribers
                for scope in (
                    NotificationScope.SCOPE_PROJECT,
                    NotificationScope.SCOPE_COMPONENT,
                )
            ]
        )
        # Exclude fixture users; bucket zero exercises the 200-user boundary.
        Subscription.objects.exclude(user_id__gte=240000).delete()
        seen = []
        for hour in range(24):
            with (
                patch(
                    "weblate.accounts.tasks.now", return_value=now().replace(hour=hour)
                ),
                patch(
                    "weblate.accounts.tasks.cleanup_inaccessible_subscriptions.delay"
                ) as cleanup,
            ):
                schedule_subscription_cleanup(using="default")
            batches = [call.args[0] for call in cleanup.call_args_list]
            self.assertEqual(
                [len(batch) for batch in batches], [200, 1] if hour == 0 else [1]
            )
            self.assertTrue(
                all(call.args[1] == "default" for call in cleanup.call_args_list)
            )
            ids = [pk for batch in batches for pk in batch]
            self.assertTrue(all(pk % 24 == hour for pk in ids))
            seen.extend(ids)
        self.assertCountEqual(seen, [user.pk for user in subscribers])

    def test_no_scoped_subscriptions(self) -> None:
        Subscription.objects.exclude(scope=NotificationScope.SCOPE_ALL).delete()
        with patch(
            "weblate.accounts.tasks.cleanup_inaccessible_subscriptions.delay"
        ) as cleanup:
            schedule_subscription_cleanup()
        cleanup.assert_not_called()

    def test_periodic_registration(self) -> None:
        with patch(
            "weblate.accounts.tasks.schedule_subscription_cleanup.s"
        ) as signature:
            sender = Mock()
            setup_periodic_tasks(sender)
        sender.add_periodic_task.assert_any_call(
            3600, signature.return_value, name="subscription-cleanup"
        )
