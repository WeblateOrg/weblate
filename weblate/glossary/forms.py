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

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, Layout
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from weblate.glossary.models import Glossary, Term
from weblate.trans.defines import GLOSSARY_LENGTH
from weblate.utils.forms import ColorWidget
from weblate.utils.validators import validate_file_extension


class CommaSeparatedIntegerField(forms.Field):
    def to_python(self, value):
        if not value:
            return []

        try:
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        except (ValueError, TypeError):
            raise ValidationError(_("Invalid integer list!"))


class OneTermForm(forms.Form):
    """Simple one-term form."""

    term = forms.CharField(
        label=_("Search"), max_length=GLOSSARY_LENGTH, required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Div(
                Field("term", template="snippets/user-query-field.html"),
                css_class="btn-toolbar",
                role="toolbar",
            ),
        )


class GlossaryForm(forms.ModelForm):
    class Meta:
        model = Glossary
        fields = ["name", "color", "links"]
        widgets = {"color": ColorWidget}

    def __init__(self, user, project, data=None, instance=None, **kwargs):
        super().__init__(data=data, instance=instance, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.fields["links"].queryset = user.owned_projects.exclude(
            pk=project.id,
        ).filter(source_language=project.source_language)


class TermForm(forms.ModelForm):
    """Form for adding term to a glossary."""

    terms = CommaSeparatedIntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Term
        fields = ["source", "target", "glossary"]

    def __init__(self, project, data=None, instance=None, initial=None, **kwargs):
        glossaries = Glossary.objects.for_project(project).order_by("name").distinct()
        if not instance and not initial:
            initial = {}
        if initial is not None and "glossary" not in initial and len(glossaries) == 1:
            initial["glossary"] = glossaries[0]
        super().__init__(data=data, instance=instance, initial=initial, **kwargs)
        self.fields["glossary"].queryset = glossaries


class GlossaryUploadForm(forms.Form):
    """Uploading file to a glossary."""

    file = forms.FileField(
        label=_("File"),
        validators=[validate_file_extension],
        help_text=_(
            "You can upload any format understood by "
            "Translate Toolkit (including TBX, CSV or gettext PO files)."
        ),
    )
    method = forms.ChoiceField(
        label=_("Merge method"),
        choices=(
            ("", _("Keep current")),
            ("overwrite", _("Overwrite existing")),
            ("add", _("Add as other translation")),
        ),
        required=False,
    )
    glossary = forms.ModelChoiceField(
        label=_("Glossary"), queryset=Glossary.objects.none()
    )

    def __init__(self, project, data=None, initial=None, **kwargs):
        glossaries = Glossary.objects.for_project(project)
        initial = initial or {}
        if initial is not None and "glossary" not in initial and len(glossaries) == 1:
            initial["glossary"] = glossaries[0]
        super().__init__(data=data, initial=initial, **kwargs)
        self.fields["glossary"].queryset = glossaries


class LetterForm(forms.Form):
    """Form for choosing starting letter in a glossary."""

    LETTER_CHOICES = [(chr(97 + x), chr(65 + x)) for x in range(26)]
    any_letter = pgettext_lazy("Choose starting letter in glossary", "Any")
    letter = forms.ChoiceField(
        label=_("Starting letter"),
        choices=[("", any_letter)] + LETTER_CHOICES,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_class = "form-inline"
        self.helper.field_template = "bootstrap3/layout/inline_field.html"
