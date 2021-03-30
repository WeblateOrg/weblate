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


from itertools import chain

from django.conf import settings

from weblate.utils.licensedata import LICENSES

LIBRE_IDS = {license[0] for license in LICENSES if license[3]}
LICENSE_URLS = {
    license[0]: license[2] for license in chain(LICENSES, settings.LICENSE_EXTRA)
}
LOWER_LICENSES = {license[0].lower(): license[0] for license in LICENSES}

FIXUPS = (
    ("polymer license", "bsd-3-clause"),
    ("apache license", "apache"),
    ("bsd beerware derivative", "beerware"),
    ("gnu general public licence", "gpl-2.0-or-later"),
    ("mit like license", "mit"),
    ("-2+", "-2.0+"),
    ("v2", "-2.0"),
    ("v3", "-3.0"),
    ("+", "-or-later"),
    ("gnu ", ""),
    (" ", "-"),
    ("--", "-"),
)


def is_libre(license):
    return license in LIBRE_IDS


def get_license_url(license):
    try:
        return LICENSE_URLS[license]
    except KeyError:
        return None


def get_license_choices():
    license_filter = settings.LICENSE_FILTER
    if not license_filter or "proprietary" in license_filter:
        result = [("proprietary", "Proprietary")]
    else:
        result = []
    for license in LICENSES:
        if license_filter is not None and license[0] not in license_filter:
            continue
        result.append((license[0], license[1]))

    for license in settings.LICENSE_EXTRA:
        result.append((license[0], license[1]))

    return result


def convert_license(license):
    """Convert license to SPDX identifier, used in migration."""
    license = license.strip().lower()

    if not license:
        return ""

    if " or " in license:
        license = license.split(" or ")[0]

    if license in LOWER_LICENSES:
        return LOWER_LICENSES[license]

    # Simply tokenize
    for token in license.split():
        token = token.strip("+")
        if license in LOWER_LICENSES:
            return LOWER_LICENSES[license]

    # Some replacements
    for fixup, replacement in FIXUPS:
        if fixup in license:
            license = license.replace(fixup, replacement)
            if license in LOWER_LICENSES:
                return LOWER_LICENSES[license]

    # Append only
    license += "-only"
    if license in LOWER_LICENSES:
        return LOWER_LICENSES[license]

    return "proprietary"
