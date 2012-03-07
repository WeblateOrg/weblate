from django.template.defaultfilters import stringfilter
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.encoding import force_unicode
from django import template
from django.conf import settings
import re

from trans.util import split_plural
from lang.models import Language

register = template.Library()


def fmt_whitespace(value):
    value = re.sub(r'(  +| $|^ )', '<span class="hlspace">\\1</span>', value)
    return value

@register.filter
@stringfilter
def fmttranslation(value, language=None):
    if language is None:
        language = Language.objects.get(code = 'en')
    plurals = split_plural(value)
    parts = []
    for idx, value in enumerate(plurals):
        value = escape(force_unicode(value))
        value = re.sub(r'\r\n|\r|\n', '\n', value) # normalize newlines
        paras = re.split('\n', value)
        paras = [fmt_whitespace(p) for p in paras]
        value = '<span class="plural">%s</span><br />' % language.get_plural_label(idx)
        value += '<br />'.join(paras)
        parts.append(value)
    value = '<hr />'.join(parts)
    return mark_safe(value)


@register.filter
@stringfilter
def site_title(value):
    return settings.SITE_TITLE
