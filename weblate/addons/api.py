# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Globally registered APIs whose availability depends on scoped installation."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import unquote

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import MaxLengthValidator, validate_slug
from django.shortcuts import get_object_or_404
from django.urls import include, path
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import IO

    from django.urls.resolvers import URLResolver
    from rest_framework.request import Request

    from weblate.addons.base import BaseAddon
    from weblate.addons.models import Addon
    from weblate.auth.models import User


def api_providers() -> dict[str, type[BaseAddon]]:
    """Validate provider declarations without accessing installation rows."""
    from weblate.addons.models import ADDONS  # ruff: ignore[import-outside-top-level]

    providers: dict[str, type[BaseAddon]] = {}
    for addon in ADDONS.values():
        name = addon.api_name
        if name is None:
            continue
        if not isinstance(name, str):
            msg = f"Invalid API name for {addon.name}: {name!r}"
            raise ImproperlyConfigured(msg)
        try:
            validate_slug(name)
            MaxLengthValidator(64)(name)
        except ValidationError as error:
            msg = f"Invalid API name for {addon.name}: {name!r}"
            raise ImproperlyConfigured(msg) from error
        if addon.repo_scope or not addon.needs_component or addon.multiple:
            msg = f"API provider {addon.name} must be a single-installation component add-on."
            raise ImproperlyConfigured(msg)
        if name in providers:
            msg = f"Duplicate add-on API name {name!r}: {providers[name].name} and {addon.name}."
            raise ImproperlyConfigured(msg)
        providers[name] = addon
    return providers


def api_patterns() -> list[URLResolver]:
    return [
        path(
            f"components/<str:project__slug>/<str:slug>/addons/{name}/",
            include((addon.get_api_urls(), name), namespace=name),
        )
        for name, addon in api_providers().items()
    ]


class BoundedJSONParser(JSONParser):
    max_body_size = 5 * 1024 * 1024

    def parse(
        self,
        stream: IO[Any],
        media_type: str | None = None,
        parser_context: Mapping[str, Any] | None = None,
    ) -> Any:  # ruff: ignore[any-type]
        raw = stream.read(self.max_body_size + 1)
        if len(raw) > self.max_body_size:
            msg = "Add-on request body is too large."
            raise ParseError(msg)
        try:
            return super().parse(BytesIO(raw), media_type, parser_context)
        except (ValueError, UnicodeError, RecursionError) as error:
            msg = "Invalid JSON."
            raise ParseError(msg) from error


class InstalledAddonAPIView(GenericAPIView):
    """Authenticate and resolve an enabled provider installed on this component."""

    addon_name: str
    addon: Addon
    permission = "component.edit"
    permission_classes = (IsAuthenticated,)
    parser_classes = (BoundedJSONParser,)

    def initial(self, request: Request, *args: object, **kwargs: str) -> None:
        super().initial(request, *args, **kwargs)
        from weblate.addons.models import ADDONS, Addon  # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

        if self.addon_name not in ADDONS:
            raise NotFound
        component = get_object_or_404(
            Component.objects.filter_access(cast("User", request.user)).filter_by_path(
                f"{kwargs['project__slug']}/{unquote(kwargs['slug'])}"
            ),
        )
        self.addon = get_object_or_404(Addon, component=component, name=self.addon_name)
        if not self.addon.is_valid or not self.addon.addon.can_process(
            component=component
        ):
            raise NotFound
        if not request.user.has_perm(self.permission, component):
            raise PermissionDenied
