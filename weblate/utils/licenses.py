# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.conf import settings

from weblate.utils.licensedata import LICENSES

ALL_LICENSES = (*LICENSES, *settings.LICENSE_EXTRA)

LIBRE_IDS = {name for name, _verbose, _url, is_libre in ALL_LICENSES if is_libre}
LICENSE_URLS = {name: url for name, _verbose, url, _is_libre in ALL_LICENSES}
LICENSE_NAMES = {name: verbose for name, verbose, _url, _is_libre in ALL_LICENSES}


def is_libre(name):
    return name in LIBRE_IDS


def get_license_url(name):
    return LICENSE_URLS.get(name, None)


def get_license_name(name):
    return LICENSE_NAMES.get(name, name)


def get_license_choices():
    license_filter = settings.LICENSE_FILTER
    if license_filter is None or "proprietary" in license_filter:
        result = [("proprietary", "Proprietary")]
    else:
        result = []

    result.extend(
        (name, verbose)
        for name, verbose, _url, _is_libre in LICENSES
        if license_filter is None or name in license_filter
    )

    result.extend(
        (name, verbose) for name, verbose, _url, _is_libre in settings.LICENSE_EXTRA
    )

    return result
