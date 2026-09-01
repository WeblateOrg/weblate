# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for Git manipulation views."""

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test.utils import override_settings
from django.urls import reverse

from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, Permission, Role, TeamMembership
from weblate.lang.models import Language
from weblate.trans.models import Component, PendingUnitChange, Project
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_optional_path


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

    def test_commit(self) -> None:
        response = self.client.post(self.get_test_url("commit"))
        self.assertRedirects(response, self.get_expected_redirect())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_commit_queues_background_task(self) -> None:
        with patch.object(
            Component, "queue_commit_pending", autospec=True
        ) as queue_commit:
            response = self.client.post(self.get_test_url("commit"))

        self.assertRedirects(response, self.get_expected_redirect())
        if self.TEST_TYPE == "translation" and not self.translation.needs_commit():
            queue_commit.assert_not_called()
            self.assertEqual(list(get_messages(response.wsgi_request)), [])
        else:
            self.assertGreaterEqual(queue_commit.call_count, 1)
            for call in queue_commit.call_args_list:
                self.assertEqual(call.args[1], "commit")
                self.assertEqual(call.kwargs, {"user_id": self.user.id})

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

    def test_push(self) -> None:
        response = self.client.post(self.get_test_url("push"))
        self.assertRedirects(response, self.get_expected_redirect())

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
        self.assertRedirects(response, self.get_expected_redirect())

    def test_file_sync(self) -> None:
        response = self.client.post(self.get_test_url("file_sync"))
        self.assertRedirects(response, self.get_expected_redirect())

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
