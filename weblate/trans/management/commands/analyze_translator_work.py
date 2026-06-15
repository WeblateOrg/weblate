# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean, median
from typing import TYPE_CHECKING, cast

from django.core.management.base import CommandError
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date

from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, Component
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.core.management.base import CommandParser
    from django.db.models import QuerySet


TRANSLATOR_ACTIONS = (
    ActionEvents.CHANGE,
    ActionEvents.NEW,
    ActionEvents.ACCEPT,
)


class Command(BaseCommand):
    help = "Analyze realistic daily translator throughput from change history"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Number of recent days to analyze when --since is not specified",
        )
        parser.add_argument(
            "--since",
            help="Start date to analyze, in YYYY-MM-DD format",
        )
        parser.add_argument(
            "--until",
            help="End date to analyze, in YYYY-MM-DD format (defaults to now)",
        )
        parser.add_argument(
            "--project",
            help="Limit analysis to a project slug",
        )
        parser.add_argument(
            "--component",
            help="Limit analysis to a component path as project/component",
        )
        parser.add_argument(
            "--language",
            help="Limit analysis to a language code",
        )
        parser.add_argument(
            "--min-changes",
            type=int,
            default=5,
            help="Minimum translated strings per user day to include",
        )
        parser.add_argument(
            "--max-changes",
            type=int,
            default=1000,
            help="Maximum translated strings per user day to include",
        )
        parser.add_argument(
            "--max-words",
            type=int,
            default=10000,
            help="Maximum translated source words per user day to include",
        )

    def handle(self, *args: object, **options: object) -> None:
        since = self.get_since(options)
        until = self.get_until(options)
        if since >= until:
            msg = "The analysis start date must be before the end date."
            raise CommandError(msg)

        base = self.get_queryset(options).filter(
            timestamp__gte=since, timestamp__lt=until
        )
        rows = list(
            base.annotate(day=TruncDate("timestamp"))
            .values("day", "author_id", "author__username")
            .annotate(strings=Count("id"), words=Sum("unit__num_words"))
            .order_by("day", "author__username")
        )

        min_changes = cast("int", options["min_changes"])
        max_changes = cast("int", options["max_changes"])
        max_words = cast("int", options["max_words"])
        included = [
            row
            for row in rows
            if min_changes <= row["strings"] <= max_changes
            and (row["words"] or 0) <= max_words
        ]
        excluded = len(rows) - len(included)

        self.stdout.write("Translator work analysis")
        self.stdout.write(f"Period: {since:%Y-%m-%d} to {until:%Y-%m-%d}")
        self.stdout.write(
            "Included actions: "
            + ", ".join(
                ActionEvents(action).name.lower() for action in TRANSLATOR_ACTIONS
            )
        )
        self.stdout.write(
            "Filtering: active human users, unit-backed changes, "
            f"{min_changes}..{max_changes} strings/day, "
            f"up to {max_words} words/day"
        )
        self.stdout.write(f"User days: {len(included)} included, {excluded} excluded")

        if not included:
            self.stdout.write("No matching translator activity found.")
            return

        strings = [row["strings"] for row in included]
        words = [row["words"] or 0 for row in included]
        self.stdout.write("")
        self.write_metric("Translated strings per day", strings)
        self.write_metric("Source words per day", words)

    def get_queryset(self, options: dict[str, object]) -> QuerySet[Change]:
        queryset = Change.objects.filter(
            action__in=TRANSLATOR_ACTIONS,
            unit__isnull=False,
            author__isnull=False,
            author__is_active=True,
            author__is_bot=False,
        )
        if options["project"]:
            queryset = queryset.filter(project__slug=options["project"])
        if options["component"]:
            components = Component.objects.filter_by_path(
                cast("str", options["component"])
            )
            if not components.exists():
                msg = "No matching component found."
                raise CommandError(msg)
            queryset = queryset.filter(component__in=components)
        if options["language"]:
            queryset = queryset.filter(language__code=options["language"])
        return queryset

    def get_since(self, options: dict[str, object]) -> datetime:
        if options["since"]:
            parsed = parse_date(cast("str", options["since"]))
            if parsed is None:
                msg = "--since must use YYYY-MM-DD format."
                raise CommandError(msg)
            return timezone.make_aware(datetime.combine(parsed, datetime.min.time()))
        return timezone.now() - timedelta(days=cast("int", options["days"]))

    def get_until(self, options: dict[str, object]) -> datetime:
        if options["until"]:
            parsed = parse_date(cast("str", options["until"]))
            if parsed is None:
                msg = "--until must use YYYY-MM-DD format."
                raise CommandError(msg)
            return timezone.make_aware(datetime.combine(parsed, datetime.max.time()))
        return timezone.now()

    def write_metric(self, label: str, values: Iterable[int]) -> None:
        ordered = sorted(values)
        self.stdout.write(f"{label}:")
        self.stdout.write(f"  median: {median(ordered):.0f}")
        self.stdout.write(f"  average: {mean(ordered):.0f}")
        self.stdout.write(f"  p75: {self.percentile(ordered, 75):.0f}")
        self.stdout.write(f"  p90: {self.percentile(ordered, 90):.0f}")

    def percentile(self, values: list[int], percent: int) -> float:
        if len(values) == 1:
            return values[0]
        position = (len(values) - 1) * percent / 100
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight
