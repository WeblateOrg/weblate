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
"""Wrapper around django.contrib.messages to work with Django REST Framework.

It also ignories messages without request object (for example from CLI).
"""


from django.contrib.messages import add_message, constants


def get_request(request):
    """Return Django request object even for DRF requests."""
    return getattr(request, "_request", request)


def debug(request, message, extra_tags=""):
    """Add a message with the ``DEBUG`` level."""
    if request is not None:
        add_message(get_request(request), constants.DEBUG, message, extra_tags)


def info(request, message, extra_tags=""):
    """Add a message with the ``INFO`` level."""
    if request is not None:
        add_message(get_request(request), constants.INFO, message, extra_tags)


def success(request, message, extra_tags=""):
    """Add a message with the ``SUCCESS`` level."""
    if request is not None:
        add_message(get_request(request), constants.SUCCESS, message, extra_tags)


def warning(request, message, extra_tags=""):
    """Add a message with the ``WARNING`` level."""
    if request is not None:
        add_message(get_request(request), constants.WARNING, message, extra_tags)


def error(request, message, extra_tags=""):
    """Add a message with the ``ERROR`` level."""
    if request is not None:
        add_message(get_request(request), constants.ERROR, message, extra_tags)


def get_message_kind(tags):
    if "error" in tags:
        return "danger"
    for tag in ["info", "success", "warning"]:
        if tag in tags:
            return tag
    return "info"
