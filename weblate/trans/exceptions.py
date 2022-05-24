#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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


class WeblateError(Exception):
    """Base class for Weblate errors."""

    def __init__(self, message=None):
        super().__init__(message or self.__doc__)


class FileParseError(WeblateError):
    """File parse error."""


class PluralFormsMismatch(WeblateError):
    """Plural forms do not match the language."""


class InvalidTemplate(WeblateError):
    """Template file can not be parsed."""

    def __init__(self, nested, message=None):
        super().__init__(message or f"Template file can not be parsed: {nested}")
        self.nested = nested
