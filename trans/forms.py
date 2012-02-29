from django import forms
from django.utils.translation import ugettext_lazy, ugettext as _

class TranslationForm(forms.Form):
    checksum = forms.CharField(widget = forms.HiddenInput)
    target = forms.CharField(widget = forms.Textarea, required = False)
    fuzzy = forms.BooleanField(label = ugettext_lazy('Fuzzy'), required = False)

