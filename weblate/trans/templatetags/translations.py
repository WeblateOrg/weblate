# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.template.defaultfilters import stringfilter
from django.utils.html import escape
from django.contrib.admin.templatetags.admin_static import static
from django.utils.safestring import mark_safe
from django.utils.encoding import force_unicode
from django.utils.translation import ugettext as _, ungettext, ugettext_lazy
from django.utils.formats import date_format
from django.utils import timezone
from django import template
from weblate import appsettings

import re

from datetime import date, datetime

import weblate

from weblate.trans.simplediff import html_diff
from weblate.trans.util import split_plural
from weblate.lang.models import Language
from weblate.trans.models import Project, SubProject, Dictionary, Advertisement
from weblate.trans.checks import CHECKS

register = template.Library()

WHITESPACE_RE = re.compile(r'(  +| $|^ )')
NEWLINES_RE = re.compile(r'\r\n|\r|\n')
TYPE_MAPPING = {
    True: 'yes',
    False: 'no',
    None: 'unknown'
}
# Mapping of status report flags to names
NAME_MAPPING = {
    True: ugettext_lazy('Good configuration'),
    False: ugettext_lazy('Bad configuration'),
    None: ugettext_lazy('Possible configuration')
}


def fmt_whitespace(value):
    '''
    Formats whitespace so that it is more visible.
    '''
    # Highlight exta whitespace
    value = WHITESPACE_RE.sub(
        '<span class="hlspace">\\1</span>',
        value
    )
    # Highlight tabs
    value = value.replace(
        '\t',
        u'<span class="hlspace space-tab" title="%s">→</span>' % (
            _('Tab character')
        )
    )
    return value


@register.filter
@stringfilter
def fmttranslation(value, language=None, diff=None, search_match=None):
    '''
    Formats translation to show whitespace, plural forms or diff.
    '''
    # Get language
    if language is None:
        language = Language.objects.get_default()

    # Split plurals to separate strings
    plurals = split_plural(value)

    # Split diff plurals
    if diff is not None:
        diff = split_plural(diff)
        # Previous message did not have to be a plural
        while len(diff) < len(plurals):
            diff.append(diff[0])

    # We will collect part for each plural
    parts = []

    for idx, value in enumerate(plurals):

        # HTML escape
        value = escape(force_unicode(value))

        # Format diff if there is any
        if diff is not None:
            diffvalue = escape(force_unicode(diff[idx]))
            value = html_diff(diffvalue, value)

        # Format search term
        if search_match is not None:
            # Since the search ignored case, we need to highlight any
            # combination of upper and lower case we find. This is too
            # advanced for str.replace().
            caseless = re.compile(re.escape(search_match), re.IGNORECASE)
            for variation in re.findall(caseless, value):
                value = re.sub(
                    caseless,
                    '<span class="hlmatch">%s</span>' % (variation),
                    value,
                )

        # Normalize newlines
        value = NEWLINES_RE.sub('\n', value)

        # Split string
        paras = value.split('\n')

        # Format whitespace in each paragraph
        paras = [fmt_whitespace(p) for p in paras]

        # Show label for plural (if there are any)
        if len(plurals) > 1:
            value = '<span class="pluraltxt">%s</span><br />' % (
                language.get_plural_label(idx)
            )
        else:
            value = ''

        # Join paragraphs
        newline = u'<span class="hlspace" title="%s">↵</span><br />' % (
            _('New line')
        )
        value += newline.join(paras)

        parts.append(value)

    value = '<hr />'.join(parts)

    return mark_safe(
        '<span lang="%s" dir="%s" class="direction">%s</span>' %
        (language.code, language.direction, value)
    )


@register.filter
@stringfilter
def fmttranslationdiff(value, other):
    '''
    Formats diff between two translations.
    '''
    return fmttranslation(value, other.translation.language, other.target)


@register.filter
@stringfilter
def fmtsearchmatch(value, term):
    '''
    Formats terms matching a search query.
    '''
    return fmttranslation(value, search_match=term)


