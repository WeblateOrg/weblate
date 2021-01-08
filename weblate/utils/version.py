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


from collections import namedtuple
from datetime import datetime, timedelta
from distutils.version import LooseVersion

from dateutil.parser import parse
from django.core.cache import cache
from django.core.checks import Info

from weblate import VERSION_BASE
from weblate.utils.checks import weblate_check
from weblate.utils.requests import request

PYPI = "https://pypi.org/pypi/Weblate/json"
CACHE_KEY = "version-check"


Release = namedtuple("Release", ["version", "timestamp"])


def download_version_info():
    response = request("get", PYPI)
    result = []
    for version, info in response.json()["releases"].items():
        if not info:
            continue
        result.append(Release(version, parse(info[0]["upload_time"])))
    return sorted(result, key=lambda x: x[1], reverse=True)


def flush_version_cache():
    cache.delete(CACHE_KEY)


def get_version_info():
    result = cache.get(CACHE_KEY)
    if not result:
        result = download_version_info()
        cache.set(CACHE_KEY, result, 86400)
    return result


def get_latest_version():
    return get_version_info()[0]


def check_version(app_configs=None, **kwargs):
    try:
        latest = get_latest_version()
    except (ValueError, OSError):
        return []
    if LooseVersion(latest.version) > LooseVersion(VERSION_BASE):
        # With release every two months, this get's triggered after three releases
        if latest.timestamp + timedelta(days=180) < datetime.now():
            return [
                weblate_check(
                    "weblate.C031",
                    "You Weblate version is outdated, please upgrade to {}.".format(
                        latest.version
                    ),
                )
            ]
        return [
            weblate_check(
                "weblate.I031",
                "New Weblate version is available, please upgrade to {}.".format(
                    latest.version
                ),
                Info,
            )
        ]
    return []
