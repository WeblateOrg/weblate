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

from __future__ import unicode_literals

from django import forms
from django.core.validators import FileExtensionValidator
from django.utils.translation import ugettext_lazy as _


class UploadForm(forms.Form):
    """Uploading file to a dictionary."""
    file = forms.FileField(
        label=_('File'),
        validators=[
            FileExtensionValidator(allowed_extensions=['json', 'tmx'])
        ],
        help_text=_('You can upload a TMX or JSON file.')
    )


class DeleteForm(forms.Form):
    confirm = forms.BooleanField(
        label=_('Confirm deleting all translation memory entries'),
        required=True,
    )


class ImportForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        initial=True,
        widget=forms.HiddenInput,
    )
