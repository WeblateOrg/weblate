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

from django.conf import settings
from django.utils.translation import get_language
from weblate_language_data.docs import DOCUMENTATION_LANGUAGES

import weblate.utils.version


def get_doc_url(page, anchor="", user=None):
    """Return URL to documentation."""
    # Should we use tagged release or latest version
    if "-dev" in weblate.utils.version.VERSION or (
        (user is None or not user.is_authenticated) and settings.HIDE_VERSION
    ):
        version = "latest"
    else:
        version = f"weblate-{weblate.utils.version.VERSION}"
    # Language variant
    code = DOCUMENTATION_LANGUAGES.get(get_language(), "en")
    # Generate URL
    url = f"https://docs.weblate.org/{code}/{version}/{page}.html"
    # Optionally append anchor
    if anchor != "":
        url += "#{}".format(anchor.replace("_", "-"))

    return url
