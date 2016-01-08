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
"""Custom Weblate signals"""

from django.dispatch import Signal

vcs_post_push = Signal(providing_args=['subproject'])
vcs_post_update = Signal(providing_args=['subproject'])
vcs_pre_commit = Signal(providing_args=['translation'])
vcs_post_commit = Signal(providing_args=['translation'])
translation_post_add = Signal(providing_args=['translation'])
user_pre_delete = Signal()
