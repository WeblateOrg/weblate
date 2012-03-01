from django import forms
from django.utils.translation import ugettext_lazy, ugettext as _

class PluralTextarea(forms.Textarea):
    '''
    Text area extension which possibly handles plurals.
    '''
    def render(self, name, value, attrs=None):
        ret = super(PluralTextarea, self).render(name, value, attrs)
        return ret

class TranslationForm(forms.Form):
    checksum = forms.CharField(widget = forms.HiddenInput)
    target = forms.CharField(widget = PluralTextarea, required = False)
    fuzzy = forms.BooleanField(label = ugettext_lazy('Fuzzy'), required = False)

