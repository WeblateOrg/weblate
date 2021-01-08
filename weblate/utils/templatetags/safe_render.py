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
import os.path

from django import template
from django.template.defaulttags import do_for, do_if

register = template.Library()


@register.simple_tag()
def replace(value, char, replace_char):
    return value.replace(char, replace_char)


@register.filter
def dirname(value):
    return os.path.dirname(value)


@register.filter
def stripext(value):
    return os.path.splitext(value)[0]


@register.filter
def parentdir(value):
    return value.split("/", 1)[-1]


register.tag("if")(do_if)
register.tag("for")(do_for)
