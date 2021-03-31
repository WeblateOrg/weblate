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
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, Optional, Set

from django.db import models
from django.db.models import Q


class MetricQuerySet(models.QuerySet):
    def get_current(self, scope: int, relation: int, secondary: int = 0, **kwargs):
        from weblate.metrics.tasks import collect_metrics

        today = date.today()
        yesterday = today - timedelta(days=1)

        # Get todays stats
        data = dict(
            self.filter(
                scope=scope,
                relation=relation,
                secondary=secondary,
                date=today,
                **kwargs,
            ).values_list("name", "value")
        )
        if not data:
            # Fallback to yesterday in case they are not yet calculated
            data = dict(
                self.filter(
                    scope=scope,
                    relation=relation,
                    secondary=secondary,
                    date=yesterday,
                    **kwargs,
                ).values_list("name", "value")
            )
        if (
            not data
            and not self.filter(
                (Q(date=yesterday) | Q(date=today)) & Q(scope=Metric.SCOPE_GLOBAL)
            ).exists()
        ):
            # Trigger collection in case no data is present
            collect_metrics()
            return self.get_current(scope, relation, secondary, **kwargs)
        return data

    def get_past(
        self, scope: int, relation: int, secondary: int = 0, delta: int = 30, **kwargs
    ):
        return defaultdict(
            int,
            self.filter(
                scope=scope,
                relation=relation,
                secondary=secondary,
                date=date.today() - timedelta(days=delta),
                **kwargs,
            ).values_list("name", "value"),
        )


class MetricsManager(models.Manager):
    def create_metrics(
        self,
        data: Dict,
        stats: Optional[Dict],
        keys: Set,
        scope: int,
        relation: int,
        secondary: int = 0,
    ):
        if stats is not None:
            for key in keys:
                data[key] = getattr(stats, key)

        self.bulk_create(
            [
                Metric(
                    scope=scope,
                    relation=relation,
                    secondary=secondary,
                    name=name,
                    value=value,
                )
                for name, value in data.items()
            ]
        )


class Metric(models.Model):
    SCOPE_GLOBAL = 0
    SCOPE_PROJECT = 1
    SCOPE_COMPONENT = 2
    SCOPE_TRANSLATION = 3
    SCOPE_USER = 4
    SCOPE_COMPONENT_LIST = 5
    SCOPE_PROJECT_LANGUAGE = 6

    date = models.DateField(auto_now_add=True)
    scope = models.SmallIntegerField()
    relation = models.IntegerField()
    secondary = models.IntegerField(default=0)
    name = models.CharField(max_length=100)
    value = models.IntegerField(db_index=True)

    objects = MetricsManager.from_queryset(MetricQuerySet)()

    class Meta:
        unique_together = (("date", "scope", "relation", "secondary", "name"),)

    def __str__(self):
        return f"<{self.scope}.{self.relation}>:{self.date}:{self.name}={self.value}"
