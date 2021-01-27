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


import os.path

from django.core.files.storage import DefaultStorage

from weblate.screenshots.models import Screenshot
from weblate.utils.celery import app


@app.task(trail=False)
def cleanup_screenshot_files():
    """Remove stale screenshots."""
    storage = DefaultStorage()
    try:
        files = storage.listdir("screenshots")[1]
    except OSError:
        return
    for name in files:
        fullname = os.path.join("screenshots", name)
        if not Screenshot.objects.filter(image=fullname).exists():
            storage.delete(fullname)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600 * 24, cleanup_screenshot_files.s(), name="screenshot-files-cleanup"
    )
