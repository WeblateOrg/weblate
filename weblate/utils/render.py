# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template import Context, TemplateSyntaxError
from django.template.base import render_value_in_context
from django.urls import reverse
from django.utils.timezone import get_current_timezone_name
from django.utils.translation import gettext, override

from weblate.utils.outbound import validate_runtime_url
from weblate.utils.render_engine import check_text, encode_request, encode_value
from weblate.utils.render_worker import (
    ERROR_LIMIT,
    OUTPUT_LIMIT,
    RENDER_TIMEOUT,
    SOURCE_LIMIT,
)
from weblate.utils.site import get_site_url
from weblate.utils.validators import WeblateEditorURLValidator, WeblateURLValidator

if TYPE_CHECKING:
    from django.core.validators import URLValidator


def render_simple(source: str, values: dict[str, object]) -> str | None:
    """Keep frequent flat substitutions bounded without starting a process."""
    if "{%" in source or "{#" in source:
        return None
    parts = source.split("{{")
    substitutions = []
    for part in parts[1:]:
        name, closing, tail = part.partition("}}")
        if "\n" in name:
            return None
        name = name.strip()
        if (
            not closing
            or not name.isascii()
            or not name.isidentifier()
            or name.startswith("_")
            or name not in values
            or type(values[name]) not in {str, int, float, bool, type(None)}
        ):
            return None
        substitutions.append((name, tail))
    result = [parts[0]]
    size = check_text(parts[0])
    context = Context(autoescape=False)
    for name, tail in substitutions:
        # These are built-in scalars only, without user-provided conversion hooks.
        value = render_value_in_context(values[name], context)
        size += check_text(value) + check_text(tail)
        if size > OUTPUT_LIMIT:
            msg = gettext("Template output exceeds its size limit.")
            raise TemplateSyntaxError(msg)
        result.extend((value, tail))
    return "".join(result)


