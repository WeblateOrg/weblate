# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import cProfile
import os
import pstats

from weblate.trans.models import Component, Project
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Run simple project import to perform benchmarks."""

    help = "performs import benchmark"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        prefix = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        parser.add_argument(
            "--profile-sort", default="cumulative", help="sort order for profile stats"
        )
        parser.add_argument(
            "--profile-filter",
            default=prefix,
            help=f"filter for profile stats, defaults to {prefix}",
        )
        parser.add_argument(
            "--profile-count",
            type=int,
            default=20,
            help="number of profile stats to show",
        )
        parser.add_argument("--template", default="", help="template monolingual files")
        parser.add_argument(
            "--delete", action="store_true", help="delete after testing"
        )
        parser.add_argument("--format", default="po", help="file format")
        parser.add_argument("project", help="Existing project slug for tests")
        parser.add_argument("repo", help="Test VCS repository URL")
        parser.add_argument("mask", help="File mask")

    def handle(self, *args, **options) -> None:
        project = Project.objects.get(slug=options["project"])
        # Delete any possible previous tests
        Component.objects.filter(project=project, slug="benchmark").delete()
        profiler = cProfile.Profile()
        component = profiler.runcall(
            Component.objects.create,
            name="Benchmark",
            slug="benchmark",
            repo=options["repo"],
            filemask=options["mask"],
            template=options["template"],
            file_format=options["format"],
            project=project,
        )
        profiler.enable()
        component.after_save(
            changed_git=True,
            changed_setup=False,
            changed_template=False,
            changed_variant=False,
            changed_enforced_checks=False,
            skip_push=True,
            create=True,
        )
        profiler.disable()
        stats = pstats.Stats(profiler, stream=self.stdout)
        stats.sort_stats(options["profile_sort"])
        stats.print_stats(options["profile_filter"], options["profile_count"])
        # Delete after testing
        if options["delete"]:
            component.delete()
