# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import re

from datetime import date

from django.utils.html import escape, urlize
from django.templatetags.static import static
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.encoding import force_text
from django.utils.translation import ugettext as _, ungettext, ugettext_lazy
from django.utils import timezone
from django import template

from weblate.accounts.models import Profile
from weblate.trans.simplediff import html_diff
from weblate.trans.util import split_plural
from weblate.lang.models import Language
from weblate.trans.models import (
    Project, Component, Dictionary, WhiteboardMessage, Unit,
    ContributorAgreement, Translation,
)
from weblate.checks import CHECKS, highlight_string
from weblate.trans.filter import get_filter_choice
from weblate.utils.docs import get_doc_url
from weblate.utils.stats import BaseStats

register = template.Library()

HIGHLIGTH_SPACE = '<span class="hlspace">{}</span>{}'
SPACE_TEMPLATE = '<span class="{}"><span class="sr-only">{}</span></span>'
SPACE_SPACE = SPACE_TEMPLATE.format('space-space', ' ')
SPACE_NL = HIGHLIGTH_SPACE.format(
    SPACE_TEMPLATE.format('space-nl', ''), '<br />'
)
SPACE_TAB = HIGHLIGTH_SPACE.format(
    SPACE_TEMPLATE.format('space-tab', '\t'), ''
)

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
BADGE_TEMPLATE = '<span class="badge pull-right flip {1}">{0}</span>'

PERM_TEMPLATE = '''
<td>
<input type="checkbox"
    class="set-group"
    data-placement="bottom"
    data-username="{0}"
    data-group="{1}"
    data-name="{2}"
    {3} />
</td>
'''

SOURCE_LINK = '''
<a href="{0}" target="_blank" rel="noopener noreferrer">{1}
<i class="fa fa-external-link"></i></a>
'''


def replace_whitespace(match):
    spaces = match.group(1).replace(' ', SPACE_SPACE)
    return HIGHLIGTH_SPACE.format(spaces, '')


def fmt_whitespace(value):
    """Format whitespace so that it is more visible."""
    # Highlight exta whitespace
    value = WHITESPACE_RE.sub(replace_whitespace, value)

    # Highlight tabs
    value = value.replace('\t', SPACE_TAB.format(_('Tab character')))

    return value


def fmt_diff(value, diff, idx):
    """Format diff if there is any"""
    if diff is None:
        return value
    diffvalue = escape(force_text(diff[idx]))
    return html_diff(diffvalue, value)


def fmt_highlights(raw_value, value, unit):
    """Format check highlights"""
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


def fmt_search(value, search_match, match):
    """Format search match"""
    if search_match:
        search_match = escape(search_match)
        if match == 'search':
            # Since the search ignored case, we need to highlight any
            # combination of upper and lower case we find.
            return re.sub(
                r'(' + re.escape(search_match) + ')',
                r'<span class="hlmatch">\1</span>',
                value,
                flags=re.IGNORECASE
            )
        elif match in ('replacement', 'replaced'):
            return value.replace(
                search_match,
                '<span class="{0}">{1}</span>'.format(
                    match, search_match
                )
            )
    return value


@register.inclusion_tag('format-translation.html')
def format_translation(value, language, plural=None, diff=None,
                       search_match=None, simple=False, num_plurals=2,
                       unit=None, match='search'):
    """Nicely formats translation text possibly handling plurals or diff."""
    # Split plurals to separate strings
    plurals = split_plural(value)

    if plural is None:
        plural = language.plural

    # Show plurals?
    if int(num_plurals) <= 1:
        plurals = plurals[-1:]

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
        value = fmt_search(value, search_match, match)

        # Normalize newlines
        value = NEWLINES_RE.sub('\n', value)

        # Split string
        paras = value.split('\n')

        # Format whitespace in each paragraph
        paras = [fmt_whitespace(p) for p in paras]

        # Show label for plural (if there are any)
        title = ''
        if len(plurals) > 1:
            title = plural.get_plural_name(idx)

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
    """Return check severity, or its id if check is not known."""
    try:
        return escape(CHECKS[check].severity)
    except KeyError:
        return 'info'


@register.simple_tag
def check_name(check):
    """Return check name, or its id if check is not known."""
    try:
        return escape(CHECKS[check].name)
    except KeyError:
        return escape(check)


@register.simple_tag
def check_description(check):
    """Return check description, or its id if check is not known."""
    try:
        return escape(CHECKS[check].description)
    except KeyError:
        return escape(check)


@register.simple_tag
def project_name(prj):
    """Get project name based on slug."""
    return escape(force_text(Project.objects.get(slug=prj)))


@register.simple_tag
def component_name(prj, subprj):
    """Get component name based on slug."""
    return escape(
        force_text(Component.objects.get(project__slug=prj, slug=subprj))
    )


@register.simple_tag
def language_name(code):
    """Get language name based on its code."""
    return escape(force_text(Language.objects.get(code=code)))


@register.simple_tag
def dictionary_count(lang, project):
    """Return number of words in dictionary."""
    return Dictionary.objects.filter(project=project, language=lang).count()


@register.simple_tag
def documentation(page, anchor=''):
    """Return link to Weblate documentation."""
    return get_doc_url(page, anchor)


@register.inclusion_tag('documentation-icon.html')
def documentation_icon(page, anchor='', right=False):
    return {
        'right': right,
        'doc_url': get_doc_url(page, anchor),
    }


