# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.management.base import CommandError
from django.utils.text import slugify
from rest_framework.exceptions import ValidationError

from weblate.api.serializers import ComponentSerializer
from weblate.trans.models import Component, Project
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class ImportUser:
    """User object granting permissions for serializer validation."""

    needs_component_restrictions_filter = False
    needs_project_filter = False
    component_permissions: tuple[int, ...] = ()

    def has_perm(self, perm, obj=None) -> bool:
        return True

    def get_author_name(self) -> str:
        return "Weblate import"


class ImportRequest:
    """Request object for serializer context."""

    user = ImportUser()


def format_serializer_error(error: ValidationError) -> str:
    return str(error.detail)


def get_component_serializer(
    project: Project, data: dict[str, Any], component: Component | None = None
) -> ComponentSerializer:
    if component is not None and "source_language" in data:
        data = data.copy()
        del data["source_language"]
    kwargs: dict[str, Any] = {
        "context": {"request": ImportRequest(), "project": project},
        "data": data,
    }
    if component is not None:
        kwargs["instance"] = component
        kwargs["partial"] = True
    return ComponentSerializer(**kwargs)


class Command(BaseCommand):
    """Command for mass importing of repositories into Weblate based on JSON data."""

    help = "imports projects based on JSON data"

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--project", default=None, required=True, help="Project where to operate"
        )
        parser.add_argument(
            "--ignore",
            default=False,
            action="store_true",
            help="Ignore already existing entries",
        )
        parser.add_argument(
            "--update",
            default=False,
            action="store_true",
            help="Update already existing entries",
        )
        parser.add_argument(
            "--main-component",
            default=None,
            help="Define which component will be used as main for the VCS repository",
        )
        parser.add_argument(
            "json-file",
            type=Path,
            help="JSON file containing component definition",
        )

    # ruff: ignore[complex-structure]
    def handle(self, *args, **options) -> None:
        """Automatic import of components."""
        # Get project
        try:
            project = Project.objects.get(slug=options["project"])
        except Project.DoesNotExist as error:
            msg = "Project does not exist!"
            raise CommandError(msg) from error

        # Get main component
        main_component = None
        if options["main_component"]:
            try:
                main_component = Component.objects.get(
                    project=project, slug=options["main_component"]
                )
            except Component.DoesNotExist as error:
                msg = "Main component does not exist!"
                raise CommandError(msg) from error
        try:
            handle = options["json-file"].open("r")
        except OSError as error:
            msg = f"Could not open file: {error}"
            raise CommandError(msg) from error
        with handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError as error:
                msg = "Could not parse JSON file!"
                raise CommandError(msg) from error

        # Handle dumps from API
        if "results" in data:
            data = data["results"]

        for item in data:
            if "filemask" not in item or "name" not in item:
                msg = "Missing required fields in JSON!"
                raise CommandError(msg)

            if "slug" not in item:
                item["slug"] = slugify(item["name"])

            if "repo" not in item:
                if main_component is None:
                    msg = "No main component and no repository URL!"
                    raise CommandError(msg)
                item["repo"] = main_component.get_repo_link_url()

            try:
                component = Component.objects.get(slug=item["slug"], project=project)
            except Component.DoesNotExist:
                serializer = get_component_serializer(project, item)
                try:
                    serializer.is_valid(raise_exception=True)
                    component = serializer.save()
                except ValidationError as error:
                    self.stderr.write(format_serializer_error(error))
                    msg = "Component failed validation!"
                    raise CommandError(msg) from error
                self.stdout.write(
                    f"Imported {component} with {component.translation_set.count()} translations"
                )
            else:
                self.stderr.write(f"Component {component} already exists")
                if options["ignore"]:
                    continue
                if options["update"]:
                    serializer = get_component_serializer(project, item, component)
                    try:
                        serializer.is_valid(raise_exception=True)
                        serializer.save()
                    except ValidationError as error:
                        self.stderr.write(format_serializer_error(error))
                        msg = "Component failed validation!"
                        raise CommandError(msg) from error
                    continue
                msg = "Component already exists, use --ignore or --update!"
                raise CommandError(msg)
