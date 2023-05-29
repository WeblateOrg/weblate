# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
