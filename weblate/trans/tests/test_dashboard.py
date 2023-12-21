# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test.utils import override_settings
from django.urls import reverse

from weblate.accounts.models import Profile
from weblate.lang.models import Language
from weblate.trans.models import Announcement, ComponentList, Project
from weblate.trans.tests.test_views import ViewTestCase


class DashboardTest(ViewTestCase):
    """Test for home/index view."""

    def setUp(self):
        super().setUp()
        self.user.profile.languages.add(Language.objects.get(code="cs"))

    def test_view_home_anonymous(self):
        self.client.logout()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Browse 1 project")

    def test_view_home(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "test/test")

    def test_view_projects(self):
        response = self.client.get(reverse("projects"))
        self.assertContains(response, "Test")

    def test_view_projects_slash(self):
        response = self.client.get("/projects")
        self.assertRedirects(response, reverse("projects"), status_code=301)

    def test_home_with_announcement(self):
        msg = Announcement(message="test_message")
        msg.save()

        response = self.client.get(reverse("home"))
        self.assertContains(response, "announcement")
        self.assertContains(response, "test_message")

    def test_home_without_announcement(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "announcement")

    def test_component_list(self):
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)

        response = self.client.get(reverse("home"))
        self.assertContains(response, "TestCL")
        self.assertContains(
            response, reverse("component-list", kwargs={"name": "testcl"})
        )
        self.assertEqual(len(response.context["componentlists"]), 1)

    def test_component_list_ghost(self):
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)

        self.user.profile.languages.add(Language.objects.get(code="es"))

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Spanish")

    def test_user_component_list(self):
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)

        self.user.profile.dashboard_view = Profile.DASHBOARD_COMPONENT_LIST
        self.user.profile.dashboard_component_list = clist
        self.user.profile.save()

        response = self.client.get(reverse("home"))
        self.assertContains(response, "TestCL")
        self.assertEqual(response.context["active_tab_slug"], "list-testcl")

    def test_subscriptions(self):
        # no subscribed projects at first
        response = self.client.get(reverse("home"))
        self.assertFalse(len(response.context["watched_projects"]))

        # subscribe a project
        self.user.profile.watched.add(self.project)
        response = self.client.get(reverse("home"))
        self.assertEqual(len(response.context["watched_projects"]), 1)

    def test_language_filters(self):
        # check language filters
        response = self.client.get(reverse("home"))
        self.assertFalse(response.context["usersubscriptions"])

        # add a language
        response = self.client.get(reverse("home"))
        self.assertFalse(response.context["usersubscriptions"])

        # add a subscription
        self.user.profile.watched.add(self.project)
        response = self.client.get(reverse("home"))
        self.assertEqual(len(response.context["usersubscriptions"]), 1)

    def test_user_nolang(self):
        self.user.profile.languages.clear()
        # This picks up random language
        self.client.get(reverse("home"), headers={"accept-language": "en"})
        self.client.get(reverse("home"))

        # Pick language from request
        response = self.client.get(reverse("home"), headers={"accept-language": "cs"})
        self.assertTrue(response.context["suggestions"])
        self.assertFalse(self.user.profile.languages.exists())

    def test_user_hide_completed(self):
        self.user.profile.hide_completed = True
        self.user.profile.save()

        response = self.client.get(reverse("home"))
        self.assertContains(response, "test/test")

    @override_settings(SINGLE_PROJECT=True)
    def test_single_project(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, self.component.get_absolute_url())

    @override_settings(SINGLE_PROJECT="test")
    def test_single_project_slug(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, self.project.get_absolute_url())

    @override_settings(SINGLE_PROJECT=True)
    def test_single_project_restricted(self):
        # Additional component to redirect to a project
        self.create_link_existing()
        # Make the project private
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.client.logout()
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, "/accounts/login/?next=/projects/test/")
