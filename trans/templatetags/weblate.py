from django.template.defaultfilters import stringfilter
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.encoding import force_unicode
from django import template
import re

register = template.Library()


def fmt_whitespace(value):
    value = re.sub(r'(  +| $|^ )', '<span class="hlspace">\\1</span>', value)
    return value

@register.filter
@stringfilter
def fmttranslation(value):
    value = escape(force_unicode(value))
    value = re.sub(r'\r\n|\r|\n', '\n', value) # normalize newlines
    paras = re.split('\n', value)
    paras = [fmt_whitespace(p) for p in paras]
    value = '<br />'.join(paras)
    return mark_safe(value)
