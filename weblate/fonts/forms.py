# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import cast

from django import forms

from weblate.fonts.models import Font, FontGroup, FontOverride
from weblate.utils.forms import AssetFileField


class FontForm(forms.ModelForm):
    class Meta:
        model = Font
        fields = ("font",)
        # ruff: ignore[mutable-class-default]
        field_classes = {"font": AssetFileField}


class FontGroupForm(forms.ModelForm):
    class Meta:
        model = FontGroup
        fields = ("name", "font")

    def __init__(self, data=None, project=None, **kwargs) -> None:
        super().__init__(data, **kwargs)
        field = cast("forms.ModelChoiceField", self.fields["font"])
        field.queryset = field.queryset.filter(project=project)  # type: ignore[union-attr]


class FontOverrideForm(forms.ModelForm):
    class Meta:
        model = FontOverride
        fields = ("language", "font")