def render_isolated(source: str, values: dict[str, object]) -> str:
    payload = encode_request(
        {
            "template": source,
            "context": encode_value(values),
            "use_tz": settings.USE_TZ,
            "time_zone": get_current_timezone_name(),
            "thousands": settings.USE_THOUSAND_SEPARATOR,
        }
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("render_worker.py"))],
            input=payload,
            capture_output=True,
            timeout=RENDER_TIMEOUT,
            check=True,
            env={"LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        msg = gettext("Template rendering failed or exceeded its resource limits.")
        raise TemplateSyntaxError(msg) from error
    return decode_response(completed.stdout)


def decode_response(data: bytes) -> str:
    if len(data) > OUTPUT_LIMIT * 6 + ERROR_LIMIT:
        raise TemplateSyntaxError(gettext("Oversized template response."))
    try:
        response = json.loads(data)
        rendered = response.get("text")
        error = response.get("error")
    except (ValueError, AttributeError) as parse_error:
        raise TemplateSyntaxError(
            gettext("Invalid template rendering response.")
        ) from parse_error
    if isinstance(error, str):
        raise TemplateSyntaxError(gettext(error[:ERROR_LIMIT]))
    if not isinstance(rendered, str):
        raise TemplateSyntaxError(gettext("Invalid template rendering response."))
    check_text(rendered)
    return rendered


def render_template(template: str, **kwargs: object) -> str:
    """Render string template with Weblate context."""
    check_text(template, SOURCE_LIMIT)

    from weblate.trans.models import (  # ruff: ignore[import-outside-top-level]
        Component,
        Project,
        Translation,
    )

    translation = kwargs.get("translation")
    component = kwargs.get("component")
    project = kwargs.get("project")

    # Comppatibility with older templates
    if "addon_name" in kwargs:
        kwargs["hook_name"] = kwargs["addon_name"]

    if isinstance(translation, Translation):
        kwargs["language_code"] = translation.language_code
        kwargs["language_name"] = translation.language.get_name()
        kwargs["stats"] = translation.stats.get_data()
        kwargs["url"] = get_site_url(translation.get_absolute_url())
        kwargs["filename"] = translation.filename
        component = translation.component
        kwargs.pop("translation", None)

    if isinstance(component, Component):
        kwargs["component_name"] = component.name
        kwargs["component_full_name"] = str(component)
        kwargs["component_slug"] = component.slug
        kwargs["component_remote_branch"] = (
            component.repository.get_remote_branch_name()
        )
        if "url" not in kwargs:
            kwargs["url"] = get_site_url(component.get_absolute_url())
        kwargs["widget_url"] = get_site_url(
            reverse(
                "widget-image",
                kwargs={
                    "path": component.get_url_path(),
                    "widget": "matrix",
                    "color": "auto",
                    "extension": "svg",
                },
            )
        )
        if component.pk and "component_linked_children" in template:
            kwargs["component_linked_children"] = (
                component.get_linked_children_for_template()
            )
        project = component.project
        kwargs.pop("component", None)

    if isinstance(project, Project):
        kwargs["project_name"] = project.name
        kwargs["project_slug"] = project.slug
        if "url" not in kwargs:
            kwargs["url"] = get_site_url(project.get_absolute_url())
        kwargs.pop("project", None)

    kwargs["site_title"] = settings.SITE_TITLE
    kwargs["site_url"] = get_site_url()

    with override("en"):
        rendered = render_simple(template, kwargs)
        if rendered is None:
            rendered = render_isolated(template, kwargs)
    # Django marks this result safe even though its source was not HTML-escaped.
    # These templates produce plain text; a plain str lets HTML sinks escape it.
    return "" + rendered


def validate_render(value: str, **kwargs: object) -> str:
    """Validate rendered template."""
    try:
        return render_template(value, **kwargs)
    except Exception as err:
        raise ValidationError(
            gettext("Could not render template: {}").format(err)
        ) from err


def validate_render_mock(
    value: str, *, translation: bool = False, **kwargs: object
) -> str:
    from weblate.lang.models import Language  # ruff: ignore[import-outside-top-level]
    from weblate.trans.models import (  # ruff: ignore[import-outside-top-level]
        Component,
        Project,
        Translation,
    )

    # ruff: ignore[import-outside-top-level]
    from weblate.utils.stats import (
        DummyTranslationStats,
    )

    project = Project(name="project", slug="project", id=-1)
    project.stats = DummyTranslationStats(project)  # type: ignore[assignment]
    component = Component(
        project=project,
        name="component",
        slug="component",
        branch="main",
        source_language=Language(name="aa", code="x-aa"),
        vcs="git",
        id=-1,
    )
    component.stats = DummyTranslationStats(component)  # type: ignore[assignment]
    if translation:
        mock_translation = Translation(
            id=-1,
            component=component,
            language_code="xx",
            language=Language(name="xxx", code="xx"),
        )
        mock_translation.stats = DummyTranslationStats(mock_translation)  # type: ignore[assignment]
        kwargs["translation"] = mock_translation
    else:
        kwargs["component"] = component
    return validate_render(value, **kwargs)


def validate_render_translation(value: str) -> None:
    validate_render_mock(value, translation=True)


def validate_render_component(value: str) -> None:
    validate_render_mock(value)


def validate_render_addon(value: str) -> None:
    validate_render_mock(value, hook_name="addon", addon_name="addon")


def validate_render_commit(value: str) -> None:
    validate_render_mock(value, translation=True, author="author")


def validate_repoweb(val: str, allow_editor: bool = False) -> None:
    """
    Validate whether URL for repository browser is valid.

    It checks whether it can be filled in using format string.
    """
    if "%(file)s" in val or "%(line)s" in val:
        raise ValidationError(
            gettext(
                "The format strings are no longer supported, "
                "please use the template language instead."
            )
        )
    url = validate_render_mock(val, filename="file.po", line=9, branch="main")

    validator: URLValidator
    if (
        allow_editor
        and val.split("://", 1)[0].lower() in WeblateEditorURLValidator.schemes
    ):
        validator = WeblateEditorURLValidator()
    elif allow_editor:
        validator = WeblateURLValidator()
    else:
        validator = WeblateURLValidator()
        try:
            validate_runtime_url(
                url, allow_private_targets=not settings.PROJECT_WEB_RESTRICT_PRIVATE
            )
        except ValidationError as error:
            if not isinstance(error.__cause__, OSError):
                raise
    validator(url)


def validate_editor(val: str) -> None:
    """
    Validate URL for custom editor link.

    - Check whether it correctly uses format strings.
    - Check whether scheme is sane.
    """
    if not val:
        return
    validate_repoweb(val, allow_editor=True)
