from django.template.defaultfilters import stringfilter
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django import template

register = template.Library()

@register.filter
@stringfilter
def fmttranslation(s):
    s = escape(s)
    return mark_safe(s)
