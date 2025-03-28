# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from django.core.cache import cache
from django.utils import timezone
from django.utils.functional import Promise, cached_property
from django.utils.translation import pgettext_lazy

from weblate.metrics.models import Metric

MONTH_NAMES = [
    pgettext_lazy("Short name of month", "Jan"),
    pgettext_lazy("Short name of month", "Feb"),
    pgettext_lazy("Short name of month", "Mar"),
    pgettext_lazy("Short name of month", "Apr"),
    pgettext_lazy("Short name of month", "May"),
    pgettext_lazy("Short name of month", "Jun"),
    pgettext_lazy("Short name of month", "Jul"),
    pgettext_lazy("Short name of month", "Aug"),
    pgettext_lazy("Short name of month", "Sep"),
    pgettext_lazy("Short name of month", "Oct"),
    pgettext_lazy("Short name of month", "Nov"),
    pgettext_lazy("Short name of month", "Dec"),
]


class MetricsWrapper:
    def __init__(self, obj, scope: int, relation: int, secondary: int = 0) -> None:
        self.obj = obj
        self.scope = scope
        self.relation = relation
        self.secondary = secondary

    @cached_property
    def _data(self) -> tuple[Metric, Metric, Metric]:
        today = timezone.now().date()
        dates = [today - timedelta(days=days) for days in [0, 1, 30, 31, 60, 61]]

        # Use use range as it is more likely to use index than
        # the IN operator with six values.
        metrics = Metric.objects.filter_metric(
            self.scope, self.relation, self.secondary
        ).filter(date__range=(dates[-1], dates[0]))

        # Fetch the most recent metric for each date
        current = past_30 = past_60 = Metric()
        for metric in metrics:
            if metric.date in dates[0:2] and current.pk is None:
                current = metric
            if metric.date in dates[2:4] and past_30.pk is None:
                past_30 = metric
            if metric.date in dates[4:6] and past_60.pk is None:
                past_30 = metric

        return (current, past_30, past_60)

    @property
    def current(self) -> Metric:
        return self._data[0]

    @property
    def past_30(self) -> Metric:
        return self._data[1]

    @property
    def past_60(self) -> Metric:
        return self._data[2]

    @property
    def all_words(self) -> int:
        return self.current["all_words"]

    @property
    def all(self) -> int:
        return self.current["all"]

    @property
    def translated_percent(self) -> float:
        total = self.all
        if not total:
            return 0
        return 100 * self.current["translated"] / total

    @property
    def contributors(self) -> int:
        return self.current.get("contributors", 0)

    @property
    def contributors_total(self) -> int:
        return self.current.get("contributors_total", 0)

    def calculate_trend_percent(
        self, key, modkey, base: Metric, origin: Metric
    ) -> float:
        total = base.get(key, 0)
        if not total:
            return 0
        divisor = base[modkey]
        if not divisor:
            return 0
        total = 100 * total / divisor

        past = origin[key]
        if not past:
            return total

        divisor = origin[modkey]
        if not divisor:
            return total
        past = 100 * past / divisor
        return total - past

    def calculate_trend(self, key, base: Metric, origin: Metric) -> float:
        total = base.get(key, 0)
        if not total:
            return 0
        return 100 * (total - origin[key]) / total

    @property
    def trend_30_all(self) -> float:
        return self.calculate_trend("all", self.current, self.past_30)

    @property
    def trend_30_all_words(self) -> float:
        return self.calculate_trend("all_words", self.current, self.past_30)

    @property
    def trend_30_contributors(self) -> float:
        return self.calculate_trend("contributors", self.current, self.past_30)

    @property
    def trend_30_translated_percent(self) -> float:
        return self.calculate_trend_percent(
            "translated", "all", self.current, self.past_30
        )

    @property
    def trend_60_all(self) -> float:
        return self.calculate_trend("all", self.past_30, self.past_60)

    @property
    def trend_60_all_words(self) -> float:
        return self.calculate_trend("all_words", self.past_30, self.past_60)

    @property
    def trend_60_contributors(self) -> float:
        return self.calculate_trend("contributors", self.past_30, self.past_60)

    @property
    def trend_60_translated_percent(self) -> float:
        return self.calculate_trend_percent(
            "translated", "all", self.past_30, self.past_60
        )

    @property
    def projects(self) -> int:
        return self.current["projects"]

    @property
    def languages(self) -> int:
        return self.current["languages"]

    @property
    def components(self) -> int:
        return self.current["components"]

    @property
    def users(self) -> int:
        return self.current["users"]

    @property
    def trend_30_projects(self) -> float:
        return self.calculate_trend("projects", self.current, self.past_30)

    @property
    def trend_30_languages(self) -> float:
        return self.calculate_trend("languages", self.current, self.past_30)

    @property
    def trend_30_components(self) -> float:
        return self.calculate_trend("components", self.current, self.past_30)

    @property
    def trend_30_users(self) -> float:
        return self.calculate_trend("users", self.current, self.past_30)

    @property
    def trend_60_projects(self) -> float:
        return self.calculate_trend("projects", self.past_30, self.past_60)

    @property
    def trend_60_languages(self) -> float:
        return self.calculate_trend("languages", self.past_30, self.past_60)

    @property
    def trend_60_components(self) -> float:
        return self.calculate_trend("components", self.past_30, self.past_60)

    @property
    def trend_60_users(self) -> float:
        return self.calculate_trend("users", self.past_30, self.past_60)

    def get_daily_activity(self, start: date, days: int) -> dict[date, int]:
        today = timezone.now().date()
        kwargs = {
            "scope": self.scope,
            "relation": self.relation,
        }
        if self.secondary:
            kwargs["secondary"] = self.secondary
        result = dict(
            Metric.objects.filter(
                date__range=(start - timedelta(days=days), start),
                **kwargs,
            ).values_list("date", "changes")
        )
        for offset in range(days):
            current = start - timedelta(days=offset)
            if current not in result:
                if current == today:
                    # Lazily calculate today value (if task is not running)
                    result[current] = Metric.objects.calculate_changes(
                        date=current,
                        obj=self.obj,
                        **kwargs,
                    )
                else:
                    # Use zero if metric is not stored
                    result[current] = 0
        return result

    @cached_property
    def daily_activity(self) -> list[int]:
        today = timezone.now().date()
        result = [0] * 52
        for pos, value in self.get_daily_activity(today, 52).items():
            result[51 - (today - pos).days] = value
        return result

    @cached_property
    def cache_key_prefix(self) -> str:
        return f"metrics:{self.scope}:{self.relation}:{self.secondary}"

    def get_month_cache_key(self, year, month) -> str:
        return f"{self.cache_key_prefix}:month:{year}:{month}"

    def get_month_activity(
        self, year: int, month: int, cached_results: dict[str, int]
    ) -> int:
        cache_key = self.get_month_cache_key(year, month)
        if cache_key in cached_results:
            return cached_results[cache_key]
        numdays = monthrange(year, month)[1]
        daily = self.get_daily_activity(date(year, month, numdays), numdays - 1)
        result = sum(daily.values())
        # Cache for one year
        cache.set(cache_key, result, 365 * 24 * 3600)
        return result

    @cached_property
    def monthly_activity(self) -> list[dict[str, int | date | str | Promise]]:
        months: list[tuple[int, int]] = []
        prefetch: list[str] = []
        last_month_date = timezone.now().date().replace(day=1) - timedelta(days=1)
        month = last_month_date.month
        year = last_month_date.year
        for _dummy in range(12):
            months.append((year, month))
            prefetch.extend(
                (
                    self.get_month_cache_key(year, month),
                    self.get_month_cache_key(year - 1, month),
                )
            )
            month -= 1
            if month < 1:
                month = 12
                year -= 1

        cached_results: dict[str, int] = cache.get_many(prefetch)
        result: list[dict[str, int | date | str | Promise]] = [
            {
                "month": month,
                "year": year,
                "previous_year": year - 1,
                "month_name": MONTH_NAMES[month - 1],
                "start_date": date(year, month, 1),
                "end_date": date(year, month, monthrange(year, month)[1]),
                "previous_start_date": date(year - 1, month, 1),
                "previous_end_date": date(
                    year - 1, month, monthrange(year - 1, month)[1]
                ),
                "current": self.get_month_activity(year, month, cached_results),
                "previous": self.get_month_activity(year - 1, month, cached_results),
            }
            for year, month in reversed(months)
        ]

        maximum = max(1, *(max(item["current"], item["previous"]) for item in result))  # type: ignore[call-overload]
        for item in result:
            item["current_height"] = 140 * item["current"] // maximum  # type: ignore[operator]
            item["current_offset"] = 140 - item["current_height"]  # type: ignore[operator]
            item["previous_height"] = 140 * item["previous"] // maximum  # type: ignore[operator]
            item["previous_offset"] = 140 - item["previous_height"]  # type: ignore[operator]

        return result
