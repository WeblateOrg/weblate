# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Add components for file format charset migration testing."""

from weblate.trans.models import Component

Component.objects.bulk_create(
    [
        Component(
            name="iOS Strings UTF16",
            slug="strings-utf16",
            project_id=1,
            repo="weblate://test/stringsutf16",
            file_format="strings",
            filemask="strings/*.strings",
        ),
        Component(
            name="iOS Strings UTF8",
            slug="strings-utf8",
            project_id=1,
            repo="weblate://test/stringsutf8",
            file_format="strings-utf8",
            filemask="strings/*.strings",
        ),
        Component(
            name="Java Properties UTF 8",
            slug="java-properties-utf8",
            project_id=1,
            repo="weblate://test/propertiesutf8",
            file_format="properties-utf8",
            filemask="properties/*.properties",
        ),
        Component(
            name="Java Properties UTF 16",
            slug="java-properties-utf16",
            project_id=1,
            repo="weblate://test/propertiesutf16",
            file_format="properties-utf16",
            filemask="properties/*.properties",
        ),
        Component(
            name="Java Properties ISO 8859-1",
            slug="java-properties-iso8859-1",
            project_id=1,
            repo="weblate://test/propertiesutfiso8859-1",
            file_format="properties",
            filemask="properties/*.properties",
        ),
        Component(
            name="CSV Auto",
            slug="csv-auto",
            project_id=1,
            repo="weblate://test/csvauto",
            file_format="csv",
            filemask="csv/*.csv",
        ),
        Component(
            name="CSV UTF-8",
            slug="csv-utf-8",
            project_id=1,
            repo="weblate://test/csvutf-8",
            file_format="csv-utf-8",
            filemask="csv/*.csv",
        ),
        Component(
            name="CSV Simple Auto",
            slug="csv-simple-auto",
            project_id=1,
            repo="weblate://test/csvsimpleauto",
            file_format="csv-simple",
            filemask="csv-simple/*.csv",
        ),
        Component(
            name="CSV Simple UTF-8",
            slug="csv-simple-utf-8",
            project_id=1,
            repo="weblate://test/csvsimpleutf-8",
            file_format="csv-simple-utf-8",
            filemask="csv-simple/*.csv",
        ),
        Component(
            name="CSV Simple ISO 8859-1",
            slug="csv-simple-iso8859-1",
            project_id=1,
            repo="weblate://test/csvsimpleiso8859-1",
            file_format="csv-simple-iso",
            filemask="csv-simple/*.csv",
        ),
        Component(
            name="GWT ISO 8859-1",
            slug="gwt-iso",
            project_id=1,
            repo="weblate://test/gwtiso",
            file_format="gwt-iso",
            filemask="gwt/*.properties",
        ),
        Component(
            name="GWT UTF-8",
            slug="gwt-utf-8",
            project_id=1,
            repo="weblate://test/gwtutf-8",
            file_format="gwt",
            filemask="gwt/*.properties",
        ),
    ]
)
