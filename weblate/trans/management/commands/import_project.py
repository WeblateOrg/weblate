# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import re
import tempfile

from django.conf import settings
from django.core.management.base import CommandError

from weblate.formats.models import FILE_FORMATS
from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.trans.discovery import ComponentDiscovery
from weblate.trans.models import Component, Project
from weblate.trans.util import is_repo_link
from weblate.utils.files import remove_tree
from weblate.utils.management.base import BaseCommand
from weblate.vcs.base import RepositoryError
from weblate.vcs.models import VCS_REGISTRY


class Command(BaseCommand):
    """Command for mass importing of repositories into Weblate."""

    help = "imports projects with more components"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--name-template",
            default="{{ component }}",
            help="Template string, transforming the file mask match to a project name",
        )
        parser.add_argument(
            "--base-file-template",
            default="",
            help=(
                "Template string, transforming the file mask "
                "match to a monolingual base filename"
            ),
        )
        parser.add_argument(
            "--new-base-template",
            default="",
            help=(
                "Template string, transforming the file mask "
                "match to a base filename for new translations"
            ),
        )
        parser.add_argument(
            "--file-format",
            default="po",
            help="File format type, defaults to Gettext PO",
        )
        parser.add_argument(
            "--language-regex",
            default="^[^.]+$",
            help=(
                "Language filter regular expression to be used for created components"
            ),
        )
        parser.add_argument(
            "--license", default="", help="License of imported components"
        )
        parser.add_argument(
            "--vcs", default=settings.DEFAULT_VCS, help="Version control system to use"
        )
        parser.add_argument(
            "--push-url", default="", help="Set push URL for the project"
        )
        parser.add_argument(
            "--push-url-same",
            action="store_true",
            default=False,
            help="Set push URL for the project to same as pull",
        )
        parser.add_argument(
            "--disable-push-on-commit",
            action="store_false",
            default=settings.DEFAULT_PUSH_ON_COMMIT,
            dest="push_on_commit",
            help="Disable push on commit for created components",
        )
        parser.add_argument(
            "--push-on-commit",
            action="store_true",
            default=settings.DEFAULT_PUSH_ON_COMMIT,
            dest="push_on_commit",
            help="Enable push on commit for created components",
        )
        parser.add_argument(
            "--main-component",
            default=None,
            help=(
                "Define which component will be used as main - including full"
                " VCS repository"
            ),
        )
        parser.add_argument(
            "--source-language",
            default=settings.DEFAULT_LANGUAGE,
            help="Source language code",
        )
        parser.add_argument("project", help="Existing project slug")
        parser.add_argument("repo", help="VCS repository URL")
        parser.add_argument("branch", help="VCS repository branch")
        parser.add_argument("filemask", help="File mask")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.filemask: str
        self.file_format: str
        self.language_regex: str
        self.license: str
        self.main_component: str | None = None
        self.name_template: str
        self.source_language: str
        self.base_file_template: str
        self.new_base_template: str
        self.vcs: str
        self.push_url: str
        self.discovery: ComponentDiscovery | None = None
        self.logger = LOGGER
        self.push_on_commit = True

    def checkout_tmp(self, project, repo, branch):
        """Checkout project to temporary location."""
        # Create temporary working dir
        workdir = tempfile.mkdtemp(dir=project.full_path)
        # Make the temporary directory readable by others
        os.chmod(workdir, 0o755)  # noqa: S103, nosec

        # Initialize git repository
        self.logger.info("Cloning git repository...")
        try:
            gitrepo = VCS_REGISTRY[self.vcs].clone(repo, workdir, branch)
        except RepositoryError as error:
            msg = f"Failed clone: {error}"
            raise CommandError(msg) from error
        self.logger.info("Updating working copy in git repository...")
        with gitrepo.lock:
            gitrepo.configure_branch(branch)

        return workdir

    def parse_options(self, repo, options) -> None:
        """Parse parameters."""
        self.filemask = options["filemask"]
        self.vcs = options["vcs"]
        if options["push_url_same"]:
            self.push_url = repo
        else:
            self.push_url = options["push_url"]
        self.file_format = options["file_format"]
        self.language_regex = options["language_regex"]
        self.main_component = options["main_component"]
        self.name_template = options["name_template"]
        self.source_language = Language.objects.get(code=options["source_language"])
        if "%s" in self.name_template:
            self.name_template = self.name_template.replace("%s", "{{ component }}")
        self.license = options["license"]
        self.push_on_commit = options["push_on_commit"]
        self.base_file_template = options["base_file_template"]
        self.new_base_template = options["new_base_template"]
        if "%s" in self.base_file_template:
            self.base_file_template = self.base_file_template.replace(
                "%s", "{{ component }}"
            )

        # Is file format supported?
        if self.file_format not in FILE_FORMATS:
            msg = "Invalid file format: {}".format(options["file_format"])
            raise CommandError(msg)

        # Is vcs supported?
        if self.vcs not in VCS_REGISTRY:
            msg = "Invalid vcs: {}".format(options["vcs"])
            raise CommandError(msg)

        # Do we have correct mask?
        # - if there is **, then it's simple mask (it's invalid in regexp)
        # - validate regexp otherwise
        if "**" in self.filemask and "*" in self.filemask.replace("**", ""):
            match = re.escape(self.filemask)
            match = match.replace(r"\*\*", "(?P<component>[[WILDCARD]])", 1)
            match = match.replace(r"\*\*", "(?P=component)")
            match = match.replace(r"\*", "(?P<language>[[WILDCARD]])", 1)
            match = match.replace(r"\*", "(?P=language)")
            match = match.replace("[[WILDCARD]]", "[^/]*")
            self.filemask = match
        else:
            try:
                compiled = re.compile(self.filemask)
            except re.error as error:
                msg = f"Could not compile regular expression {self.filemask!r}: {error}"
                raise CommandError(msg) from error
            if (
                "component" not in compiled.groupindex
                or "language" not in compiled.groupindex
            ):
                msg = (
                    "Component regular expression lacks named group "
                    '"component" and/or "language"'
                )
                raise CommandError(msg)

    def handle(self, *args, **options) -> None:
        """Automatic import of project."""
        # Read params
        repo = options["repo"]
        branch = options["branch"]
        self.parse_options(repo, options)

        # Try to get project
        try:
            project = Project.objects.get(slug=options["project"])
        except Project.DoesNotExist as error:
            msg = 'Project "{}" not found, please create it first!'.format(
                options["project"]
            )
            raise CommandError(msg) from error

        # Get or create main component
        if is_repo_link(repo):
            try:
                component = Component.objects.get_linked(repo)
                # Avoid operating on link
                if component.is_repo_link:
                    component = component.linked_component
            except Component.DoesNotExist as error:
                msg = f"Component {repo!r} not found, please create it first!"
                raise CommandError(msg) from error
        else:
            component = self.import_initial(project, repo, branch)

        discovery = self.get_discovery(component)
        discovery.perform()

    def get_discovery(self, component, path=None):
        """Return discovery object after doing basic sanity check."""
        if self.discovery is not None:
            self.discovery.component = component
        else:
            self.discovery = ComponentDiscovery(
                component,
                match=self.filemask,
                name_template=self.name_template,
                language_regex=self.language_regex,
                base_file_template=self.base_file_template,
                new_base_template=self.new_base_template,
                file_format=self.file_format,
                path=path,
            )
            self.logger.info(
                "Found %d matching files", len(self.discovery.matched_files)
            )

            if not self.discovery.matched_files:
                msg = "Your mask did not match any files!"
                raise CommandError(msg)

            self.logger.info(
                "Found %d components", len(self.discovery.matched_components)
            )
            langs = set()
            for match in self.discovery.matched_components.values():
                langs.update(match["languages"])
            self.logger.info("Found %d languages", len(langs))

            # Do some basic sanity check on languages
            if not Language.objects.filter(code__in=langs).exists():
                msg = (
                    "None of matched languages exists, maybe you have "
                    "mixed * and ** in the mask?"
                )
                raise CommandError(msg)
        return self.discovery

    def import_initial(self, project, repo, branch):
        """Import the first repository of a project."""
        # Checkout git to temporary dir
        workdir = self.checkout_tmp(project, repo, branch)
        # Create fake discovery without existing component
        discovery = self.get_discovery(None, workdir)

        components = project.component_set.all()

        component = None

        # Create first component (this one will get full git repo)
        if self.main_component:
            match = None
            for match in discovery.matched_components.values():
                if match["slug"] == self.main_component:
                    break
            if match is None or match["slug"] != self.main_component:
                msg = "Specified --main-component was not found in matches!"
                raise CommandError(msg)
        else:
            # Try if one is already there
            for match in discovery.matched_components.values():
                try:
                    component = components.get(repo=repo, filemask=match["mask"])
                except Component.DoesNotExist:
                    continue
            # Pick random
            if component is None:
                match = next(iter(discovery.matched_components.values()))

        try:
            if component is None:
                component = components.get(slug=match["slug"])
            self.logger.warning(
                "Component %s already exists, skipping and using it "
                "as a main component",
                match["slug"],
            )
            remove_tree(workdir)
        except Component.DoesNotExist:
            self.logger.info("Creating component %s as main one", match["slug"])

            # Rename gitrepository to new name
            os.rename(workdir, os.path.join(project.full_path, match["slug"]))

            # Create new component
            component = discovery.create_component(
                None,
                match,
                existing_slugs=set(),
                existing_names=set(),
                project=project,
                source_language=self.source_language,
                repo=repo,
                branch=branch,
                vcs=self.vcs,
                push_on_commit=self.push_on_commit,
                license=self.license,
            )

        return component
