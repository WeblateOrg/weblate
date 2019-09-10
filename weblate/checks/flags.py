# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

import six
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy

from weblate.checks import CHECKS
from weblate.fonts.utils import get_font_weight

PLAIN_FLAGS = {
    v.enable_string: v.name
    for k, v in CHECKS.items()
    if v.default_disabled and not v.param_type
}
TYPED_FLAGS = {v.enable_string: v.name for k, v in CHECKS.items() if v.param_type}
TYPED_FLAGS_ARGS = {
    v.enable_string: v.param_type for k, v in CHECKS.items() if v.param_type
}

PLAIN_FLAGS["rst-text"] = ugettext_lazy("RST text")
PLAIN_FLAGS["md-text"] = ugettext_lazy("Markdown text")
PLAIN_FLAGS["xml-text"] = ugettext_lazy("XML text")
PLAIN_FLAGS["dos-eol"] = ugettext_lazy("DOS line endings")
PLAIN_FLAGS["url"] = ugettext_lazy("URL")
PLAIN_FLAGS["auto-java-messageformat"] = ugettext_lazy(
    "Automatically detect Java MessageFormat"
)

TYPED_FLAGS["font-family"] = ugettext_lazy("Font family")
TYPED_FLAGS_ARGS["font-family"] = six.text_type
TYPED_FLAGS["font-size"] = ugettext_lazy("Font size")
TYPED_FLAGS_ARGS["font-size"] = int
TYPED_FLAGS["font-weight"] = ugettext_lazy("Font weight")
TYPED_FLAGS_ARGS["font-weight"] = get_font_weight
TYPED_FLAGS["font-spacing"] = ugettext_lazy("Font spacing")
TYPED_FLAGS_ARGS["font-spacing"] = int
TYPED_FLAGS["priority"] = ugettext_lazy("Priority")
TYPED_FLAGS_ARGS["priority"] = int

IGNORE_CHECK_FLAGS = {CHECKS[x].ignore_string for x in CHECKS}


class Flags(object):
    def __init__(self, *args):
        self._items = {}
        self._values = {}
        for flags in args:
            self.merge(flags)

    def merge(self, flags):
        if isinstance(flags, six.string_types):
            flags = self.parse(flags)
        elif hasattr(flags, 'tag'):
            flags = self.parse_xml(flags)
        elif isinstance(flags, Flags):
            flags = flags.items()
        for flag in flags:
            if ":" in flag:
                key, value = flag.split(":", 1)
                self._values[key] = value
                self._items[key] = flag
            else:
                self._items[flag] = flag

    @staticmethod
    def parse(flags):
        """Parse comma separated list of flags."""
        for flag in flags.split(","):
            value = flag.strip()
            if not value or value in ("fuzzy", "#"):
                continue
            yield value

    @classmethod
    def parse_xml(cls, flags):
        """Parse comma separated list of flags."""
        maxwidth = flags.get("maxwidth")
        sizeunit = flags.get("size-unit")
        if maxwidth:
            if sizeunit in (None, "pixel", "point"):
                yield "max-size:{0}".format(maxwidth)
            elif sizeunit in ("byte", "char"):
                yield "max-length:{0}".format(maxwidth)
        font = flags.get("font")
        if font:
            font = font.split(";")
            yield "font-family:{}".format(font[0].strip().replace(' ', '_'))
            if len(font) > 1:
                yield "font-size:{}".format(font[1].strip())
            if len(font) > 2:
                yield "font-weight:{}".format(font[2].strip())
        text = flags.get("weblate-flags")
        if text:
            for flag in cls.parse(text):
                yield flag

    def has_value(self, key):
        return key in self._values

    def get_value(self, key):
        return TYPED_FLAGS_ARGS[key](self._values[key])

    def items(self):
        return set(self._items.values())

    def __contains__(self, key):
        return key in self._items

    def __bool__(self):
        return bool(self._items)

    # Python 2 compatibility:
    def __nonzero__(self):
        return bool(self._items)

    def format(self):
        return ", ".join(sorted(self._items.values()))

    def validate(self):
        for name in self._items.keys():
            is_typed = name in TYPED_FLAGS
            is_plain = name in PLAIN_FLAGS or name in IGNORE_CHECK_FLAGS
            if not is_typed and not is_plain:
                raise ValidationError(_('Invalid translation flag: "%s"') % name)
            if name in self._values:
                if is_plain:
                    raise ValidationError(
                        _('Translation flag has no parameters: "%s"') % name
                    )
                try:
                    self.get_value(name)
                except Exception:
                    raise ValidationError(
                        _('Wrong parameters for translation flag: "%s"') % name
                    )
            elif is_typed:
                raise ValidationError(
                    _('Missing parameters for translation flag: "%s"') % name
                )
