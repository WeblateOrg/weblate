# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
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

from __future__ import unicode_literals

import re

from datetime import date

from django.utils.html import escape, urlize
from django.contrib.admin.templatetags.admin_static import static
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.encoding import force_text
from django.utils.translation import ugettext as _, ungettext, ugettext_lazy
from django.utils import timezone
from django import template
import django

import weblate
from weblate.trans.simplediff import html_diff
from weblate.trans.util import split_plural
from weblate.lang.models import Language
from weblate.trans.models import (
    Project, SubProject, Dictionary, Advertisement, WhiteboardMessage
)
from weblate.trans.checks import CHECKS, highlight_string

register = template.Library()

SPACE_NL = '<span class="hlspace space-nl" title="{0}"></span><br />'
SPACE_TAB = '<span class="hlspace space-tab" title="{0}"></span>'

HL_CHECK = (
    '<span class="hlcheck">{0}'
    '<span class="highlight-number"></span>'
    '</span>'
)

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

FLAG_TEMPLATE = '<i title="{0}" class="fa fa-{1}"></i>'


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
        SPACE_TAB.format(_('Tab character'))
    )
    return value


def fmt_diff(value, diff, idx):
    """Format diff if there is any"""
    if diff is None:
        return value
    diffvalue = escape(force_text(diff[idx]))
    return html_diff(diffvalue, value)


def fmt_highlights(raw_value, value, unit):
    """Formats check highlights"""
    if unit is None:
        return value
    highlights = highlight_string(raw_value, unit)
    start_search = 0
    for highlight in highlights:
        htext = escape(force_text(highlight[2]))
        find_highlight = value.find(htext, start_search)
        if find_highlight >= 0:
            newpart = HL_CHECK.format(htext)
            next_part = value[(find_highlight + len(htext)):]
            value = value[:find_highlight] + newpart + next_part
            start_search = find_highlight + len(newpart)
    return value


def fmt_search(value, search_match):
    """Formats search match"""
    if search_match:
        # Since the search ignored case, we need to highlight any
        # combination of upper and lower case we find. This is too
        # advanced for str.replace().
        caseless = re.compile(re.escape(search_match), re.IGNORECASE)
        for variation in re.findall(caseless, value):
            value = re.sub(
                caseless,
                '<span class="hlmatch">{0}</span>'.format(variation),
                value,
            )
    return value


@register.inclusion_tag('format-translation.html')
def format_translation(value, language, diff=None, search_match=None,
                       simple=False, num_plurals=2, unit=None):
    """
    Nicely formats translation text possibly handling plurals or diff.
    """
    # Split plurals to separate strings
    plurals = split_plural(value)

    # Show plurals?
    if int(num_plurals) <= 1:
        plurals = plurals[:1]

    # Newline concatenator
    newline = SPACE_NL.format(_('New line'))

    # Split diff plurals
    if diff is not None:
        diff = split_plural(diff)
        # Previous message did not have to be a plural
        while len(diff) < len(plurals):
            diff.append(diff[0])

    # We will collect part for each plural
    parts = []

    for idx, raw_value in enumerate(plurals):
        # HTML escape
        value = escape(force_text(raw_value))

        # Format diff if there is any
        value = fmt_diff(value, diff, idx)

        # Create span for checks highlights
        value = fmt_highlights(raw_value, value, unit)

        # Format search term
        value = fmt_search(value, search_match)

        # Normalize newlines
        value = NEWLINES_RE.sub('\n', value)

        # Split string
        paras = value.split('\n')

        # Format whitespace in each paragraph
        paras = [fmt_whitespace(p) for p in paras]

        # Show label for plural (if there are any)
        title = ''
        if len(plurals) > 1:
            title = language.get_plural_label(idx)

        # Join paragraphs
        content = mark_safe(newline.join(paras))

        parts.append({'title': title, 'content': content})

    return {
        'simple': simple,
        'items': parts,
        'language': language,
    }


@register.simple_tag
def check_severity(check):
    '''
    Returns check severity, or its id if check is not known.
    '''
    try:
        return escape(CHECKS[check].severity)
    except KeyError:
        return 'info'


@register.simple_tag
def check_name(check):
    '''
    Returns check name, or its id if check is not known.
    '''
    try:
        return escape(CHECKS[check].name)
    except KeyError:
        return escape(check)


@register.simple_tag
def check_description(check):
    '''
    Returns check description, or its id if check is not known.
    '''
    try:
        return escape(CHECKS[check].description)
    except KeyError:
        return escape(check)


@register.simple_tag
def project_name(prj):
    '''
    Gets project name based on slug.
    '''
    return escape(force_text(Project.objects.get(slug=prj)))


