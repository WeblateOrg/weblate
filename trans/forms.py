from django import forms
from django.utils.translation import ugettext_lazy as _, ugettext
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_unicode

class PluralTextarea(forms.Textarea):
    '''
    Text area extension which possibly handles plurals.
    '''
    def render(self, name, value, attrs=None):
        lang, value = value
        if not isinstance(value, list):
            return super(PluralTextarea, self).render(name, value, attrs)
        ret = []
        for idx, val in enumerate(value):
            if idx > 0:
                fieldname = '%s_%d' % (name, idx)
                attrs['id'] += '_%d' % idx
            else:
                fieldname = name
            attrs['class'] = 'translation'
            textarea = super(PluralTextarea, self).render(fieldname, val, attrs)
            label = lang.get_plural_label(idx)
            ret.append('<label class="plural" for="%s">%s</label><br />%s' % (attrs['id'], label, textarea))
        pluralmsg = '<br /><span class="plural"><abbr title="%s">%s</abbr>: %s</span>' % (
            ugettext('This equation is used to identify which plural form will be used based on given count (n).'),
            ugettext('Plural equation'),
            lang.pluralequation)
        return mark_safe('<br />'.join(ret) + pluralmsg)

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
    file  = forms.FileField(label = _('File'))
    overwrite = forms.BooleanField(label = _('Overwrite existing translations'), required = False)

class SearchForm(forms.Form):
    q = forms.CharField(label = _('Query'))
    src = forms.BooleanField(label = _('Search in source strings'), required = False, initial = True)
    tgt = forms.BooleanField(label = _('Search in target strings'), required = False, initial = True)
    ctx = forms.BooleanField(label = _('Search in context strings'), required = False, initial = True)
