from django.template.defaultfilters import stringfilter
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.encoding import force_unicode
from django import template
from django.conf import settings
from trans.simplediff import htmlDiff
import re

from trans.util import split_plural
from lang.models import Language
from trans.models import Project, SubProject, Dictionary
import trans.checks

register = template.Library()


def fmt_whitespace(value):
    value = re.sub(r'(  +| $|^ )', '<span class="hlspace">\\1</span>', value)
    return value

@register.filter
@stringfilter
def fmttranslation(value, language = None, diff = None):
    if language is None:
        language = Language.objects.get(code = 'en')
    plurals = split_plural(value)
    if diff is not None:
        diff = split_plural(diff)
    parts = []
    for idx, value in enumerate(plurals):
        value = escape(force_unicode(value))
        if diff is not None:
            diffvalue = escape(force_unicode(diff[idx]))
            value = htmlDiff(diffvalue, value)
        value = re.sub(r'\r\n|\r|\n', '\n', value) # normalize newlines
        paras = re.split('\n', value)
        paras = [fmt_whitespace(p) for p in paras]
        if len(plurals) > 1:
            value = '<span class="pluraltxt">%s</span><br />' % language.get_plural_label(idx)
        else:
            value = ''
        value += '<span class="hlspace">\\n</span><br />'.join(paras)
        parts.append(value)
    value = '<hr />'.join(parts)
    return mark_safe(value)

@register.filter
@stringfilter
def fmttranslationdiff(value, other):
    return fmttranslation(value, other.translation.language, other.target)

@register.filter
@stringfilter
def site_title(value):
    return settings.SITE_TITLE

@register.simple_tag
def check_name(check):
    return trans.checks.CHECKS[check].name

@register.simple_tag
def check_description(check):
    return trans.checks.CHECKS[check].description

@register.simple_tag
def project_name(prj):
    return Project.objects.get(slug = prj).__unicode__()

@register.simple_tag
def subproject_name(prj, subprj):
    return SubProject.objects.get(project__slug = prj, slug = subprj).__unicode__()

@register.simple_tag
def language_name(code):
    return Language.objects.get(code = code).__unicode__()

@register.simple_tag
def dictionary_count(lang, project):
    return Dictionary.objects.filter(project = project, language = lang).count()
