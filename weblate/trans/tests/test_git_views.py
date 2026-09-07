# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for Git manipulation views."""

from unittest.mock import Mock, patch

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test.utils import override_settings
from django.urls import reverse

from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, Permission, Role, TeamMembership
from weblate.lang.models import Language
from weblate.trans.models import Component, PendingUnitChange, Project, Translation
from weblate.trans.repository import (
    RepositoryOperationConflictError,
    acquire_repository_operation,
    get_repository_operation_key,
    get_repository_operation_published_key,
    get_repository_operation_scope_key,
    get_repository_operation_update_key,
    keep_repository_operation_reservation,
    queue_repository_operation,
    refresh_repository_operation,
    release_repository_operation,
    store_repository_operation_tracking,
)
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_optional_path
from weblate.utils.celery import (
    delete_task_metadata,
    get_task_metadata,
    get_task_metadata_key,
)


class GitNoChangeProjectTest(ViewTestCase):
    """Testing of git manipulations with no change in repo."""

    TEST_TYPE = "project"
    EXPECTED_COMMITS = 3
    EXPECTED_CHANGE_KEEP = False

    def setUp(self) -> None:
        super().setUp()
        # We need extra privileges for overwriting
        self.user.is_superuser = True
        self.user.save()

    def get_test_url(self, prefix):
        obj = getattr(self, self.TEST_TYPE)
        return reverse(prefix, kwargs={"path": obj.get_url_path()})

    def get_expected_redirect(self):
        return f"{getattr(self, f'{self.TEST_TYPE}_url')}#repository"

    def get_expected_redirect_progress(self):
        obj = getattr(self, self.TEST_TYPE)
        return f"{reverse('show_progress', kwargs={'path': obj.get_url_path()})}?info=1"

    def assert_progress_redirect(self, response) -> None:
        self.assertRedirects(
            response,
            self.get_expected_redirect_progress(),
            # Eager execution can finish before the progress page is retrieved.
            fetch_redirect_response=False,
        )

    def test_commit(self) -> None:
        has_changes = self.TEST_TYPE != "translation" or self.translation.needs_commit()
        response = self.client.post(self.get_test_url("commit"))
        if has_changes:
            self.assert_progress_redirect(response)
        else:
            self.assertRedirects(response, self.get_expected_redirect())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_commit_queues_background_task(self) -> None:
        with patch(
            "weblate.trans.tasks.perform_repository_operation.apply_async"
        ) as queue_operation:
            response = self.client.post(self.get_test_url("commit"))

        if self.TEST_TYPE == "translation" and not self.translation.needs_commit():
            self.assertRedirects(response, self.get_expected_redirect())
            queue_operation.assert_not_called()
            self.assertEqual(list(get_messages(response.wsgi_request)), [])
        else:
            self.assert_progress_redirect(response)
            queue_operation.assert_called_once()
            self.assertEqual(
                queue_operation.call_args.kwargs["kwargs"]["operation"], "commit"
            )

    def test_update(self) -> None:
        response = self.client.post(self.get_test_url("update"))
        self.assertRedirects(
            response,
            self.get_expected_redirect_progress(),
            # Do not attempt to retrieve the redirected URL, the answer
            # to the `show_progress` view can differ depending on whether
            # there is actually (still) some on-going background processing for
            # the current component, or not.
            fetch_redirect_response=False,
        )

    def test_conflict_does_not_redirect_to_inaccessible_task(self) -> None:
        with (
            patch(
                "weblate.trans.views.git.queue_repository_operation",
                side_effect=RepositoryOperationConflictError("task-id"),
            ),
            patch(
                "weblate.trans.views.git.can_access_repository_operation_task",
                return_value=False,
            ),
        ):
            response = self.client.post(self.get_test_url("update"))

        self.assertRedirects(response, self.get_expected_redirect())

    def test_push(self) -> None:
        response = self.client.post(self.get_test_url("push"))
        self.assert_progress_redirect(response)

    def test_get_push_redirects_to_repository_status(self) -> None:
        response = self.client.get(self.get_test_url("push"))
        self.assertRedirects(
            response, self.get_expected_redirect(), fetch_redirect_response=False
        )
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            messages[0].message,
            "Use the button on the repository status page to run this action.",
        )

    def test_reset(self) -> None:
        response = self.client.post(self.get_test_url("reset"))
        self.assertRedirects(
            response,
            self.get_expected_redirect_progress(),
            # Do not attempt to retrieve the redirected URL, the answer
            # to the `show_progress` view can differ depending on whether
            # there is actually (still) some on-going background processing for
            # the current component, or not.
            fetch_redirect_response=False,
        )
        self.assertEqual(self.component.count_repo_outgoing, 0)
        self.assertEqual(PendingUnitChange.objects.count(), 0)
        self.assertEqual(self.get_unit().target, "")

    def test_reset_keep(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.get_test_url("reset"), {"keep_changes": "1"}
            )
        self.assertRedirects(
            response,
            self.get_expected_redirect_progress(),
            # Do not attempt to retrieve the redirected URL, the answer
            # to the `show_progress` view can differ depending on whether
            # there is actually (still) some on-going background processing for
            # the current component, or not.
            fetch_redirect_response=False,
        )
        # One change for each translation and translator
        self.assertEqual(self.component.count_repo_outgoing, self.EXPECTED_COMMITS)
        self.assertEqual(PendingUnitChange.objects.count(), 0)
        self.assertEqual(
            self.get_unit().target,
            "Nazdar světe!\n" if self.EXPECTED_CHANGE_KEEP else "",
        )

    def test_cleanup(self) -> None:
        response = self.client.post(self.get_test_url("cleanup"))
        self.assert_progress_redirect(response)

    def test_file_sync(self) -> None:
        response = self.client.post(self.get_test_url("file_sync"))
        self.assert_progress_redirect(response)

    def test_file_scan(self) -> None:
        response = self.client.post(self.get_test_url("file_scan"))
        self.assertRedirects(
            response,
            self.get_expected_redirect_progress(),
            # Do not attempt to retrieve the redirected URL, the answer
            # to the `show_progress` view can differ depending on whether
            # there is actually (still) some on-going background processing for
            # the current component, or not.
            fetch_redirect_response=False,
        )

    def test_status_does_not_check_project_needs_commit(self) -> None:
        with patch.object(
            Project,
            "needs_commit",
            side_effect=AssertionError("Project.needs_commit should not be evaluated"),
        ):
            response = self.client.get(self.get_test_url("git_status"))
        self.assertContains(response, "Repository status")


