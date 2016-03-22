# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from rest_framework import viewsets

from weblate.api.serializers import ProjectSerializer, ComponentSerializer
from weblate.trans.models import Project, SubProject


class ProjectViewSet(viewsets.ReadOnlyModelViewSet):
    """Translation projects API.
    """
    queryset = Project.objects.none()
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.all_acl(self.request.user)


class ComponentViewSet(viewsets.ReadOnlyModelViewSet):
    """Translation components API.
    """
    queryset = SubProject.objects.none()
    serializer_class = ComponentSerializer

    def get_queryset(self):
        acl_projects, filtered = Project.objects.get_acl_status(
            self.request.user
        )
        if filtered:
            return SubProject.objects.filter(project__in=acl_projects)
        return SubProject.objects.all()
