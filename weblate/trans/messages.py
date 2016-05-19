# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Wrapper around django.contrib.messages to work with Django REST Framework as
well.
"""

from __future__ import unicode_literals
from django.contrib.messages import constants
from django.contrib.messages import add_message


def get_request(request):
    """
    Returns Django request object even for DRF requests.
    """
    if hasattr(request, '_request'):
        return getattr(request, '_request')
    return request


def debug(request, message):
    """
    Adds a message with the ``DEBUG`` level.
    """
    add_message(get_request(request), constants.DEBUG, message)


def info(request, message):
    """
    Adds a message with the ``INFO`` level.
    """
    add_message(get_request(request), constants.INFO, message)


def success(request, message):
    """
    Adds a message with the ``SUCCESS`` level.
    """
    add_message(get_request(request), constants.SUCCESS, message)


def warning(request, message):
    """
    Adds a message with the ``WARNING`` level.
    """
    add_message(get_request(request), constants.WARNING, message)


def error(request, message):
    """
    Adds a message with the ``ERROR`` level.
    """
    add_message(get_request(request), constants.ERROR, message)