class RepositoryPermissionScopeTest(ViewTestCase):
    def grant_permission(
        self,
        permission: str,
        *,
        component: Component | None = None,
        project: Project | None = None,
        language: Language | None = None,
    ) -> None:
        group = Group.objects.create(
            name=f"Repository scope {permission} {Group.objects.count()}",
            language_selection=SELECTION_ALL,
        )
        if component is not None:
            group.components.add(component)
        if project is not None:
            group.projects.add(project)
        role = Role.objects.create(
            name=f"Repository scope {permission} {Role.objects.count()}"
        )
        role.permissions.add(Permission.objects.get(codename=permission))
        group.roles.add(role)
        self.user.groups.add(group)
        if language is not None:
            TeamMembership.objects.get(user=self.user, group=group).limit_languages.add(
                language
            )
        self.user.clear_permissions_cache()

    def test_language_limited_reset_and_cleanup_are_denied(self) -> None:
        self.user.groups.clear()
        translation = self.get_translation("cs")
        self.grant_permission(
            "vcs.reset",
            project=self.project,
            language=Language.objects.get(code="cs"),
        )

        self.assertFalse(self.user.has_perm("vcs.reset", translation))
        self.assertFalse(self.user.has_perm("meta:vcs.status", translation))
        for view_name in (
            "reset",
            "cleanup",
            "file_sync",
            "file_scan",
            "remove_duplicate_units",
            "cleanup_unused",
            "remove_obsolete_units",
        ):
            with self.subTest(view_name=view_name):
                response = self.client.post(
                    reverse(view_name, kwargs={"path": translation.get_url_path()})
                )
                self.assertEqual(response.status_code, 403)

    def test_linked_child_reset_requires_owner_permission(self) -> None:
        self.user.groups.clear()
        other_project = self.create_project(name="Other", slug="other")
        linked = self.create_link_existing(
            name="Linked repository permission",
            slug="linked-repository-permission",
            project=other_project,
        )
        self.grant_permission("vcs.reset", component=linked)

        self.assertFalse(self.user.has_perm("vcs.reset", linked))
        with patch.object(Component, "do_reset", autospec=True) as reset:
            response = self.client.post(
                reverse("reset", kwargs={"path": linked.get_url_path()})
            )
        self.assertEqual(response.status_code, 403)
        reset.assert_not_called()

    def test_project_repository_status_lists_inaccessible_components(self) -> None:
        self.user.groups.clear()
        other_project = self.create_project(name="Other", slug="other")
        linked = self.create_link_existing(
            name="Blocked linked component",
            slug="blocked-linked-component",
            project=other_project,
        )
        self.grant_permission("vcs.reset", project=self.project)

        self.assertTrue(self.user.has_perm("meta:vcs.status", self.project))
        self.assertFalse(self.user.has_perm("vcs.reset", self.project))

        response = self.client.get(
            reverse("git_status", kwargs={"path": self.project.get_url_path()})
        )

        self.assertContains(response, "Some repositories are not accessible")
        self.assertContains(response, self.component.full_slug)
        self.assertNotContains(response, linked.full_slug)

        with patch.object(Component, "do_reset", autospec=True) as reset:
            response = self.client.post(
                reverse("reset", kwargs={"path": self.project.get_url_path()})
            )
        self.assertEqual(response.status_code, 403)
        reset.assert_not_called()

    def test_project_repository_operation_filters_inaccessible_components(self) -> None:
        self.user.groups.clear()
        independent = self.create_po(project=self.project, name="Independent")
        other_project = self.create_project(name="Other", slug="other")
        linked = self.create_link_existing(
            name="Blocked linked component",
            slug="blocked-linked-component",
            project=other_project,
        )
        self.grant_permission("vcs.reset", project=self.project)

        self.assertTrue(self.user.has_perm("vcs.reset", self.project))
        with patch.object(
            Component, "do_reset", autospec=True, return_value=True
        ) as reset:
            response = self.client.post(
                reverse("reset", kwargs={"path": self.project.get_url_path()})
            )

        self.assertRedirects(
            response,
            f"{reverse('show_progress', kwargs={'path': self.project.get_url_path()})}?info=1",
            fetch_redirect_response=False,
        )
        reset.assert_called_once()
        self.assertEqual(reset.call_args.args[0], independent)
        self.assertNotEqual(reset.call_args.args[0], self.component)
        self.assertNotEqual(reset.call_args.args[0], linked)

    def test_project_repository_status_lists_restrictions_by_operation(self) -> None:
        self.user.groups.clear()
        self.create_po(project=self.project, name="Independent")
        other_project = self.create_project(name="Other", slug="other")
        linked = self.create_link_existing(
            name="Blocked linked component",
            slug="blocked-linked-component",
            project=other_project,
        )
        self.grant_permission("vcs.reset", project=self.project)
        self.grant_permission("vcs.reset", component=linked)
        self.grant_permission("vcs.commit", project=self.project)
        self.grant_permission("vcs.push", project=self.project)
        self.grant_permission("vcs.update", project=self.project)
        PendingUnitChange.objects.create(unit=self.get_unit(), author=self.user)
        self.component.push_branch = "push"
        self.component.save(update_fields=["push_branch"])
        repository_class = self.component.repository_class

        with (
            patch.object(
                Component,
                "can_push",
                autospec=True,
                side_effect=lambda component: component == self.component,
            ),
            patch.object(
                Component,
                "count_repo_outgoing",
                new=property(lambda component: 7 if component == self.component else 0),
            ),
            patch.object(
                Component,
                "count_push_branch_outgoing",
                new=property(lambda component: 5 if component == self.component else 0),
            ),
            patch.object(
                Component,
                "count_repo_missing",
                new=property(lambda component: 9 if component == self.component else 0),
            ),
            patch.object(
                repository_class,
                "get_push_label",
                side_effect=lambda component: (
                    "Reset-only push label"
                    if component == self.component
                    else "Push-scoped label"
                ),
            ),
        ):
            response = self.client.get(
                reverse("git_status", kwargs={"path": self.project.get_url_path()})
            )

        operation_restrictions = dict(
            response.context["repository_operation_restrictions"]
        )
        self.assertEqual(set(operation_restrictions), {"Commit", "Push", "Update"})
        for restrictions in operation_restrictions.values():
            self.assertEqual(len(restrictions), 1)
            self.assertEqual(restrictions[0].project_components, (self.component,))
            self.assertEqual(restrictions[0].permission_blockers, (linked,))
        self.assertContains(response, "Some repositories are not accessible")
        self.assertContains(response, "Push")
        self.assertContains(response, self.component.full_slug)
        self.assertContains(response, linked.full_slug)
        self.assertFalse(response.context["can_push"])
        self.assertEqual(response.context["outgoing_commits"], 0)
        self.assertFalse(response.context["has_push_branch"])
        self.assertEqual(response.context["push_branch_outgoing_commits"], 0)
        self.assertEqual(response.context["push_label"], "Push-scoped label")
        self.assertEqual(response.context["pending_units"]["total"], 0)
        self.assertEqual(response.context["missing_commits"], 0)

    def test_project_repository_status_hides_inaccessible_blockers(self) -> None:
        self.user.groups.clear()
        self.create_po(project=self.project, name="Independent")
        other_project = self.create_project(name="Other", slug="other")
        linked = self.create_link_existing(
            name="Hidden linked component",
            slug="hidden-linked-component",
            project=other_project,
        )
        linked.restricted = True
        linked.save(update_fields=["restricted"])
        self.grant_permission("vcs.reset", project=self.project)

        response = self.client.get(
            reverse("git_status", kwargs={"path": self.project.get_url_path()})
        )

        self.assertContains(response, "Some repositories are not accessible")
        self.assertContains(response, self.component.full_slug)
        self.assertNotContains(response, linked.full_slug)


