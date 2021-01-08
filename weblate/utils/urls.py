#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django.urls import register_converter
from django.urls.converters import StringConverter


class WeblateSlugConverter(StringConverter):
    regex = "[^/]+"


class GitPathConverter(StringConverter):
    regex = "(info/|git-upload-pack)[a-z0-9_/-]*"


class WordConverter(StringConverter):
    regex = "[^/-]+"


class WidgetExtensionConverter(StringConverter):
    regex = "(png|svg)"


class OptionalPathConverter(StringConverter):
    regex = "(info/|git-upload-pack)[a-z0-9_/-]*|"


register_converter(WeblateSlugConverter, "name")
register_converter(GitPathConverter, "gitpath")
register_converter(WordConverter, "word")
register_converter(WidgetExtensionConverter, "extension")
register_converter(OptionalPathConverter, "optionalpath")
