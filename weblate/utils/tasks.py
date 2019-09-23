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

from __future__ import absolute_import, unicode_literals

import os

from django.core.management.commands import diffsettings

from weblate.celery import app
from weblate.utils.data import data_dir


@app.task(trail=False)
def ping():
    return None


@app.task(trail=False)
def settings_backup(indent=2):
    os.makedirs(data_dir("backups"))
    filename = data_dir("backups", "settings.py")
    with open(filename, "w") as handle:
        handle.write(diffsettings.Command().handle())


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(3600 * 24, settings_backup.s(), name="settings-backup")
