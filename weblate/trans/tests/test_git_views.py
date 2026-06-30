# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for Git manipulation views."""

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test.utils import override_settings
from django.urls import reverse

from weblate.trans.models import Component, PendingUnitChange
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

    def test_status(self) -> None:
        response = self.client.get(self.get_test_url("git_status"))
        self.assertContains(response, "Repository status")


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
