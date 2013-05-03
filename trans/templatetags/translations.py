# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from django.utils.translation import ugettext as _, ungettext
from django.utils.formats import date_format
from django.utils import timezone
from django import template
from weblate import appsettings

import re

from datetime import date, datetime

import weblate

from trans.simplediff import html_diff
from trans.util import (
    split_plural, avatar_for_email, get_user_display
)
from lang.models import Language
from trans.models import Project, SubProject, Dictionary
from trans.checks import CHECKS

register = template.Library()

WHITESPACE_RE = re.compile(r'(  +| $|^ )')
NEWLINES_RE = re.compile(r'\r\n|\r|\n')


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


@register.simple_tag
def admin_boolean_icon(val):
    '''
    Admin icon wrapper.
    '''
    icon_url = static('admin/img/icon-%s.gif' %
                      {True: 'yes', False: 'no', None: 'unknown'}[val])
    return mark_safe(u'<img src="%s" alt="%s" />' % (icon_url, val))


@register.inclusion_tag('message.html')
def show_message(tags, message):
    return {
        'tags': tags,
        'message': message,
    }


@register.simple_tag
def avatar(user, size=80):
    url = avatar_for_email(user.email, size)
    alt = escape(_('Avatar for %s') % get_user_display(user, False))
    return """<img src="%s" alt="Avatar for %s" height="%s" width="%s"/>""" % (
        url, alt, size, size
    )


@register.filter
def gitdate(value):
    '''
    Formats timestamp as returned byt GitPython.
    '''
    return date_format(
        datetime.fromtimestamp(value),
        'DATETIME_FORMAT'
    )


@register.filter
def naturaltime(value):
    """
    Heavily based on Django's django.contrib.humanize
    implementation of naturaltime

    For date and time values shows how many seconds, minutes or hours ago
    compared to current timestamp returns representing string.
    """
    # this function is huge
    # pylint: disable=R0911,R0912

    # datetime is a subclass of date
    if not isinstance(value, date):
        return value

    now = timezone.now()
    if value < now:
        delta = now - value
        if delta.days >= 365:
            count = delta.days / 365
            return ungettext(
                'a year ago', '%(count)s years ago', count
            ) % {'count': count}
        elif delta.days >= 30:
            count = delta.days / 30
            return ungettext(
                'a month ago', '%(count)s months ago', count
            ) % {'count': count}
        elif delta.days >= 14:
            count = delta.days / 7
            return ungettext(
                'a week ago', '%(count)s weeks ago', count
            ) % {'count': count}
        elif delta.days > 0:
            return ungettext(
                'yesterday', '%(count)s days ago', delta.days
            ) % {'count': delta.days}
        elif delta.seconds == 0:
            return _('now')
        elif delta.seconds < 60:
            return ungettext(
                'a second ago', '%(count)s seconds ago', delta.seconds
            ) % {'count': delta.seconds}
        elif delta.seconds // 60 < 60:
            count = delta.seconds // 60
            return ungettext(
                'a minute ago', '%(count)s minutes ago', count
            ) % {'count': count}
        else:
            count = delta.seconds // 60 // 60
            return ungettext(
                'an hour ago', '%(count)s hours ago', count
            ) % {'count': count}
    else:
        delta = value - now
        if delta.days >= 365:
            count = delta.days / 365
            return ungettext(
                'a year from now', '%(count)s years from now', count
            ) % {'count': count}
        elif delta.days >= 30:
            count = delta.days / 30
            return ungettext(
                'a month from now', '%(count)s months from now', count
            ) % {'count': count}
        elif delta.days >= 14:
            count = delta.days / 7
            return ungettext(
                'a week from now', '%(count)s weeks from now', count
            ) % {'count': count}
        elif delta.days > 0:
            return ungettext(
                'tomorrow', '%(count)s days from now', delta.days
            ) % {'count': delta.days}
        elif delta.seconds == 0:
            return _('now')
        elif delta.seconds < 60:
            return ungettext(
                'a second from now',
                '%(count)s seconds from now',
                delta.seconds
            ) % {'count': delta.seconds}
        elif delta.seconds // 60 < 60:
            count = delta.seconds // 60
            return ungettext(
                'a minute from now', '%(count)s minutes from now', count
            ) % {'count': count}
        else:
            count = delta.seconds // 60 // 60
            return ungettext(
                'an hour from now', '%(count)s hours from now', count
            ) % {'count': count}
