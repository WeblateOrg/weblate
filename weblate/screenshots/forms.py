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

from weblate.screenshots.models import Screenshot
from weblate.trans.forms import QueryField
from weblate.utils.forms import SortedSelect


class ScreenshotEditForm(forms.ModelForm):
    """Screenshot editing."""

    class Meta:
        model = Screenshot
        fields = ("name", "image")


class LanguageChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.language


class ScreenshotForm(forms.ModelForm):
    """Screenshot upload."""

    class Meta:
        model = Screenshot
        fields = ("name", "image", "translation")
        widgets = {
            "translation": SortedSelect,
        }
        field_classes = {
            "translation": LanguageChoiceField,
        }

    def __init__(self, component, data=None, files=None, instance=None):
        self.component = component
        super().__init__(data=data, files=files, instance=instance)
        self.fields[
            "translation"
        ].queryset = component.translation_set.prefetch_related("language")
        self.fields["translation"].initial = component.source_translation


class SearchForm(forms.Form):
    q = QueryField(required=False)
