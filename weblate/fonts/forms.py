# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
