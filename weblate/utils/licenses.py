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


from itertools import chain

from django.conf import settings

from weblate.utils.licensedata import LICENSES

LIBRE_IDS = {
    name
    for name, _verbose, _url, is_libre in chain(LICENSES, settings.LICENSE_EXTRA)
    if is_libre
}
LICENSE_URLS = {
    name: url
    for name, _verbose, url, _is_libre in chain(LICENSES, settings.LICENSE_EXTRA)
}


def is_libre(name):
    return name in LIBRE_IDS


def get_license_url(name):
    try:
        return LICENSE_URLS[name]
    except KeyError:
        return None


def get_license_choices():
    license_filter = settings.LICENSE_FILTER
    if license_filter is None or "proprietary" in license_filter:
        result = [("proprietary", "Proprietary")]
    else:
        result = []
    for name, verbose, _url, _is_libre in LICENSES:
        if license_filter is not None and name not in license_filter:
            continue
        result.append((name, verbose))

    for name, verbose, _url, _is_libre in settings.LICENSE_EXTRA:
        result.append((name, verbose))

    return result
