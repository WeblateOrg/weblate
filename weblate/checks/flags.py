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
import json

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from weblate.checks.models import CHECKS
from weblate.checks.parser import SYNTAXCHARS, FlagsParser, single_value_flag
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

PLAIN_FLAGS["rst-text"] = gettext_lazy("RST text")
PLAIN_FLAGS["md-text"] = gettext_lazy("Markdown text")
PLAIN_FLAGS["xml-text"] = gettext_lazy("XML text")
PLAIN_FLAGS["dos-eol"] = gettext_lazy("DOS line endings")
PLAIN_FLAGS["url"] = gettext_lazy("URL")
PLAIN_FLAGS["auto-java-messageformat"] = gettext_lazy(
    "Automatically detect Java MessageFormat"
)
PLAIN_FLAGS["read-only"] = gettext_lazy("Read only")
PLAIN_FLAGS["strict-same"] = gettext_lazy("Strict unchanged check")

TYPED_FLAGS["font-family"] = gettext_lazy("Font family")
TYPED_FLAGS_ARGS["font-family"] = single_value_flag(str)
TYPED_FLAGS["font-size"] = gettext_lazy("Font size")
TYPED_FLAGS_ARGS["font-size"] = single_value_flag(int)
TYPED_FLAGS["font-weight"] = gettext_lazy("Font weight")
TYPED_FLAGS_ARGS["font-weight"] = single_value_flag(get_font_weight)
TYPED_FLAGS["font-spacing"] = gettext_lazy("Font spacing")
TYPED_FLAGS_ARGS["font-spacing"] = single_value_flag(int)
TYPED_FLAGS["priority"] = gettext_lazy("Priority")
TYPED_FLAGS_ARGS["priority"] = single_value_flag(int)
TYPED_FLAGS["max-length"] = gettext_lazy("Maximum length of translation")
TYPED_FLAGS_ARGS["max-length"] = single_value_flag(int)

IGNORE_CHECK_FLAGS = {CHECKS[x].ignore_string for x in CHECKS}

FLAG_ALIASES = {"markdown-text": "md-text"}


class Flags:
    def __init__(self, *args):
        self._items = {}
        self._values = {}
        for flags in args:
            self.merge(flags)

    def get_items(self, flags):
        if isinstance(flags, str):
            return self.parse(flags)
        elif hasattr(flags, "tag"):
            return self.parse_xml(flags)
        elif isinstance(flags, Flags):
            return flags.items()
        return flags

    def merge(self, flags):
        for flag in self.get_items(flags):
            if isinstance(flag, tuple):
                self._values[flag[0]] = flag[1:]
                self._items[flag[0]] = flag
            elif flag and flag not in ("fuzzy", "#"):
                # Ignore some flags
                self._items[flag] = flag

    def remove(self, flags):
        for flag in self.get_items(flags):
            if isinstance(flag, tuple):
                key = flag[0]
                value = flag[1:]
                if key in self._values and self._values[key] == value:
                    del self._values[key]
                    del self._items[key]
            else:
                self._items.pop(flag, None)

    @staticmethod
    def parse(flags):
        """Parse comma separated list of flags."""
        state = 0
        name = None
        value = []
        for token in FlagsParser.parseString(flags, parseAll=True):
            if state == 0 and token == ",":
                pass
            elif state == 0:
                # Handle aliases
                if token in FLAG_ALIASES:
                    name = FLAG_ALIASES[token]
                else:
                    name = token
                value = [name]
                state = 1
            elif state == 1 and token == ",":
                state = 0
                yield name
            elif state in (1, 3) and token == ":":
                # Value separator
                state = 2
            elif state == 2:
                # Value
                value.append(token)
                state = 3
            elif state == 3 and token == ",":
                # Last value
                yield tuple(value)
                state = 0
            else:
                raise ValueError("Unexpected token: {}, state={}".format(token, state))

        if state > 0:
            if len(value) > 1:
                yield tuple(value)
            else:
                yield name

    @classmethod
    def parse_xml(cls, flags):
        """Parse comma separated list of flags."""
        maxwidth = flags.get("maxwidth")
        sizeunit = flags.get("size-unit")
        if maxwidth:
            if sizeunit in (None, "pixel", "point"):
                yield "max-size", maxwidth
            elif sizeunit in ("byte", "char"):
                yield "max-length", maxwidth
        font = flags.get("font")
        if font:
            font = font.split(";")
            yield "font-family", font[0].strip().replace(" ", "_")
            if len(font) > 1:
                yield "font-size", font[1].strip()
            if len(font) > 2:
                yield "font-weight", font[2].strip()
        text = flags.get("weblate-flags")
        if text:
            yield from cls.parse(text)

    def has_value(self, key):
        return key in self._values

    def get_value(self, key):
        return TYPED_FLAGS_ARGS[key](self._values[key])

    def items(self):
        return set(self._items.values())

    def __iter__(self):
        return self._items.__iter__()

    def __contains__(self, key):
        return key in self._items

    def __bool__(self):
        return bool(self._items)

    @staticmethod
    def format_value(value):
        if any(c in value for c in SYNTAXCHARS):
            return json.dumps(value, ensure_ascii=False)
        return value

    @classmethod
    def format_flag(cls, flag):
        if isinstance(flag, tuple):
            return ":".join(cls.format_value(val) for val in flag)
        return cls.format_value(flag)

    def _format_values(self):
        return (self.format_flag(item) for item in self._items.values())

    def format(self):
        return ", ".join(sorted(self._format_values()))

    def validate(self):
        for name in self._items:
            if isinstance(name, tuple):
                name = name[0]
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
