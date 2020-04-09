#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import requests
from django.core.cache import cache

from weblate import USER_AGENT


def request(method, url, headers=None, **kwargs):
    agent = {"User-Agent": USER_AGENT}
    if headers:
        headers.update(agent)
    else:
        headers = agent
    response = requests.request(method, url, headers=headers, **kwargs)
    response.raise_for_status()
    return response


def get_uri_error(uri):
    """Return error for fetching the URL or None if it works."""
    if uri.startswith("https://nonexisting.weblate.org/"):
        return "Non existing test URL"
    cached = cache.get(f"uri-check-{uri}")
    if cached:
        return None
    try:
        with request("get", uri, stream=True):
            cache.set(f"uri-check-{uri}", True, 3600)
            return None
    except (
        requests.exceptions.HTTPError,
        requests.exceptions.ConnectionError,
    ) as error:
        return str(error)
