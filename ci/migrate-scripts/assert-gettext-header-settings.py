# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Migrate project set language team settings to file format params."""

from weblate.trans.models import Component

component1 = Component.objects.get(slug="gettext-header-settings-component-1")
component2 = Component.objects.get(slug="gettext-header-settings-component-2")

assert component1.file_format_params["po_set_language_team"] is False
assert component1.file_format_params["po_set_last_translator"] is True
assert component1.file_format_params["po_set_x_generator"] is True
assert component1.file_format_params["po_report_msgid_bugs_to"] is True

assert component2.file_format_params["po_set_language_team"] is True
assert component2.file_format_params["po_set_last_translator"] is True
assert component2.file_format_params["po_set_x_generator"] is True
assert component2.file_format_params["po_report_msgid_bugs_to"] is True
