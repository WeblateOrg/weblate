# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.test.utils import override_settings

from weblate.trans.models import Component, Project
from weblate.utils.management.base import BaseCommand
from weblate.utils.views import create_component_from_zip


class Command(BaseCommand):
    """Run simple project import to perform benchmarks."""

    help = "performs import benchmark"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument("--template", default="", help="template monolingual files")
        parser.add_argument("--keep", action="store_true", help="keep after testing")
        parser.add_argument("--format", default="po", help="file format")
        parser.add_argument("--project", help="Existing project slug for tests")
        parser.add_argument("--repo", help="Test VCS repository URL")
        parser.add_argument("--filemask", help="File mask")
        parser.add_argument("--zipfile", help="Zip file")

    def handle(self, *args, **options) -> None:
        # Execute tasks in place
        with override_settings(CELERY_TASK_ALWAYS_EAGER=True):
            project = Project.objects.get(slug=options["project"])
            # Delete any possible previous tests
            Component.objects.filter(project=project, slug="benchmark").delete()
            params = {
                "name": "Benchmark",
                "slug": "benchmark",
                "repo": options["repo"],
                "filemask": options["filemask"],
                "template": options["template"],
                "file_format": options["format"],
                "project": project,
            }
            if options["zipfile"]:
                params["vcs"] = "local"
                params["repo"] = "local:"
                params["branch"] = "main"
                create_component_from_zip(params, options["zipfile"])
            component = Component.objects.create(**params)
            # Delete after testing
            if not options["keep"]:
                component.delete()