@register.filter
@stringfilter
def fmtsourcediff(value, other):
    '''
    Formats diff between two sources.
    '''
    return fmttranslation(other.source, diff=value)


@register.filter
@stringfilter
def site_title(value):
    '''
    Returns site title
    '''
    return appsettings.SITE_TITLE


@register.simple_tag
def check_name(check):
    '''
    Returns check name, or it's id if check is not known.
    '''
    try:
        return CHECKS[check].name
    except:
        return check


@register.simple_tag
def check_description(check):
    '''
    Returns check description, or it's id if check is not known.
    '''
    try:
        return CHECKS[check].description
    except:
        return check


@register.simple_tag
def project_name(prj):
    '''
    Gets project name based on slug.
    '''
    return Project.objects.get(slug=prj).__unicode__()


@register.simple_tag
def subproject_name(prj, subprj):
    '''
    Gets subproject name based on slug.
    '''
    return SubProject.objects.get(project__slug=prj, slug=subprj).__unicode__()


@register.simple_tag
def language_name(code):
    '''
    Gets language name based on it's code.
    '''
    return Language.objects.get(code=code).__unicode__()


@register.simple_tag
def dictionary_count(lang, project):
    '''
    Returns number of words in dictionary.
    '''
    return Dictionary.objects.filter(project=project, language=lang).count()


@register.simple_tag
def documentation(page, anchor=''):
    '''
    Returns link to Weblate documentation.
    '''
    return weblate.get_doc_url(page, anchor)


@register.assignment_tag
def doc_url(page, anchor=''):
    '''
    Returns link to Weblate documentation.
    '''
    return weblate.get_doc_url(page, anchor)


@register.simple_tag
def admin_boolean_icon(val):
    '''
    Admin icon wrapper.
    '''
    icon_url = static('admin/img/icon-%s.gif' % TYPE_MAPPING[val])
    return mark_safe(
        u'<img src="{url}" alt="{text}" title="{text}" />'.format(
            url=icon_url,
            text=NAME_MAPPING[val],
        )
    )


@register.inclusion_tag('message.html')
def show_message(tags, message):
    return {
        'tags': tags,
        'message': message,
    }


@register.inclusion_tag('list-checks.html')
def show_checks(checks, user):
    return {
        'checks': checks,
        'perms_ignore_check': user.has_perm('trans.ignore_check'),
    }


@register.filter
def gitdate(value):
    '''
    Formats timestamp as returned byt GitPython.
    '''
    return date_format(
        datetime.fromtimestamp(value),
        'DATETIME_FORMAT'
    )


def naturaltime_past(value, now):
    """
    Handling of past dates for naturaltime.
    """

    # this function is huge
    # pylint: disable=R0911,R0912

    delta = now - value

    if delta.days >= 365:
        count = delta.days / 365
        if count == 1:
            return _('a year ago')
        return ungettext(
            '%(count)s year ago', '%(count)s years ago', count
        ) % {'count': count}
    elif delta.days >= 30:
        count = delta.days / 30
        if count == 1:
            return _('a month ago')
        return ungettext(
            '%(count)s month ago', '%(count)s months ago', count
        ) % {'count': count}
    elif delta.days >= 14:
        count = delta.days / 7
        return ungettext(
            '%(count)s week ago', '%(count)s weeks ago', count
        ) % {'count': count}
    elif delta.days > 0:
        if delta.days == 7:
            return _('a week ago')
        if delta.days == 1:
            return _('yesterday')
        return ungettext(
            '%(count)s day ago', '%(count)s days ago', delta.days
        ) % {'count': delta.days}
    elif delta.seconds == 0:
        return _('now')
    elif delta.seconds < 60:
        if delta.seconds == 1:
            return _('a second ago')
        return ungettext(
            '%(count)s second ago', '%(count)s seconds ago', delta.seconds
        ) % {'count': delta.seconds}
    elif delta.seconds // 60 < 60:
        count = delta.seconds // 60
        if count == 1:
            return _('a minute ago')
        return ungettext(
            '%(count)s minute ago', '%(count)s minutes ago', count
        ) % {'count': count}
    else:
        count = delta.seconds // 60 // 60
        if count == 1:
            return _('an hour ago')
        return ungettext(
            '%(count)s hour ago', '%(count)s hours ago', count
        ) % {'count': count}


