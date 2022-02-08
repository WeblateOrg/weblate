#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

import subprocess

from weblate.fonts.models import FONT_STORAGE, Font
from weblate.fonts.utils import configure_fontconfig
from weblate.trans.util import get_clean_env
from weblate.utils.celery import app


@app.task(trail=False)
def cleanup_font_files():
    """Remove stale fonts."""
    try:
        files = FONT_STORAGE.listdir(".")[1]
    except OSError:
        return
    for name in files:
        if name == "fonts.conf":
            continue
        if not Font.objects.filter(font=name).exists():
            FONT_STORAGE.delete(name)


@app.task(trail=False)
def update_fonts_cache():
    configure_fontconfig()
    subprocess.run(
        ["fc-cache"],
        env=get_clean_env(),
        check=True,
        capture_output=True,
    )


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600 * 24, cleanup_font_files.s(), name="font-files-cleanup"
    )
