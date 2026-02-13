# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assertion for encoding -> params migration."""

from weblate.trans.models import Component

assert (
    Component.objects.get(
        slug="strings-utf16", file_format="strings"
    ).file_format_params["strings_encoding"]
    == "utf-16"
)
assert (
    Component.objects.get(
        slug="strings-utf8", file_format="strings"
    ).file_format_params["strings_encoding"]
    == "utf-8"
)
assert (
    Component.objects.get(
        slug="java-properties-iso8859-1", file_format="properties"
    ).file_format_params["properties_encoding"]
    == "iso-8859-1"
)
assert (
    Component.objects.get(
        slug="java-properties-utf8", file_format="properties"
    ).file_format_params["properties_encoding"]
    == "utf-8"
)
assert (
    Component.objects.get(
        slug="java-properties-utf16", file_format="properties"
    ).file_format_params["properties_encoding"]
    == "utf-16"
)
assert (
    Component.objects.get(slug="csv-auto", file_format="csv").file_format_params[
        "csv_encoding"
    ]
    == "auto"
)
assert (
    Component.objects.get(slug="csv-utf-8", file_format="csv").file_format_params[
        "csv_encoding"
    ]
    == "utf-8"
)
assert (
    Component.objects.get(
        slug="csv-simple-auto", file_format="csv-simple"
    ).file_format_params["csv_simple_encoding"]
    == "auto"
)
assert (
    Component.objects.get(
        slug="csv-simple-utf-8", file_format="csv-simple"
    ).file_format_params["csv_simple_encoding"]
    == "utf-8"
)
assert (
    Component.objects.get(
        slug="csv-simple-iso8859-1", file_format="csv-simple"
    ).file_format_params["csv_simple_encoding"]
    == "iso-8859-1"
)
assert (
    Component.objects.get(slug="gwt-iso", file_format="gwt").file_format_params[
        "gwt_encoding"
    ]
    == "iso-8859-1"
)
assert (
    Component.objects.get(slug="gwt-utf-8", file_format="gwt").file_format_params[
        "gwt_encoding"
    ]
    == "utf-8"
)
