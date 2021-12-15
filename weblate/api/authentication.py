#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


from django.contrib.auth.base_user import AbstractBaseUser
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication

from weblate.trans.models import Project, ProjectToken, Unit
from weblate.trans.models.component import Component
from weblate.trans.models.translation import Translation
from weblate.utils.stats import ProjectLanguage


class BearerAuthentication(TokenAuthentication):
    """RFC 6750 compatible Bearer authentication."""

    keyword = "Bearer"


class ProjectUser(AbstractBaseUser):
    """User class for project users."""

    USERNAME_FIELD = "username"

    def __init__(self, *args, **kwargs) -> None:
        self.project = kwargs.pop("project")
        self.groups = []
        self.is_superuser = False
        self.username = self.project.slug
        self.allowed_project_ids = {self.project.id}
        self.allowed_projects = Project.objects.filter(pk=self.project.id)
        self.component_permissions = {}
        super().__init__(*args, **kwargs)

    def has_perm(self, perm: str, obj=None):
        if isinstance(obj, ProjectLanguage):
            obj = obj.project
        if isinstance(obj, Component):
            obj = obj.project
        if isinstance(obj, Translation):
            obj = obj.component.project
        if isinstance(obj, Unit):
            obj = obj.translation.component.project
        if isinstance(obj, Project):
            return obj.pk == self.project.pk
        return False


class ProjectTokenAuthentication(TokenAuthentication):
    """Authentication with project token."""

    def authenticate_credentials(self, key):
        try:
            project_token = ProjectToken.objects.get(
                token=key, expires__gte=timezone.now()
            )
            user = ProjectUser(project=project_token.project)
            return (user, key)
        except ProjectToken.DoesNotExist:
            return None
