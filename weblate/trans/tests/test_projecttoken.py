from django.urls import reverse
import re

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.models import Project

class ProjectTokenTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.access_url = reverse("manage-access", kwargs=self.kw_project) + "#api"
        self.token_one = "This is token 1"

    def create_token(self):
        self.make_manager()
        response = self.client.post(
            reverse("create-project-token", kwargs=self.kw_project),
            {"name": self.token_one, "expires": "2999-12-99"},
            follow=True
        )
        html = response.content.decode("utf-8")
        result = re.search(r"Token has been created: (\w)", html)
        return result.group(1)

    def test_create_token(self):
        """Managers should be able to create new tokens"""
        token = self.create_token()
        self.assertTrue(token is not None)
