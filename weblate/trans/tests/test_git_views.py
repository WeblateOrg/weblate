# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for Git manipulation views."""

from django.urls import reverse

from weblate.trans.tests.test_views import ViewTestCase


class GitNoChangeProjectTest(ViewTestCase):
    """Testing of git manipulations with no change in repo."""

    TEST_TYPE = "project"

    def setUp(self) -> None:
        super().setUp()
        # We need extra privileges for overwriting
        self.user.is_superuser = True
        self.user.save()

    def get_test_url(self, prefix):
        obj = getattr(self, self.TEST_TYPE)
        return reverse(prefix, kwargs={"path": obj.get_url_path()})

    def get_expected_redirect(self):
        return getattr(self, f"{self.TEST_TYPE}_url") + "#repository"

    def get_expected_redirect_progress(self):
        obj = getattr(self, self.TEST_TYPE)
        return "{}?info=1".format(
            reverse("show_progress", kwargs={"path": obj.get_url_path()})
        )

    def test_commit(self) -> None:
        response = self.client.post(self.get_test_url("commit"))
        self.assertRedirects(response, self.get_expected_redirect())

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


class GitChangeProjectTest(GitNoChangeProjectTest):
    """Testing of project git manipulations with not committed change."""

    def setUp(self) -> None:
        super().setUp()
        self.change_unit("Ahoj světe!\n")


class GitChangeComponentTest(GitChangeProjectTest):
    """Testing of component git manipulations with not committed change."""

    TEST_TYPE = "component"


class GitChangeTranslationTest(GitChangeProjectTest):
    """Testing of translation git manipulations with not committed change."""

    TEST_TYPE = "translation"


class GitCommittedChangeProjectTest(GitNoChangeProjectTest):
    """Testing of project git manipulations with committed change in repo."""

    def setUp(self) -> None:
        super().setUp()
        self.change_unit("Ahoj světe!\n")
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
            repo.execute(["branch", "--delete", "--remotes", "origin/main"])


class GitBrokenComponentTest(GitBrokenProjectTest):
    """Testing of component git manipulations with disappeared remote."""

    TEST_TYPE = "component"


class GitBrokenTranslationTest(GitBrokenProjectTest):
    """Testing of translation git manipulations with disappeared remote."""

    TEST_TYPE = "translation"