class RepositoryOperationQueueTest(ViewTestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_task_tracking_excludes_inaccessible_linked_components(self) -> None:
        self.user.groups.clear()
        other_project = self.create_project(name="Other", slug="other")
        linked = self.create_link_existing(
            name="Hidden linked component",
            slug="hidden-linked-component",
            project=other_project,
        )
        linked.restricted = True
        linked.save(update_fields=["restricted"])
        group = Group.objects.create(
            name="Visible repository scope", language_selection=SELECTION_ALL
        )
        group.projects.add(self.project)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertTrue(self.user.can_access_component(self.component))
        self.assertFalse(self.user.can_access_component(linked))

        with patch("weblate.trans.tasks.perform_repository_operation.apply_async"):
            queued = queue_repository_operation(self.component, "pull", self.user)

        self.addCleanup(
            release_repository_operation, [self.component.pk], queued.task_id
        )
        self.addCleanup(delete_task_metadata, queued.task_id)
        self.addCleanup(
            cache.delete_many,
            [
                get_repository_operation_update_key(self.component.pk),
                get_repository_operation_update_key(linked.pk),
            ],
        )
        metadata = get_task_metadata(queued.task_id)

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["component_ids"], [self.component.pk])
        self.assertEqual(
            cache.get(get_repository_operation_update_key(self.component.pk)),
            queued.task_id,
        )
        self.assertIsNone(cache.get(get_repository_operation_update_key(linked.pk)))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_progress_hides_aggregated_task_from_partial_viewer(self) -> None:
        hidden = self.create_po(project=self.project, name="Hidden")
        hidden.restricted = True
        hidden.save(update_fields=["restricted"])
        owner_group = Group.objects.create(
            name="Hidden component access", language_selection=SELECTION_ALL
        )
        owner_group.components.add(hidden)
        self.user.groups.add(owner_group)
        self.user.clear_permissions_cache()
        self.anotheruser.groups.add(Group.objects.get(name="Users"))
        self.anotheruser.clear_permissions_cache()
        self.assertTrue(self.user.can_access_component(hidden))
        self.assertTrue(self.anotheruser.can_access_component(self.component))
        self.assertFalse(self.anotheruser.can_access_component(hidden))

        task_id = "aggregated-task-id"
        component_ids = [self.component.pk, hidden.pk]
        store_repository_operation_tracking(
            task_id,
            component_ids,
            self.user.pk,
            authorization_component_ids=component_ids,
        )
        self.addCleanup(delete_task_metadata, task_id)
        self.addCleanup(
            cache.delete_many,
            [
                get_repository_operation_update_key(component_id)
                for component_id in component_ids
            ],
        )
        progress_url = reverse(
            "show_progress", kwargs={"path": self.component.get_url_path()}
        )
        pending_task = Mock(id=task_id)
        pending_task.ready.return_value = False

        with (
            patch(
                "weblate.trans.models.component.AsyncResult",
                return_value=pending_task,
            ),
            patch.object(Component, "get_progress", return_value=(10, ["Owner log"])),
        ):
            owner_response = self.client.get(progress_url)

        self.assertContains(owner_response, "Owner log")
        self.client.force_login(self.anotheruser)

        with (
            patch.object(
                Component,
                "get_progress",
                side_effect=AssertionError("Unauthorized task log was read"),
            ),
        ):
            response = self.client.get(progress_url)
            project_response = self.client.get(
                reverse("show_progress", kwargs={"path": self.project.get_url_path()})
            )

        self.assertEqual(response.status_code, 404)
        self.assertRedirects(
            project_response,
            self.project.get_absolute_url(),
            fetch_redirect_response=False,
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_progress_stores_completed_repository_message(self) -> None:
        task_id = "completed-task-id"
        component_ids = [self.component.pk]
        store_repository_operation_tracking(
            task_id,
            component_ids,
            self.user.pk,
            authorization_component_ids=component_ids,
        )
        self.addCleanup(delete_task_metadata, task_id)
        self.addCleanup(
            cache.delete, get_repository_operation_update_key(self.component.pk)
        )

        class CompletedTask:
            def __init__(self, result_task_id: str) -> None:
                self.id = result_task_id
                self.result = {
                    "result": False,
                    "completion_message": {
                        "level": "error",
                        "text": "Repository operation failed.",
                    },
                }

            def ready(self) -> bool:
                return True

        with patch("weblate.trans.models.component.AsyncResult", CompletedTask):
            response = self.client.get(
                reverse("show_progress", kwargs={"path": self.component.get_url_path()})
            )

        self.assertRedirects(
            response,
            f"{self.component.get_absolute_url()}#alerts",
            fetch_redirect_response=False,
        )
        stored_messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(stored_messages), 1)
        self.assertEqual(stored_messages[0].message, "Repository operation failed.")
        self.assertTrue(
            response.wsgi_request.session[f"task-completion-message-{task_id}"]
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_tracking_failure_releases_repository_reservation(self) -> None:
        with (
            patch("weblate.trans.repository.uuid", return_value="task-id"),
            patch(
                "weblate.trans.repository.store_repository_operation_tracking",
                side_effect=RuntimeError("cache failure"),
            ),
            patch(
                "weblate.trans.tasks.perform_repository_operation.apply_async"
            ) as apply_async,
            self.assertRaisesRegex(RuntimeError, "cache failure"),
        ):
            queue_repository_operation(self.component, "pull", self.user)

        self.assertIsNone(cache.get(get_repository_operation_key(self.component.pk)))
        self.assertIsNone(cache.get(get_repository_operation_scope_key("task-id")))
        apply_async.assert_not_called()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_operation_is_not_reused_before_publication(self) -> None:
        def fail_publication(**kwargs):
            with self.assertRaises(RepositoryOperationConflictError):
                queue_repository_operation(self.component, "pull", self.user)
            msg = "broker failure"
            raise RuntimeError(msg)

        with (
            patch("weblate.trans.repository.uuid", return_value="task-id"),
            patch(
                "weblate.trans.tasks.perform_repository_operation.apply_async",
                side_effect=fail_publication,
            ),
            self.assertRaisesRegex(RuntimeError, "broker failure"),
        ):
            queue_repository_operation(self.component, "pull", self.user)

        self.assertIsNone(cache.get(get_repository_operation_key(self.component.pk)))
        self.assertIsNone(cache.get(get_repository_operation_published_key("task-id")))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_eager_repository_failure_is_reported(self) -> None:
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])

        with patch.object(Component, "do_update", return_value=False):
            response = self.client.post(
                reverse("update", kwargs={"path": self.project.get_url_path()})
            )

        self.assertRedirects(response, f"{self.project_url}#repository")
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            messages[0].message,
            "Repository operation completed with errors.",
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_project_progress_deduplicates_repository_task(self) -> None:
        second = self.create_po(project=self.project, name="Second")
        task_id = "task-id"
        component_ids = [self.component.pk, second.pk]
        store_repository_operation_tracking(
            task_id,
            component_ids,
            self.user.pk,
            authorization_component_ids=component_ids,
        )
        self.addCleanup(delete_task_metadata, task_id)
        self.addCleanup(
            cache.delete_many,
            [
                get_repository_operation_update_key(component_id)
                for component_id in component_ids
            ],
        )

        pending_task = Mock(id=task_id)
        pending_task.ready.return_value = False
        with patch(
            "weblate.trans.models.component.AsyncResult", return_value=pending_task
        ):
            response = self.client.get(
                reverse("show_progress", kwargs={"path": self.project.get_url_path()})
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["components"]), 1)

    def test_repository_progress_takes_precedence_over_normal_task(self) -> None:
        repository_task_id = "repository-task-id"
        normal_task_id = "normal-task-id"
        repository_key = get_repository_operation_update_key(self.component.pk)
        cache.set(repository_key, repository_task_id, 3600)
        cache.set(self.component.update_key, normal_task_id, 3600)
        self.addCleanup(cache.delete_many, [repository_key, self.component.update_key])

        with patch("weblate.trans.models.component.AsyncResult") as async_result:
            async_result.return_value.ready.return_value = False
            self.assertEqual(self.component.background_task_id, repository_task_id)

    def test_file_cleanup_respects_repository_reservation(self) -> None:
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        acquire_repository_operation([self.component.pk], "pull", "task-id")
        self.addCleanup(release_repository_operation, [self.component.pk], "task-id")

        with patch.object(
            Translation, "do_remove_duplicate_units", autospec=True
        ) as remove_duplicates:
            response = self.client.post(
                reverse(
                    "remove_duplicate_units",
                    kwargs={"path": self.translation.get_url_path()},
                )
            )

        self.assertRedirects(response, f"{self.translation_url}#repository")
        remove_duplicates.assert_not_called()
        self.assertEqual(
            next(iter(get_messages(response.wsgi_request))).message,
            "Another repository operation is already in progress.",
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_reuses_identical_operation_and_rejects_conflict(self) -> None:
        with patch(
            "weblate.trans.tasks.perform_repository_operation.apply_async"
        ) as apply_async:
            first = queue_repository_operation(self.component, "pull", self.user)
            self.addCleanup(
                release_repository_operation, [self.component.pk], first.task_id
            )
            repeated = queue_repository_operation(self.component, "pull", self.user)

            self.assertEqual(repeated.task_id, first.task_id)
            self.assertTrue(repeated.reused)
            apply_async.assert_called_once()
            self.assertEqual(
                cache.get(get_repository_operation_key(self.component.pk)),
                {"operation": "pull", "task_id": first.task_id},
            )
            self.assertEqual(
                cache.get(get_repository_operation_scope_key(first.task_id)),
                [self.component.pk],
            )
            self.assertIs(
                cache.get(get_repository_operation_published_key(first.task_id)), True
            )

            with self.assertRaises(RepositoryOperationConflictError) as raised:
                queue_repository_operation(self.component, "push", self.user)

        self.assertEqual(raised.exception.task_id, first.task_id)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_worker_reacquires_expired_reservation(self) -> None:
        with patch("weblate.trans.tasks.perform_repository_operation.apply_async"):
            queued = queue_repository_operation(self.component, "pull", self.user)

        cache.delete(get_repository_operation_key(self.component.pk))
        cache.delete(get_repository_operation_scope_key(queued.task_id))
        acquire_repository_operation([self.component.pk], "pull", queued.task_id)
        self.addCleanup(
            release_repository_operation, [self.component.pk], queued.task_id
        )

        self.assertEqual(
            cache.get(get_repository_operation_key(self.component.pk)),
            {"operation": "pull", "task_id": queued.task_id},
        )
        self.assertEqual(
            cache.get(get_repository_operation_scope_key(queued.task_id)),
            [self.component.pk],
        )

    def test_reacquisition_conflict_releases_entire_owned_scope(self) -> None:
        second = self.create_po(project=self.project, name="Second")
        third = self.create_po(project=self.project, name="Third")
        component_ids = [self.component.pk, second.pk, third.pk]
        keys = [get_repository_operation_key(pk) for pk in component_ids]
        self.addCleanup(cache.delete_many, keys)
        reservation = {"operation": "pull", "task_id": "task-id"}
        cache.set(keys[0], reservation)
        cache.set(keys[1], {"operation": "push", "task_id": "other-task"})
        cache.set(keys[2], reservation)

        with self.assertRaises(RepositoryOperationConflictError):
            acquire_repository_operation(component_ids, "pull", "task-id")

        self.assertIsNone(cache.get(keys[0]))
        self.assertEqual(
            cache.get(keys[1]), {"operation": "push", "task_id": "other-task"}
        )
        self.assertIsNone(cache.get(keys[2]))

    def test_heartbeat_refreshes_task_tracking(self) -> None:
        task_id = "task-id"
        component_ids = [self.component.pk]
        acquire_repository_operation(component_ids, "pull", task_id)
        store_repository_operation_tracking(task_id, component_ids, self.user.pk)
        self.addCleanup(release_repository_operation, component_ids, task_id)

        with patch.object(cache, "touch", wraps=cache.touch) as touch:
            refresh_repository_operation(component_ids, task_id, component_ids)

        touched_keys = {call.args[0] for call in touch.call_args_list}
        self.assertIn(get_repository_operation_key(self.component.pk), touched_keys)
        self.assertIn(get_repository_operation_scope_key(task_id), touched_keys)
        self.assertIn(get_task_metadata_key(task_id), touched_keys)
        self.assertIn(
            get_repository_operation_update_key(self.component.pk), touched_keys
        )

    def test_reservation_heartbeat_refreshes_long_operations(self) -> None:
        class ImmediateThread:
            def __init__(self, *, target, **kwargs) -> None:
                self.target = target

            def start(self) -> None:
                self.target()

            def join(self, *, timeout) -> None:
                return None

        class ImmediateEvent:
            def __init__(self) -> None:
                self.wait_count = 0

            def wait(self, timeout) -> bool:
                self.wait_count += 1
                return self.wait_count > 1

            def set(self) -> None:
                return None

        with (
            patch("weblate.trans.repository.Thread", ImmediateThread),
            patch("weblate.trans.repository.Event", ImmediateEvent),
            patch("weblate.trans.repository.refresh_repository_operation") as refresh,
            keep_repository_operation_reservation(
                [self.component.pk], "task-id", [self.component.pk]
            ),
        ):
            pass

        self.assertEqual(refresh.call_count, 2)


class GitNoChangeComponentTest(GitNoChangeProjectTest):
    """Testing of component git manipulations."""

    TEST_TYPE = "component"


class GitNoChangeTranslationTest(GitNoChangeProjectTest):
    """Testing of translation git manipulations."""

    TEST_TYPE = "translation"

    def test_status_shows_remove_obsolete_units(self) -> None:
        cleanup_url = reverse(
            "remove_obsolete_units", kwargs={"path": self.translation.get_url_path()}
        )

        response = self.client.get(self.get_test_url("git_status"))

        self.assertContains(response, "File management")
        self.assertContains(response, cleanup_url)
        self.assertContains(response, "Remove obsolete")

    def test_remove_obsolete_units(self) -> None:
        translation_file = get_optional_path(self.translation.get_filename())
        translation_file.write_text(
            translation_file.read_text(encoding="utf-8")
            + '\n#~ msgid "Obsolete string"\n#~ msgstr "Zastaraly retezec"\n',
            encoding="utf-8",
        )
        self.translation.drop_store_cache()

        response = self.client.post(self.get_test_url("remove_obsolete_units"))

        self.assertRedirects(response, self.get_expected_redirect())
        self.assertNotIn("#~ msgid", translation_file.read_text(encoding="utf-8"))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_commit_clean_translation_does_not_queue_sibling_changes(self) -> None:
        sibling = self.component.translation_set.exclude(pk=self.translation.pk).first()
        self.assertIsNotNone(sibling)
        self.change_unit("Hallo Welt!\n", translation=sibling)
        self.assertFalse(self.translation.needs_commit())
        self.assertTrue(sibling.needs_commit())

        with patch.object(
            Component, "queue_commit_pending", autospec=True
        ) as queue_commit:
            response = self.client.post(self.get_test_url("commit"))

        self.assertRedirects(response, self.get_expected_redirect())
        queue_commit.assert_not_called()
        self.assertEqual(list(get_messages(response.wsgi_request)), [])


class GitChangeProjectTest(GitNoChangeProjectTest):
    """Testing of project git manipulations with not committed change."""

    EXPECTED_COMMITS = 4
    EXPECTED_CHANGE_KEEP = True

    def setUp(self) -> None:
        super().setUp()
        self.change_unit("Nazdar světe!\n")


class GitChangeComponentTest(GitChangeProjectTest):
    """Testing of component git manipulations with not committed change."""

    TEST_TYPE = "component"


class GitChangeTranslationTest(GitChangeProjectTest):
    """Testing of translation git manipulations with not committed change."""

    TEST_TYPE = "translation"


class GitCommittedChangeProjectTest(GitChangeProjectTest):
    """Testing of project git manipulations with committed change in repo."""

    def setUp(self) -> None:
        super().setUp()
        self.project.commit_pending("test", self.user)


class GitCommittedChangeComponentTest(GitCommittedChangeProjectTest):
    """Testing of component git manipulations with committed change."""

    TEST_TYPE = "component"


class GitCommittedChangeTranslationTest(GitCommittedChangeProjectTest):
    """Testing of translation git manipulations with committed change."""

    TEST_TYPE = "translation"


class GitBrokenProjectTest(GitNoChangeProjectTest):
    """Testing of project git manipulations with disappeared remote."""

    def setUp(self) -> None:
        super().setUp()
        repo = self.component.repository
        with repo.lock:
            repo.execute(
                ["branch", "--delete", "--remotes", "origin/main"],
                remote_op="none",
            )


class GitBrokenComponentTest(GitBrokenProjectTest):
    """Testing of component git manipulations with disappeared remote."""

    TEST_TYPE = "component"


class GitBrokenTranslationTest(GitBrokenProjectTest):
    """Testing of translation git manipulations with disappeared remote."""

    TEST_TYPE = "translation"
