# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from django.template import Template, Context, Engine
from django.utils.translation import override
from weblate.utils.site import get_site_url


class RestrictedEngine(Engine):
    default_builtins = [
        'django.template.defaultfilters',
        'weblate.utils.template_tags',
    ]

    def __init__(self, *args, **kwargs):
        kwargs['autoescape'] = False
        super(RestrictedEngine, self).__init__(*args, **kwargs)


def render_template(template, translation=None, **kwargs):
    """Helper class to render string template with context."""
    context = {}
    context.update(kwargs)

    if translation is not None:
        translation.stats.ensure_basic()
        context['project_name'] = translation.component.project.name
        context['project_slug'] = translation.component.project.slug
        context['component_name'] = translation.component.name
        context['component_slug'] = translation.component.slug
        context['language_code'] = translation.language_code
        context['language_name'] = translation.language.name
        context['stats'] = translation.stats.get_data()
        context['url'] = get_site_url(translation.get_absolute_url())

    with override('en'):
        return Template(
            template,
            engine=RestrictedEngine(),
        ).render(
            Context(context, autoescape=False),
        )
