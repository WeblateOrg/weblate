# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import UserString
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template import Context, Engine, Template, TemplateSyntaxError
from django.urls import reverse
from django.utils.functional import SimpleLazyObject
from django.utils.translation import gettext, override

from weblate.utils.site import get_site_url
from weblate.utils.validators import WeblateEditorURLValidator, WeblateURLValidator

if TYPE_CHECKING:
    from django.core.validators import URLValidator


class InvalidString(UserString):
    def __mod__(self, other: str):
        raise TemplateSyntaxError(gettext('Undefined variable: "%s"') % other)


class RestrictedEngine(Engine):
    default_builtins = [
        "django.template.defaultfilters",
        "weblate.utils.templatetags.safe_render",
    ]

    def __init__(self, *args, **kwargs) -> None:
        kwargs["autoescape"] = False
        kwargs["string_if_invalid"] = InvalidString("%s")
        super().__init__(*args, **kwargs)


def render_template(template: str, **kwargs):
    """Render string template with Weblate context."""
    from weblate.trans.models import Component, Project, Translation

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
                    "widget": "horizontal",
                    "color": "auto",
                    "extension": "svg",
                },
            )
        )
        if component.pk:
            kwargs["component_linked_childs"] = SimpleLazyObject(
                component.get_linked_childs_for_template
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
        return Template(template, engine=RestrictedEngine()).render(
            Context(kwargs, autoescape=False)
        )


def validate_render(value: str, **kwargs) -> str:
    """Validate rendered template."""
    try:
        return render_template(value, **kwargs)
    except Exception as err:
        raise ValidationError(
            gettext("Could not render template: {}").format(err)
        ) from err


def validate_render_mock(value: str, *, translation: bool = False, **kwargs) -> str:
    from weblate.lang.models import Language
    from weblate.trans.models import Component, Project, Translation
    from weblate.utils.stats import DummyTranslationStats

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
        kwargs["translation"] = Translation(
            id=-1,
            component=component,
            language_code="xx",
            language=Language(name="xxx", code="xx"),
        )
        kwargs["translation"].stats = DummyTranslationStats(translation)
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
        and val.split("://")[0].lower() in WeblateEditorURLValidator.schemes
    ):
        validator = WeblateEditorURLValidator()
    else:
        validator = WeblateURLValidator()
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
