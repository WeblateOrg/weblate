# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from django.core.exceptions import ValidationError


def validate_repoweb(val):
    try:
        val % {'file': 'file.po', 'line': '9', 'branch': 'master'}
    except Exception as e:
        raise ValidationError(_('Bad format string (%s)') % str(e))


def validate_commit_message(val):
    try:
        val % {
            'language': 'cs',
            'language_name': 'Czech',
            'project': 'Weblate',
            'subproject': 'master',
            'total': 200,
            'fuzzy': 20,
            'fuzzy_percent': 10.0,
            'translated': 40,
            'translated_percent': 20.0,
        }
    except Exception as e:
        raise ValidationError(_('Bad format string (%s)') % str(e))


def validate_filemask(val):
    if not '*' in val:
        raise ValidationError(
            _('File mask does not contain * as a language placeholder!')
        )


def validate_repo(val):
    try:
        repo = get_linked_repo(val)
        if repo is not None and repo.is_repo_link():
            raise ValidationError(_('Can not link to linked repository!'))
    except SubProject.DoesNotExist:
        raise ValidationError(_('Invalid link to repository!'))