def naturaltime_future(value, now):
    """
    Handling of future dates for naturaltime.
    """

    # this function is huge
    # pylint: disable=R0911,R0912

    delta = value - now

    if delta.days >= 365:
        count = delta.days / 365
        if count == 1:
            return _('a year from now')
        return ungettext(
            '%(count)s year from now', '%(count)s years from now', count
        ) % {'count': count}
    elif delta.days >= 30:
        count = delta.days / 30
        if count == 1:
            return _('a month from now')
        return ungettext(
            '%(count)s month from now', '%(count)s months from now', count
        ) % {'count': count}
    elif delta.days >= 14:
        count = delta.days / 7
        return ungettext(
            '%(count)s week from now', '%(count)s weeks from now', count
        ) % {'count': count}
    elif delta.days > 0:
        if delta.days == 1:
            return _('tomorrow')
        if delta.days == 7:
            return _('a week from now')
        return ungettext(
            '%(count)s day from now', '%(count)s days from now', delta.days
        ) % {'count': delta.days}
    elif delta.seconds == 0:
        return _('now')
    elif delta.seconds < 60:
        if delta.seconds == 1:
            return _('a second from now')
        return ungettext(
            '%(count)s second from now',
            '%(count)s seconds from now',
            delta.seconds
        ) % {'count': delta.seconds}
    elif delta.seconds // 60 < 60:
        count = delta.seconds // 60
        if count == 1:
            return _('a minute from now')
        return ungettext(
            '%(count)s minute from now',
            '%(count)s minutes from now',
            count
        ) % {'count': count}
    else:
        count = delta.seconds // 60 // 60
        if count == 1:
            return _('an hour from now')
        return ungettext(
            '%(count)s hour from now', '%(count)s hours from now', count
        ) % {'count': count}


@register.filter
def naturaltime(value, now=None):
    """
    Heavily based on Django's django.contrib.humanize
    implementation of naturaltime

    For date and time values shows how many seconds, minutes or hours ago
    compared to current timestamp returns representing string.
    """
    # datetime is a subclass of date
    if not isinstance(value, date):
        return value

    if now is None:
        now = timezone.now()
    if value < now:
        return naturaltime_past(value, now)
    else:
        return naturaltime_future(value, now)


@register.simple_tag
def get_advertisement_text_mail():
    '''
    Returns advertisement text.
    '''
    advertisement = Advertisement.objects.get_advertisement(
        Advertisement.PLACEMENT_MAIL_TEXT
    )
    if advertisement is None:
        return ''
    return advertisement.text


@register.simple_tag
def get_advertisement_html_mail():
    '''
    Returns advertisement text.
    '''
    advertisement = Advertisement.objects.get_advertisement(
        Advertisement.PLACEMENT_MAIL_HTML
    )
    if advertisement is None:
        return ''
    return mark_safe(advertisement.text)


def translation_progress_data(translated, fuzzy, checks):
    return {
        'good': '{0:f}'.format(translated - checks),
        'checks': '{0:f}'.format(checks),
        'fuzzy': '{0:f}'.format(fuzzy),
        'percent': '{0:f}'.format(translated),
    }


@register.inclusion_tag('progress.html')
def translation_progress(translation):
    translated = translation.get_translated_percent()
    fuzzy = translation.get_fuzzy_percent()
    checks = translation.get_failing_checks_percent()

    return translation_progress_data(translated, fuzzy, checks)


@register.inclusion_tag('progress.html')
def words_progress(translation):
    translated = translation.get_words_percent()
    fuzzy = translation.get_fuzzy_words_percent()
    checks = translation.get_failing_checks_words_percent()

    return translation_progress_data(translated, fuzzy, checks)
