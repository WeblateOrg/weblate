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

from django import forms
from django.utils.translation import gettext_lazy as _


class HostingForm(forms.Form):
    """Form for asking for hosting."""

    message = forms.CharField(
        label=_("Additional message"),
        required=True,
        widget=forms.Textarea,
        max_length=1000,
        help_text=_(
            "Please describe the project and your relation to it, "
            "preferably in English."
        ),
    )