@register.simple_tag
def subproject_name(prj, subprj):
    '''
    Gets subproject name based on slug.
    '''
    return escape(
        force_text(SubProject.objects.get(project__slug=prj, slug=subprj))
    )


@register.simple_tag
def language_name(code):
    '''
    Gets language name based on its code.
    '''
    return escape(force_text(Language.objects.get(code=code)))


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
    if django.VERSION > (1, 9):
        ext = 'svg'
    else:
        ext = 'gif'
    icon_url = static(
        'admin/img/icon-{0}.{1}'.format(TYPE_MAPPING[val], ext)
    )
    return mark_safe(
        '<img src="{url}" alt="{text}" title="{text}" />'.format(
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
def show_checks(project, checks, user):
    return {
        'checks': checks,
        'user': user,
        'project': project,
    }


def naturaltime_past(value, now):
    """
    Handling of past dates for naturaltime.
    """

    # this function is huge
    # pylint: disable=R0911,R0912

    delta = now - value

    if delta.days >= 365:
        count = delta.days // 365
        if count == 1:
            return _('a year ago')
        return ungettext(
            '%(count)s year ago', '%(count)s years ago', count
        ) % {'count': count}
    elif delta.days >= 30:
        count = delta.days // 30
        if count == 1:
            return _('a month ago')
        return ungettext(
            '%(count)s month ago', '%(count)s months ago', count
        ) % {'count': count}
    elif delta.days >= 14:
        count = delta.days // 7
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
        count = delta.days // 365
        if count == 1:
            return _('a year from now')
        return ungettext(
            '%(count)s year from now', '%(count)s years from now', count
        ) % {'count': count}
    elif delta.days >= 30:
        count = delta.days // 30
        if count == 1:
            return _('a month from now')
        return ungettext(
            '%(count)s month from now', '%(count)s months from now', count
        ) % {'count': count}
    elif delta.days >= 14:
        count = delta.days // 7
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
        'good': '{0:.1f}'.format(translated - checks),
        'checks': '{0:.1f}'.format(checks),
        'fuzzy': '{0:.1f}'.format(fuzzy),
        'percent': '{0:.1f}'.format(translated),
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


@register.simple_tag
def get_state_flags(unit):
    """
    Returns state flags.
    """
    flags = []

    if unit.fuzzy:
        flags.append((
            _('Message needs review'),
            'question-circle text-danger'
        ))
    elif not unit.translated:
        flags.append((
            _('Message is not translated'),
            'times-circle text-danger'
        ))
    elif unit.has_failing_check:
        flags.append((
            _('Message has failing checks'),
            'exclamation-circle text-warning'
        ))
    elif unit.translated:
        flags.append((
            _('Message is translated'),
            'check-circle text-success'
        ))

    if unit.has_comment:
        flags.append((
            _('Message has comments'),
            'comment text-info'
        ))

    return mark_safe(
        '\n'.join([FLAG_TEMPLATE.format(*flag) for flag in flags])
    )


@register.simple_tag
def get_location_links(unit):
    """
    Generates links to source files where translation was used.
    """
    ret = []

    # Do we have any locations?
    if len(unit.location) == 0:
        return ''

    # Is it just an ID?
    if unit.location.isdigit():
        return _('unit ID %s') % unit.location

    # Go through all locations separated by comma
    for location in unit.location.split(','):
        location = location.strip()
        if location == '':
            continue
        location_parts = location.split(':')
        if len(location_parts) == 2:
            filename, line = location_parts
        else:
            filename = location_parts[0]
            line = 0
        link = unit.translation.subproject.get_repoweb_link(filename, line)
        if link is None:
            ret.append(escape(location))
        else:
            ret.append(
                '<a href="{0}">{1}</a>'.format(escape(link), escape(location))
            )
    return mark_safe('\n'.join(ret))


@register.simple_tag
def whiteboard_messages(project=None, subproject=None, language=None):
    """Displays whiteboard messages for given context"""
    ret = []

    whiteboards = WhiteboardMessage.objects.context_filter(
        project, subproject, language
    )

    for whiteboard in whiteboards:
        ret.append(
            render_to_string(
                'message.html',
                {
                    'tags': ' '.join((whiteboard.category, 'whiteboard')),
                    'message': mark_safe(
                        urlize(whiteboard.message, autoescape=True)
                    )
                }
            )
        )

    return mark_safe('\n'.join(ret))


@register.simple_tag(takes_context=True)
def active_tab(context, slug):
    active = "active" if slug == context['active_tab_slug'] else ""
    return mark_safe('class="tab-pane %s" id="%s"' % (active, slug))
