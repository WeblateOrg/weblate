# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

from django.core.management.base import CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from weblate.trans.models import Component
from weblate.trans.translator_analysis import (
    TRANSLATOR_ACTIONS,
    analyze_translator_work,
    get_translator_work_queryset,
)
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser
    from django.db.models import QuerySet

    from weblate.trans.models import Change


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

        min_changes = cast("int", options["min_changes"])
        max_changes = cast("int", options["max_changes"])
        max_words = cast("int", options["max_words"])
        data = analyze_translator_work(
            since=since,
            until=until,
            language=cast("str", options["language"] or ""),
            min_changes=min_changes,
            max_changes=max_changes,
            max_words=max_words,
            queryset=self.get_queryset(options),
        )

        self.stdout.write("Translator work analysis")
        self.stdout.write(f"Period: {since:%Y-%m-%d} to {until:%Y-%m-%d}")
        self.stdout.write(
            "Included actions: "
            + ", ".join(action.name.lower() for action in TRANSLATOR_ACTIONS)
        )
        self.stdout.write(
            "Filtering: active human users, unit-backed changes, "
            f"{min_changes}..{max_changes} strings/day, "
            f"up to {max_words} words/day"
        )
        self.stdout.write(
            f"User days: {data['user_days']['included']} included, "
            f"{data['user_days']['excluded']} excluded"
        )

        if not data["metrics"]:
            self.stdout.write("No matching translator activity found.")
            return

        self.stdout.write("")
        self.write_metric("Translated strings per day", data["metrics"]["strings"])
        self.write_metric("Source words per day", data["metrics"]["words"])

    def get_queryset(self, options: dict[str, object]) -> QuerySet[Change]:
        queryset = get_translator_work_queryset(
            language=cast("str", options["language"] or "")
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

    def write_metric(self, label: str, values: dict[str, float]) -> None:
        self.stdout.write(f"{label}:")
        self.stdout.write(f"  median: {values['median']:.0f}")
        self.stdout.write(f"  average: {values['average']:.0f}")
        self.stdout.write(f"  p75: {values['p75']:.0f}")
        self.stdout.write(f"  p90: {values['p90']:.0f}")
