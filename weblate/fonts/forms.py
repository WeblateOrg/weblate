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

from weblate.fonts.models import Font, FontGroup, FontOverride


class FontForm(forms.ModelForm):
    class Meta:
        model = Font
        fields = ("font",)


class FontGroupForm(forms.ModelForm):
    class Meta:
        model = FontGroup
        fields = ("name", "font")

    def __init__(self, data=None, project=None, **kwargs):
        super().__init__(data, **kwargs)
        self.fields["font"].queryset = self.fields["font"].queryset.filter(
            project=project
        )


class FontOverrideForm(forms.ModelForm):
    class Meta:
        model = FontOverride
        fields = ("language", "font")
