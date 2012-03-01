from django import forms
from django.utils.translation import ugettext_lazy, ugettext as _
from django.utils.safestring import mark_safe

class PluralTextarea(forms.Textarea):
    '''
    Text area extension which possibly handles plurals.
    '''
    def render(self, name, value, attrs=None):
        if type(value) != list:
            return super(PluralTextarea, self).render(name, value, attrs)
        ret = []
        print value
        for idx, val in enumerate(value):
            if idx > 0:
                fieldname = '%s_%d' % (name, idx)
            else:
                fieldname = name
            ret.append(super(PluralTextarea, self).render(fieldname, val, attrs))
        return mark_safe('<br />'.join(ret))

class PluralField(forms.CharField):
    def __init__(self, max_length=None, min_length=None, *args, **kwargs):
        super(PluralField, self).__init__(*args, widget = PluralTextarea, **kwargs)

class TranslationForm(forms.Form):
    checksum = forms.CharField(widget = forms.HiddenInput)
    target = PluralField(required = False)
    fuzzy = forms.BooleanField(label = ugettext_lazy('Fuzzy'), required = False)

