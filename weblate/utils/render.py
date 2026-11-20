# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template import TemplateSyntaxError
from django.urls import reverse
from django.utils.translation import gettext, override

from weblate.utils.outbound import validate_runtime_url
from weblate.utils.render_context import validate_context
from weblate.utils.render_engine import check_text, render_bounded
from weblate.utils.render_limits import SOURCE_LIMIT
from weblate.utils.render_policy import TemplateDiagnosticError
from weblate.utils.site import get_site_url
from weblate.utils.validators import WeblateEditorURLValidator, WeblateURLValidator

if TYPE_CHECKING:
    from django.core.validators import URLValidator

    from weblate.utils.render_context import TemplateContext


def prepare_template_context(
    template: str, values: dict[str, object]
) -> TemplateContext:
    """Expand Weblate objects and snapshot the complete evaluation context."""
    kwargs = values.copy()

    from weblate.trans.models import (  # ruff: ignore[import-outside-top-level]
        Component,
        Project,
        Translation,
    )

    translation = kwargs.get("translation")
    component = kwargs.get("component")
    project = kwargs.get("project")

    # Compatibility with older templates
    if "addon_name" in kwargs:
        kwargs["hook_name"] = kwargs["addon_name"]

    # Inspect the actual type, without consulting arbitrary __class__ hooks.
    if issubclass(type(translation), Translation):
        translation = cast("Translation", translation)
        kwargs["language_code"] = translation.language_code
        kwargs["language_name"] = translation.language.get_name()
        kwargs["stats"] = translation.stats.get_data()
        kwargs["url"] = get_site_url(translation.get_absolute_url())
        kwargs["filename"] = translation.filename
        component = translation.component
        kwargs.pop("translation", None)

    if issubclass(type(component), Component):
        component = cast("Component", component)
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

    if issubclass(type(project), Project):
        project = cast("Project", project)
        kwargs["project_name"] = project.name
        kwargs["project_slug"] = project.slug
        if "url" not in kwargs:
            kwargs["url"] = get_site_url(project.get_absolute_url())
        kwargs.pop("project", None)

    kwargs["site_title"] = settings.SITE_TITLE
    kwargs["site_url"] = get_site_url()

    return validate_context(kwargs)


def render_template(template: str, **kwargs: object) -> str:
    """Render string template with validated Weblate context."""
    return _render_template(template, kwargs)


def _render_template(
    template: str, values: dict[str, object], *, for_validation: bool = False
) -> str:
    check_text(template, SOURCE_LIMIT)
    context = prepare_template_context(template, values)

    with override("en"):
        rendered = render_bounded(template, context, for_validation=for_validation)
    # Django marks this result safe even though its source was not HTML-escaped.
    # These templates produce plain text; a plain str lets HTML sinks escape it.
    return "" + rendered


def render_repository_template(template: str, *, setting: str, **kwargs: object) -> str:
    """Expose configured message failures through repository error handling."""
    from weblate.vcs.base import RepositoryTemplateError  # ruff: ignore[import-outside-top-level]

    try:
        with override("en"):
            return render_template(template, **kwargs)
    except TemplateSyntaxError as error:
        diagnostic = (
            str(error)
            if isinstance(error, TemplateDiagnosticError)
            else "Template rendering failed."
        )
        raise RepositoryTemplateError(setting, diagnostic) from error


def validate_render(value: str, **kwargs: object) -> str:
    """Validate a submitted template with editor diagnostics."""
    try:
        return _render_template(value, kwargs, for_validation=True)
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
