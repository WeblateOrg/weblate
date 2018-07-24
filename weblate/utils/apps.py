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

from django.apps import AppConfig
from django.core.checks import register

from weblate.utils.checks import check_mail_connection
from weblate.utils.data import check_data_writable
from weblate.utils.requirements import check_requirements


class UtilsConfig(AppConfig):
    name = 'weblate.utils'
    label = 'utils'
    verbose_name = 'Utils'

    def ready(self):
        register(check_requirements)
        register(check_data_writable)
        register(check_mail_connection, deploy=True)
        super(UtilsConfig, self).ready()
