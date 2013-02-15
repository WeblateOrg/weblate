# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

"""
Tests for notification hooks.
"""

from django.core.urlresolvers import reverse
from django.utils import simplejson
from weblate.trans.tests.test_views import ViewTestCase


class HooksViewTest(ViewTestCase):
    def test_view_hook_project(self):
        response = self.client.get(
            reverse('hook-project', kwargs={
                'project': self.subproject.project.slug
            })
        )
        self.assertContains(response, 'update triggered')

    def test_view_hook_subproject(self):
        response = self.client.get(
            reverse('hook-subproject', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
            })
        )
        self.assertContains(response, 'update triggered')
