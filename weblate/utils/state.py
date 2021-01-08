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


from django.utils.translation import pgettext_lazy

STATE_EMPTY = 0
STATE_FUZZY = 10
STATE_TRANSLATED = 20
STATE_APPROVED = 30
STATE_READONLY = 100

STATE_CHOICES = (
    (STATE_EMPTY, pgettext_lazy("String state", "Empty")),
    (STATE_FUZZY, pgettext_lazy("String state", "Needs editing")),
    (STATE_TRANSLATED, pgettext_lazy("String state", "Translated")),
    (STATE_APPROVED, pgettext_lazy("String state", "Approved")),
    (STATE_READONLY, pgettext_lazy("String state", "Read only")),
)

STATE_NAMES = {
    "empty": STATE_EMPTY,
    "untranslated": STATE_EMPTY,
    "needs-editing": STATE_FUZZY,
    "fuzzy": STATE_FUZZY,
    "translated": STATE_TRANSLATED,
    "approved": STATE_APPROVED,
    "readonly": STATE_READONLY,
    "read-only": STATE_READONLY,
}
