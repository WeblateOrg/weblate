# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
Permissions abstract layer for Weblate.
"""


def can_edit(user, translation, permission):
    """
    Generic checker for changing translation.
    """
    if translation is None or user is None:
        return False
    if translation.subproject.locked:
        return False
    if not user.has_perm(permission):
        return False
    if translation.is_template() and not user.has_perm('trans.save_template'):
        return False
    if (translation.subproject.suggestion_voting and
            translation.subproject.suggestion_autoaccept > 0 and
            not user.has_perm('trans.override_suggestion')):
        return False
    return True


def can_translate(user, translation):
    """
    Checks whether user can translate given translation.
    """
    return can_edit(user, translation, 'trans.save_translation')


def can_suggest(user, translation):
    """
    Checks whether user can add suggestions to given translation.
    """
    if translation is None or user is None:
        return False
    if not translation.subproject.enable_suggestions:
        return False
    if not user.has_perm('trans.add_translation'):
        return False
    return True


def can_accept_suggestion(user, translation):
    """
    Checks whether user can accept suggestions to given translation.
    """
    return can_edit(user, translation, 'trans.accept_suggestion')


def can_delete_suggestion(user, translation):
    """
    Checks whether user can delete suggestions to given translation.
    """
    return can_edit(user, translation, 'trans.delete_suggestion')


def can_vote_suggestions(user, translation):
    """
    Checks whether user can vote suggestions on given translation.
    """
    if translation is None or user is None:
        return False
    if not translation.subproject.suggestion_voting:
        return False
    if translation.subproject.locked:
        return False
    if not user.has_perm('trans.vote_suggestion'):
        return False
    if translation.is_template() and not user.has_perm('trans.save_template'):
        return False
    return True
