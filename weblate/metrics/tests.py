#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

from weblate.metrics.models import Metric
from weblate.metrics.tasks import cleanup_metrics, collect_metrics
from weblate.trans.models import Project
from weblate.trans.tests.test_views import FixtureTestCase


class MetricTestCase(FixtureTestCase):
    def test_collect(self):
        collect_metrics()
        self.assertNotEqual(Metric.objects.count(), 0)

    def test_collect_global(self):
        Metric.objects.collect_global()
        self.assertNotEqual(Metric.objects.count(), 0)

    def test_cleanup(self):
        collect_metrics()
        count = Metric.objects.count()
        cleanup_metrics()
        self.assertEqual(count, Metric.objects.count())
        Project.objects.all().delete()
        cleanup_metrics()
        new_count = Metric.objects.count()
        self.assertNotEqual(count, new_count)
        self.assertNotEqual(0, new_count)
