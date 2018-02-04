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
from django.utils.encoding import force_text


class RestrictedEngine(Engine):
    default_builtins = [
        'django.template.defaultfilters',
    ]


def render_template(template, translation=None):
    """Helper class to render string template with context."""
    context = {}
    if translation is not None:
        translation.stats.ensure_basic()
        context['project_name'] = translation.subproject.project.name
        context['project_slug'] = translation.subproject.project.slug
        context['component_name'] = translation.subproject.name
        context['component_slug'] = translation.subproject.slug
        context['language_code'] = translation.language_code
        context['language_name'] = force_text(translation.language)
        context['stats'] = translation.stats.get_data()
    return Template(
        template,
        engine=RestrictedEngine(autoescape=False),
    ).render(
        Context(context),
    )
