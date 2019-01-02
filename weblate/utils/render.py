# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django.core.exceptions import ValidationError
from django.template import Template, Context, Engine
from django.utils.translation import override, ugettext as _

from weblate.utils.site import get_site_url


class RestrictedEngine(Engine):
    default_builtins = [
        'django.template.defaultfilters',
        'weblate.utils.template_tags',
    ]

    def __init__(self, *args, **kwargs):
        kwargs['autoescape'] = False
        super(RestrictedEngine, self).__init__(*args, **kwargs)


def render_template(template, **kwargs):
    """Helper class to render string template with context."""
    translation = kwargs.get('translation')
    component = kwargs.get('component')
    project = kwargs.get('project')

    if getattr(translation, 'id', None):
        translation.stats.ensure_basic()
        kwargs['language_code'] = translation.language_code
        kwargs['language_name'] = translation.language.name
        kwargs['stats'] = translation.stats.get_data()
        kwargs['url'] = get_site_url(translation.get_absolute_url())
        component = translation.component

    if getattr(component, 'id', None):
        kwargs['component_name'] = component.name
        kwargs['component_slug'] = component.slug
        kwargs['component_remote_branch'] = \
            component.repository.get_remote_branch_name()
        project = component.project

    if getattr(project, 'id', None):
        kwargs['project_name'] = project.name
        kwargs['project_slug'] = project.slug

    with override('en'):
        return Template(
            template,
            engine=RestrictedEngine(),
        ).render(
            Context(kwargs, autoescape=False),
        )


def validate_render(value, **kwargs):
    """Validates rendered template."""
    try:
        render_template(value, **kwargs)
    except Exception as err:
        raise ValidationError(
            _('Failed to render template: {}').format(err)
        )
