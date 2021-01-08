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
"""Custom Weblate signals."""

from django.dispatch import Signal

vcs_pre_push = Signal()
vcs_post_push = Signal()
vcs_post_update = Signal()
vcs_pre_update = Signal()
vcs_pre_commit = Signal()
vcs_post_commit = Signal()
translation_post_add = Signal()
component_post_update = Signal()
unit_pre_create = Signal()
user_pre_delete = Signal()
store_post_load = Signal()
