#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.core.exceptions import ValidationError
from django.template import Context, Engine, Template, TemplateSyntaxError
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import override

from weblate.utils.site import get_site_url

# List of schemes not allowed in editor URL
# This list is not intededed to be complete, just block
# the possibly dangerous ones.
FORBIDDEN_URL_SCHEMES = {
    "javascript",
    "data",
    "vbscript",
    "mailto",
    "ftp",
    "sms",
    "tel",
}


class InvalidString(str):
    def __mod__(self, other):
        raise TemplateSyntaxError(_('Undefined variable: "%s"') % other)


class RestrictedEngine(Engine):
    default_builtins = [
        "django.template.defaultfilters",
        "weblate.utils.templatetags.safe_render",
    ]

    def __init__(self, *args, **kwargs):
        kwargs["autoescape"] = False
        kwargs["string_if_invalid"] = InvalidString("%s")
        super().__init__(*args, **kwargs)


def render_template(template, **kwargs):
    """Helper class to render string template with context."""
    from weblate.trans.models import Component, Project, Translation

    translation = kwargs.get("translation")
    component = kwargs.get("component")
    project = kwargs.get("project")

    # Comppatibility with older templates
    if "addon_name" in kwargs:
        kwargs["hook_name"] = kwargs["addon_name"]

    if isinstance(translation, Translation):
        translation.stats.ensure_basic()
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
        kwargs[
            "component_remote_branch"
        ] = component.repository.get_remote_branch_name()
        if "url" not in kwargs:
            kwargs["url"] = get_site_url(component.get_absolute_url())
        kwargs["widget_url"] = get_site_url(
            reverse(
                "widget-image",
                kwargs={
                    "project": component.project.slug,
                    "component": component.slug,
                    "widget": "horizontal",
                    "color": "auto",
                    "extension": "svg",
                },
            )
        )
        project = component.project
        kwargs.pop("component", None)

    if isinstance(project, Project):
        kwargs["project_name"] = project.name
        kwargs["project_slug"] = project.slug
        if "url" not in kwargs:
            kwargs["url"] = get_site_url(project.get_absolute_url())
        kwargs.pop("project", None)

    with override("en"):
        return Template(template, engine=RestrictedEngine()).render(
            Context(kwargs, autoescape=False)
        )


def validate_render(value, **kwargs):
    """Validates rendered template."""
    try:
        return render_template(value, **kwargs)
    except Exception as err:
        raise ValidationError(_("Failed to render template: {}").format(err))


def validate_render_component(value, translation=None, **kwargs):
    from weblate.lang.models import Language
    from weblate.trans.models import Component, Project, Translation

    component = Component(
        project=Project(name="project", slug="project", id=-1),
        name="component",
        slug="component",
        branch="master",
        vcs="git",
        id=-1,
    )
    if translation:
        kwargs["translation"] = Translation(
            id=-1,
            component=component,
            language_code="xx",
            language=Language(name="xxx", code="xx"),
        )
    else:
        kwargs["component"] = component
    validate_render(value, **kwargs)


def validate_render_addon(value):
    validate_render_component(value, hook_name="addon", addon_name="addon")


def validate_render_commit(value):
    validate_render_component(value, translation=True, author="author")


def validate_repoweb(val):
    """Validate whether URL for repository browser is valid.

    It checks whether it can be filled in using format string.
    """
    if "%(file)s" in val or "%(line)s" in val:
        raise ValidationError(
            _(
                "The format strings are no longer supported, "
                "please use the template language instead."
            )
        )
    validate_render(val, filename="file.po", line=9, branch="master")


def validate_editor(val):
    """Validate URL for custom editor link.

    - Check whether it correctly uses format strings.
    - Check whether scheme is sane.
    """
    if not val:
        return
    validate_repoweb(val)

    if ":" not in val:
        raise ValidationError(_("The editor link lacks URL scheme!"))

    scheme = val.split(":", 1)[0]

    # Block forbidden schemes as well as format strings
    if scheme.strip().lower() in FORBIDDEN_URL_SCHEMES or "%" in scheme:
        raise ValidationError(_("Forbidden URL scheme!"))


def migrate_repoweb(val):
    return val % {
        "file": "{{filename}}",
        "../file": "{{filename|parentdir}}",
        "../../file": "{{filename|parentdir|parentdir}}",
        "../../../file": "{{filename|parentdir|parentdir}}",
        "line": "{{line}}",
        "branch": "{{branch}}",
    }
