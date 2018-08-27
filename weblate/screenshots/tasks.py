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

from __future__ import absolute_import, unicode_literals

import os.path

from celery import shared_task

from django.core.files.storage import DefaultStorage

from weblate.screenshots.models import Screenshot


@shared_task
def cleanup_screenshot_files():
    """Remove stale screenshots"""
    storage = DefaultStorage()
    try:
        files = storage.listdir('screenshots')[1]
    except OSError:
        return
    for name in files:
        fullname = os.path.join('screenshots', name)
        if not Screenshot.objects.filter(image=fullname).exists():
            storage.delete(fullname)
