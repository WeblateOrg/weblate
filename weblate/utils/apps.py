# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from weblate.utils.checks import (
    check_cache,
    check_celery,
    check_data_writable,
    check_database,
    check_errors,
    check_mail_connection,
    check_perms,
    check_python,
    check_settings,
    check_site,
    check_templates,
)
from weblate.utils.django_hacks import monkey_patch_translate
from weblate.utils.errors import init_error_collection
from weblate.utils.requirements import check_requirements


class UtilsConfig(AppConfig):
    name = 'weblate.utils'
    label = 'utils'
    verbose_name = 'Utils'

    def ready(self):
        super(UtilsConfig, self).ready()
        register(check_requirements)
        register(check_data_writable)
        register(check_mail_connection, deploy=True)
        register(check_celery, deploy=True)
        register(check_database, deploy=True)
        register(check_cache, deploy=True)
        register(check_settings, deploy=True)
        register(check_templates, deploy=True)
        register(check_site, deploy=True)
        register(check_perms, deploy=True)
        register(check_errors, deploy=True)
        register(check_python, deploy=True)

        monkey_patch_translate()

        init_error_collection()
