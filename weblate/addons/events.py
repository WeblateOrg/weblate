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

EVENT_POST_PUSH = 1
EVENT_POST_UPDATE = 2
EVENT_PRE_COMMIT = 3
EVENT_POST_COMMIT = 4
EVENT_POST_ADD = 5
EVENT_UNIT_PRE_CREATE = 6
EVENT_STORE_POST_LOAD = 7
EVENT_UNIT_POST_SAVE = 8

EVENT_CHOICES = (
    (EVENT_POST_PUSH, 'post push'),
    (EVENT_POST_UPDATE, 'post update'),
    (EVENT_PRE_COMMIT, 'pre commit'),
    (EVENT_POST_COMMIT, 'post commit'),
    (EVENT_POST_ADD, 'post add'),
    (EVENT_UNIT_PRE_CREATE, 'unit post create'),
    (EVENT_UNIT_POST_SAVE, 'unit post save'),
    (EVENT_STORE_POST_LOAD, 'store post load'),
)
