# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from django.test.utils import override_settings

from weblate.lang.models import Language
from weblate.trans.models import Component, Project
from weblate.utils.management.base import BaseCommand
from weblate.utils.views import create_component_from_zip
from weblate.vcs.git import LocalRepository

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(BaseCommand):
    """Run simple project import to perform benchmarks."""

    help = "performs import benchmark"

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument("--template", default="", help="template monolingual files")
        parser.add_argument("--keep", action="store_true", help="keep after testing")
        parser.add_argument("--format", default="po", help="file format")
        parser.add_argument("--project", help="Existing project slug for tests")
        parser.add_argument("--repo", help="Test VCS repository URL")
        parser.add_argument("--filemask", help="File mask")
        parser.add_argument("--zipfile", help="Zip file")
        parser.add_argument("--source-language", help="Source language code")

    def handle(self, *args, **options) -> None:
        # Execute tasks in place. Glossary auto-creation is disabled so the
        # benchmark measures only the requested component import path.
        with override_settings(
            CELERY_TASK_ALWAYS_EAGER=True,
            CREATE_GLOSSARIES=False,
        ):
            project = Project.objects.get(slug=options["project"])
            # Delete any possible previous tests
            Component.objects.filter(project=project, slug="benchmark").delete()
            params: dict[str, Any] = {
                "name": "Benchmark",
                "slug": "benchmark",
                "repo": options["repo"],
                "filemask": options["filemask"],
                "template": options["template"],
                "file_format": options["format"],
                "project": project,
            }
            if options["source_language"]:
                params["source_language"] = Language.objects.get(
                    code=options["source_language"]
                )
            if options["zipfile"]:
                params["vcs"] = "local"
                params["repo"] = "local:"
                params["branch"] = "main"
                original_limits = LocalRepository.ZIP_IMPORT_LIMITS
                # Benchmark archives are expected to be large; keep all ZIP
                # member safety checks, but remove only the aggregate size cap
                # while importing data for this command.
                LocalRepository.ZIP_IMPORT_LIMITS = replace(
                    original_limits, max_total_uncompressed_size=None
                )
                try:
                    create_component_from_zip(params, options["zipfile"])
                finally:
                    LocalRepository.ZIP_IMPORT_LIMITS = original_limits
            component = Component.objects.create(**params)
            # Delete after testing
            if not options["keep"]:
                component.delete()
