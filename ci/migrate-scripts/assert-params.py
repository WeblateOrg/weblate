# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assertion for addons -> params migration."""

from weblate.addons.models import Addon
from weblate.trans.models import Component

file_format_params = Component.objects.get(pk=1).file_format_params
# check site wide params are migrated
assert "yaml_line_break" not in file_format_params
assert "yaml_indent" not in file_format_params
assert "json_indent_style" not in file_format_params
assert file_format_params["po_line_wrap"] == -1
assert file_format_params["po_keep_previous"] is False
assert file_format_params["po_no_location"] is True
assert not Addon.objects.filter(name="weblate.json.customize").exists()
assert not Addon.objects.filter(name="weblate.gettext.customize").exists()
assert Addon.objects.filter(name="weblate.gettext.msgmerge").exists()
