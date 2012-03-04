from django import forms
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_unicode

class PluralTextarea(forms.Textarea):
    '''
    Text area extension which possibly handles plurals.
    '''
    def render(self, name, value, attrs=None):
        if type(value) != list:
            return super(PluralTextarea, self).render(name, value, attrs)
        ret = []
        for idx, val in enumerate(value):
            if idx > 0:
                fieldname = '%s_%d' % (name, idx)
            else:
                fieldname = name
            ret.append(super(PluralTextarea, self).render(fieldname, val, attrs))
        return mark_safe('<br />'.join(ret))

    def value_from_datadict(self, data, files, name):
        ret = [data.get(name, None)]
        for idx in range(1, 10):
            fieldname = '%s_%d' % (name, idx)
            if not fieldname in data:
                break
            ret.append(data.get(fieldname, None))
        ret = [smart_unicode(r.replace('\r', '')) for r in ret]
        if len(ret) == 0:
            return ret[0]
        return ret

class PluralField(forms.CharField):
    def __init__(self, max_length=None, min_length=None, *args, **kwargs):
        super(PluralField, self).__init__(*args, widget = PluralTextarea, **kwargs)

    def to_python(self, value):
        # We can get list from PluralTextarea
        return value

class TranslationForm(forms.Form):
    checksum = forms.CharField(widget = forms.HiddenInput)
    target = PluralField(required = False)
    fuzzy = forms.BooleanField(label = _('Fuzzy'), required = False)

class UploadForm(forms.Form):
    file  = forms.FileField()
    overwrite = forms.BooleanField(label = _('Overwrite existing translations'), required = False)