@register.simple_tag
def admin_boolean_icon(val):
    """Admin icon wrapper."""
    ext = 'svg'
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
    """Handling of past dates for naturaltime."""

    # this function is huge
    # pylint: disable=too-many-branches,too-many-return-statements

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
    """Handling of future dates for naturaltime."""

    # this function is huge
    # pylint: disable=too-many-branches,too-many-return-statements

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
        text = naturaltime_past(value, now)
    else:
        text = naturaltime_future(value, now)
    return mark_safe(
        '<span title="{0}">{1}</span>'.format(
            escape(value.replace(microsecond=0).isoformat()),
            escape(text)
        )
    )


def translation_progress_data(approved, translated, fuzzy, checks):
    return {
        'approved': '{0:.1f}'.format(approved),
        'good': '{0:.1f}'.format(translated - checks - approved),
        'checks': '{0:.1f}'.format(checks),
        'fuzzy': '{0:.1f}'.format(fuzzy),
        'percent': '{0:.1f}'.format(translated),
    }


def get_stats(obj):
    if isinstance(obj, BaseStats):
        return obj
    return obj.stats


@register.inclusion_tag('progress.html')
def translation_progress(obj):
    stats = get_stats(obj)
    return translation_progress_data(
        stats.approved_percent,
        stats.translated_percent,
        stats.fuzzy_percent,
        stats.allchecks_percent,
    )


@register.inclusion_tag('progress.html')
def words_progress(obj):
    stats = get_stats(obj)
    return translation_progress_data(
        stats.approved_words_percent,
        stats.translated_words_percent,
        stats.fuzzy_words_percent,
        stats.allchecks_words_percent,
    )


@register.simple_tag
def get_state_badge(unit):
    """Return state badge."""
    flag = None

    if unit.fuzzy:
        flag = (
            _('Needs editing'),
            'text-danger'
        )
    elif not unit.translated:
        flag = (
            _('Not translated'),
            'text-danger'
        )
    elif unit.approved:
        flag = (
            _('Approved'),
            'text-success'
        )
    elif unit.translated:
        flag = (
            _('Translated'),
            'text-primary'
        )

    if flag is None:
        return ''

    return mark_safe(BADGE_TEMPLATE.format(*flag))


@register.simple_tag
def get_state_flags(unit):
    """Return state flags."""
    flags = []

    if unit.fuzzy:
        flags.append((
            _('Message needs edit'),
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
    elif unit.approved:
        flags.append((
            _('Message is approved'),
            'check-circle text-success'
        ))
    elif unit.translated:
        flags.append((
            _('Message is translated'),
            'check-circle text-primary'
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
def get_location_links(profile, unit):
    """Generate links to source files where translation was used."""
    ret = []

    # Do we have any locations?
    if not unit.location:
        return ''

    # Is it just an ID?
    if unit.location.isdigit():
        return _('string ID %s') % unit.location

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
        if profile.editor_link:
            link = profile.editor_link % {
                'file': filename,
                'line': line,
                'branch': unit.translation.component.branch
            }
        else:
            link = unit.translation.component.get_repoweb_link(filename, line)
        location = location.replace('/', '/\u200B')
        if link is None:
            ret.append(escape(location))
        else:
            ret.append(SOURCE_LINK.format(escape(link), escape(location)))
    return mark_safe('\n'.join(ret))


@register.simple_tag
def whiteboard_messages(project=None, component=None, language=None):
    """Display whiteboard messages for given context"""
    ret = []

    whiteboards = WhiteboardMessage.objects.context_filter(
        project, component, language
    )

    for whiteboard in whiteboards:
        if whiteboard.message_html:
            content = mark_safe(whiteboard.message)
        else:
            content = mark_safe(urlize(whiteboard.message, autoescape=True))

        ret.append(
            render_to_string(
                'message.html',
                {
                    'tags': ' '.join((whiteboard.category, 'whiteboard')),
                    'message':  content,
                }
            )
        )

    return mark_safe('\n'.join(ret))


@register.simple_tag(takes_context=True)
def active_tab(context, slug):
    active = "active" if slug == context['active_tab_slug'] else ""
    return mark_safe('class="tab-pane {0}" id="{1}"'.format(active, slug))


@register.simple_tag(takes_context=True)
def active_link(context, slug):
    if slug == context['active_tab_slug']:
        return mark_safe('class="active"')
    return ''


@register.simple_tag
def matching_cotentsum(item):
    """Find matching objects to suggestion, comment or check"""
    return Unit.objects.prefetch().filter(
        translation__component__project=item.project,
        translation__language=item.language,
        content_hash=item.content_hash,
    )


@register.simple_tag
def user_permissions(user, groups):
    """Render checksboxes for user permissions."""
    result = []
    for group in groups:
        checked = ''
        if user.groups.filter(pk=group.pk).exists():
            checked = ' checked="checked"'
        result.append(
            PERM_TEMPLATE.format(
                escape(user.username),
                group.pk,
                escape(group.short_name),
                checked
            )
        )
    return mark_safe(''.join(result))


@register.simple_tag(takes_context=True)
def show_contributor_agreement(context, component):
    if not component.agreement:
        return ''
    if ContributorAgreement.objects.has_agreed(context['user'], component):
        return ''

    return render_to_string(
        'show-contributor-agreement.html',
        {
            'object': component,
            'next': context['request'].get_full_path(),
        }
    )


@register.simple_tag(takes_context=True)
def get_translate_url(context, translation):
    """Get translate URL based on user preference."""
    if not isinstance(translation, Translation):
        return ''
    if context['user'].profile.translate_mode == Profile.TRANSLATE_ZEN:
        name = 'zen'
    else:
        name = 'translate'
    return reverse(name, kwargs=translation.get_reverse_url_kwargs())


@register.simple_tag
def get_filter_name(name):
    names = dict(get_filter_choice(True))
    return names[name]
