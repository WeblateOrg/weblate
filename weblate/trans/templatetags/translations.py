#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import re
from datetime import date
from uuid import uuid4

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext
from siphashc import siphash

from weblate.accounts.avatar import get_user_display
from weblate.accounts.models import Profile
from weblate.auth.models import User
from weblate.checks.models import CHECKS
from weblate.checks.utils import highlight_string
from weblate.trans.filter import get_filter_choice
from weblate.trans.models import (
    Announcement,
    Component,
    ContributorAgreement,
    Project,
    Translation,
)
from weblate.trans.models.translation import GhostTranslation
from weblate.trans.simplediff import html_diff
from weblate.trans.util import get_state_css, split_plural
from weblate.utils.docs import get_doc_url
from weblate.utils.hash import hash_to_checksum
from weblate.utils.markdown import render_markdown
from weblate.utils.stats import BaseStats, ProjectLanguageStats

register = template.Library()

HIGHLIGTH_SPACE = '<span class="hlspace">{}</span>{}'
SPACE_TEMPLATE = '<span class="{}"><span class="sr-only">{}</span></span>'
SPACE_SPACE = SPACE_TEMPLATE.format("space-space", " ")
SPACE_NL = HIGHLIGTH_SPACE.format(SPACE_TEMPLATE.format("space-nl", ""), "<br />")
SPACE_TAB = HIGHLIGTH_SPACE.format(SPACE_TEMPLATE.format("space-tab", "\t"), "")

HL_CHECK = (
    '<span class="hlcheck">' '<span class="highlight-number"></span>' "{0}" "</span>"
)

WHITESPACE_RE = re.compile(r"(  +| $|^ )")
NEWLINES_RE = re.compile(r"\r\n|\r|\n")
TYPE_MAPPING = {True: "yes", False: "no", None: "unknown"}
# Mapping of status report flags to names
NAME_MAPPING = {
    True: gettext_lazy("Good configuration"),
    False: gettext_lazy("Bad configuration"),
    None: gettext_lazy("Possible configuration"),
}

FLAG_TEMPLATE = '<span title="{0}" class="{1}">{2}</span>'
BADGE_TEMPLATE = '<span class="badge pull-right flip {1}">{0}</span>'

PERM_TEMPLATE = """
<td>
<input type="checkbox"
    class="set-group"
    data-placement="bottom"
    data-username="{0}"
    data-group="{1}"
    data-name="{2}"
    {3} />
</td>
"""

SOURCE_LINK = """
<a href="{0}" target="_blank" rel="noopener noreferrer"
    class="long-filename" dir="ltr">{1}</a>
"""


def replace_whitespace(match):
    spaces = match.group(1).replace(" ", SPACE_SPACE)
    return HIGHLIGTH_SPACE.format(spaces, "")


def fmt_whitespace(value):
    """Format whitespace so that it is more visible."""
    # Highlight exta whitespace
    value = WHITESPACE_RE.sub(replace_whitespace, value)

    # Highlight tabs
    value = value.replace("\t", SPACE_TAB.format(gettext("Tab character")))

    return value


def fmt_diff(value, diff, idx):
    """Format diff if there is any."""
    if diff is None:
        return escape(value)
    return html_diff(force_str(diff[idx]), value)


def fmt_highlights(raw_value, value, unit):
    """Format check highlights."""
    if unit is None:
        return value
    highlights = highlight_string(raw_value, unit)
    start_search = 0
    for highlight in highlights:
        htext = escape(force_str(highlight[2]))
        find_highlight = value.find(htext, start_search)
        if find_highlight >= 0:
            newpart = HL_CHECK.format(htext)
            next_part = value[(find_highlight + len(htext)) :]
            value = value[:find_highlight] + newpart + next_part
            start_search = find_highlight + len(newpart)
    return value


def fmt_search(value, search_match, match):
    """Format search match."""
    if search_match:
        search_match = escape(search_match)
        if match == "search":
            # Since the search ignored case, we need to highlight any
            # combination of upper and lower case we find.
            return re.sub(
                r"(" + re.escape(search_match) + ")",
                r'<span class="hlmatch">\1</span>',
                value,
                flags=re.IGNORECASE,
            )
        if match in ("replacement", "replaced"):
            return value.replace(
                search_match, '<span class="{0}">{1}</span>'.format(match, search_match)
            )
    return value


@register.inclusion_tag("snippets/format-translation.html")
def format_translation(
    value,
    language,
    plural=None,
    diff=None,
    search_match=None,
    simple=False,
    num_plurals=2,
    unit=None,
    match="search",
):
    """Nicely formats translation text possibly handling plurals or diff."""
    # Split plurals to separate strings
    plurals = split_plural(value)

    if plural is None:
        plural = language.plural

    # Show plurals?
    if int(num_plurals) <= 1:
        plurals = plurals[-1:]

    # Newline concatenator
    newline = SPACE_NL.format(gettext("New line"))

    # Split diff plurals
    if diff is not None:
        diff = split_plural(diff)
        # Previous message did not have to be a plural
        while len(diff) < len(plurals):
            diff.append(diff[0])

    # We will collect part for each plural
    parts = []
    has_content = False

    for idx, raw_value in enumerate(plurals):
        # HTML escape
        value = force_str(raw_value)

        # Content of the Copy to clipboard button
        copy = escape(value)

        # Format diff if there is any
        value = fmt_diff(value, diff, idx)

        # Create span for checks highlights
        value = fmt_highlights(raw_value, value, unit)

        # Format search term
        value = fmt_search(value, search_match, match)

        # Normalize newlines
        value = NEWLINES_RE.sub("\n", value)

        # Split string
        paras = value.split("\n")

        # Format whitespace in each paragraph
        paras = [fmt_whitespace(p) for p in paras]

        # Show label for plural (if there are any)
        title = ""
        if len(plurals) > 1:
            title = plural.get_plural_name(idx)

        # Join paragraphs
        content = mark_safe(newline.join(paras))

        parts.append({"title": title, "content": content, "copy": copy})
        has_content |= bool(content)

    return {
        "simple": simple,
        "items": parts,
        "language": language,
        "unit": unit,
        "has_content": has_content,
    }


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
def documentation(page, anchor=""):
    """Return link to Weblate documentation."""
    return get_doc_url(page, anchor)


@register.inclusion_tag("documentation-icon.html")
def documentation_icon(page, anchor="", right=False):
    return {"right": right, "doc_url": get_doc_url(page, anchor)}


@register.inclusion_tag("documentation-icon.html")
def form_field_doc_link(form, field):
    if hasattr(form, "get_field_doc"):
        return {"right": False, "doc_url": get_doc_url(*form.get_field_doc(field))}
    return {}


@register.inclusion_tag("message.html")
def show_message(tags, message):
    tags = tags.split()
    final = []
    task_id = None
    for tag in tags:
        if tag.startswith("task:"):
            task_id = tag[5:]
        else:
            final.append(tag)
    return {"tags": " ".join(final), "task_id": task_id, "message": message}


def naturaltime_past(value, now):
    """Handling of past dates for naturaltime."""
    # this function is huge
    # pylint: disable=too-many-branches,too-many-return-statements

    delta = now - value

    if delta.days >= 365:
        count = delta.days // 365
        if count == 1:
            return gettext("a year ago")
        return ngettext("%(count)s year ago", "%(count)s years ago", count) % {
            "count": count
        }
    if delta.days >= 30:
        count = delta.days // 30
        if count == 1:
            return gettext("a month ago")
        return ngettext("%(count)s month ago", "%(count)s months ago", count) % {
            "count": count
        }
    if delta.days >= 14:
        count = delta.days // 7
        return ngettext("%(count)s week ago", "%(count)s weeks ago", count) % {
            "count": count
        }
    if delta.days > 0:
        if delta.days == 7:
            return gettext("a week ago")
        if delta.days == 1:
            return gettext("yesterday")
        return ngettext("%(count)s day ago", "%(count)s days ago", delta.days) % {
            "count": delta.days
        }
    if delta.seconds == 0:
        return gettext("now")
    if delta.seconds < 60:
        if delta.seconds == 1:
            return gettext("a second ago")
        return ngettext(
            "%(count)s second ago", "%(count)s seconds ago", delta.seconds
        ) % {"count": delta.seconds}
    if delta.seconds // 60 < 60:
        count = delta.seconds // 60
        if count == 1:
            return gettext("a minute ago")
        return ngettext("%(count)s minute ago", "%(count)s minutes ago", count) % {
            "count": count
        }
    count = delta.seconds // 60 // 60
    if count == 1:
        return gettext("an hour ago")
    return ngettext("%(count)s hour ago", "%(count)s hours ago", count) % {
        "count": count
    }


def naturaltime_future(value, now):
    """Handling of future dates for naturaltime."""
    # this function is huge
    # pylint: disable=too-many-branches,too-many-return-statements

    delta = value - now

    if delta.days >= 365:
        count = delta.days // 365
        if count == 1:
            return gettext("a year from now")
        return ngettext(
            "%(count)s year from now", "%(count)s years from now", count
        ) % {"count": count}
    if delta.days >= 30:
        count = delta.days // 30
        if count == 1:
            return gettext("a month from now")
        return ngettext(
            "%(count)s month from now", "%(count)s months from now", count
        ) % {"count": count}
    if delta.days >= 14:
        count = delta.days // 7
        return ngettext(
            "%(count)s week from now", "%(count)s weeks from now", count
        ) % {"count": count}
    if delta.days > 0:
        if delta.days == 1:
            return gettext("tomorrow")
        if delta.days == 7:
            return gettext("a week from now")
        return ngettext(
            "%(count)s day from now", "%(count)s days from now", delta.days
        ) % {"count": delta.days}
    if delta.seconds == 0:
        return gettext("now")
    if delta.seconds < 60:
        if delta.seconds == 1:
            return gettext("a second from now")
        return ngettext(
            "%(count)s second from now", "%(count)s seconds from now", delta.seconds
        ) % {"count": delta.seconds}
    if delta.seconds // 60 < 60:
        count = delta.seconds // 60
        if count == 1:
            return gettext("a minute from now")
        return ngettext(
            "%(count)s minute from now", "%(count)s minutes from now", count
        ) % {"count": count}
    count = delta.seconds // 60 // 60
    if count == 1:
        return gettext("an hour from now")
    return ngettext("%(count)s hour from now", "%(count)s hours from now", count) % {
        "count": count
    }


@register.filter
def naturaltime(value, now=None):
    """Heavily based on Django's django.contrib.humanize implementation of naturaltime.

    For date and time values shows how many seconds, minutes or hours ago compared to
    current timestamp returns representing string.
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
            escape(value.replace(microsecond=0).isoformat()), escape(text)
        )
    )


def translation_progress_data(approved, translated, fuzzy, checks):
    return {
        "approved": "{0:.1f}".format(approved),
        "good": "{0:.1f}".format(max(translated - checks - approved, 0)),
        "checks": "{0:.1f}".format(checks),
        "fuzzy": "{0:.1f}".format(fuzzy),
        "percent": "{0:.1f}".format(translated),
    }


def get_stats_parent(obj, parent):
    if not isinstance(obj, BaseStats):
        obj = obj.stats
    if parent is None:
        return obj
    return obj.get_parent_stats(parent)


@register.simple_tag
def global_stats(obj, stats, parent):
    """Return attribute from global stats."""
    if not parent:
        return None
    if isinstance(parent, str):
        parent = getattr(obj, parent)
    return get_stats_parent(stats, parent)


@register.simple_tag
def get_stats(obj, attr):
    if not attr:
        attr = "stats"
    return getattr(obj, attr)


@register.inclusion_tag("progress.html")
def translation_progress(obj, parent=None):
    stats = get_stats_parent(obj, parent)
    return translation_progress_data(
        stats.approved_percent,
        stats.translated_percent,
        stats.fuzzy_percent,
        stats.translated_checks_percent,
    )


@register.inclusion_tag("progress.html")
def words_progress(obj, parent=None):
    stats = get_stats_parent(obj, parent)
    return translation_progress_data(
        stats.approved_words_percent,
        stats.translated_words_percent,
        stats.fuzzy_words_percent,
        stats.translated_checks_words_percent,
    )


@register.simple_tag
def get_state_badge(unit):
    """Return state badge."""
    flag = None

    if unit.fuzzy:
        flag = (pgettext("String state", "Needs editing"), "text-danger")
    elif not unit.translated:
        flag = (pgettext("String state", "Not translated"), "text-danger")
    elif unit.approved:
        flag = (pgettext("String state", "Approved"), "text-success")
    elif unit.translated:
        flag = (pgettext("String state", "Translated"), "text-primary")

    if flag is None:
        return ""

    return mark_safe(BADGE_TEMPLATE.format(*flag))


@register.inclusion_tag("snippets/unit-state.html")
def get_state_flags(unit, detail=False):
    """Return state flags."""
    return {
        "state": " ".join(get_state_css(unit)),
        "unit": unit,
        "detail": detail,
    }


@register.simple_tag
def get_location_links(profile, unit):
    """Generate links to source files where translation was used."""
    ret = []

    # Do we have any locations?
    if not unit.location:
        return ""

    # Is it just an ID?
    if unit.location.isdigit():
        return gettext("string ID %s") % unit.location

    # Go through all locations separated by comma
    for location, filename, line in unit.get_locations():
        link = unit.translation.component.get_repoweb_link(
            filename, line, profile.editor_link
        )
        if link is None:
            ret.append(escape(location))
        else:
            ret.append(SOURCE_LINK.format(escape(link), escape(location)))
    return mark_safe("\n".join(ret))


@register.simple_tag(takes_context=True)
def announcements(context, project=None, component=None, language=None):
    """Display announcement messages for given context."""
    ret = []

    user = context["user"]

    for announcement in Announcement.objects.context_filter(
        project, component, language
    ):
        can_delete = user.has_perm(
            "component.edit", announcement.component
        ) or user.has_perm("project.edit", announcement.project)

        ret.append(
            render_to_string(
                "message.html",
                {
                    "tags": " ".join((announcement.category, "announcement")),
                    "message": render_markdown(announcement.message),
                    "announcement": announcement,
                    "can_delete": can_delete,
                },
            )
        )

    return mark_safe("\n".join(ret))


@register.simple_tag(takes_context=True)
def active_tab(context, slug):
    active = "active" if slug == context["active_tab_slug"] else ""
    return mark_safe('class="tab-pane {0}" id="{1}"'.format(active, slug))


@register.simple_tag(takes_context=True)
def active_link(context, slug):
    if slug == context["active_tab_slug"]:
        return mark_safe('class="active"')
    return ""


@register.simple_tag
def user_permissions(user, groups):
    """Render checksboxes for user permissions."""
    result = []
    for group in groups:
        checked = ""
        if user.groups.filter(pk=group.pk).exists():
            checked = ' checked="checked"'
        result.append(
            PERM_TEMPLATE.format(
                escape(user.username), group.pk, escape(group.short_name), checked
            )
        )
    return mark_safe("".join(result))


@register.simple_tag(takes_context=True)
def show_contributor_agreement(context, component):
    if not component.agreement:
        return ""
    if ContributorAgreement.objects.has_agreed(context["user"], component):
        return ""

    return render_to_string(
        "show-contributor-agreement.html",
        {"object": component, "next": context["request"].get_full_path()},
    )


@register.simple_tag(takes_context=True)
def get_translate_url(context, obj):
    """Get translate URL based on user preference."""
    if not isinstance(obj, Translation):
        return ""
    if context["user"].profile.translate_mode == Profile.TRANSLATE_ZEN:
        name = "zen"
    else:
        name = "translate"
    return reverse(name, kwargs=obj.get_reverse_url_kwargs())


@register.simple_tag(takes_context=True)
def get_browse_url(context, obj):
    """Get translate URL based on user preference."""
    # Project listing on language page
    if "language" in context and isinstance(obj, Project):
        return reverse(
            "project-language",
            kwargs={"lang": context["language"].code, "project": obj.slug},
        )

    # Language listing on porject page
    if isinstance(obj, ProjectLanguageStats):
        return reverse(
            "project-language",
            kwargs={"lang": obj.language.code, "project": obj.obj.slug},
        )

    return obj.get_absolute_url()


@register.simple_tag(takes_context=True)
def init_unique_row_id(context):
    context["row_uuid"] = uuid4().hex
    return ""


@register.simple_tag(takes_context=True)
def get_unique_row_id(context, obj):
    """Get unique row ID for multiline tables."""
    return "{}-{}".format(context["row_uuid"], obj.pk)


@register.simple_tag
def get_filter_name(name):
    names = dict(get_filter_choice())
    return names[name]


@register.inclusion_tag("trans/embed-alert.html", takes_context=True)
def indicate_alerts(context, obj):
    result = []

    translation = None
    component = None
    project = None

    if isinstance(obj, (Translation, GhostTranslation)):
        translation = obj
        component = obj.component
        project = component.project
    elif isinstance(obj, Component):
        component = obj
        project = component.project
    elif isinstance(obj, Project):
        project = obj

    if context["user"].has_perm("project.edit", project):
        result.append(
            ("state/admin.svg", gettext("You administrate this project."), None)
        )

    if translation:
        if translation.is_source:
            result.append(
                (
                    "state/source.svg",
                    gettext("This translation is used for source strings."),
                    None,
                )
            )

    if component:
        project = component.project

        if component.is_repo_link:
            result.append(
                (
                    "state/link.svg",
                    gettext("This component is linked to the %(target)s repository.")
                    % {"target": component.linked_component},
                    None,
                )
            )

        if component.all_alerts.exists():
            result.append(
                (
                    "state/alert.svg",
                    gettext("Fix this component to clear its alerts."),
                    component.get_absolute_url() + "#alerts",
                )
            )

        if component.locked:
            result.append(
                ("state/lock.svg", gettext("This translation is locked."), None)
            )

        if component.in_progress():
            result.append(
                (
                    "state/update.svg",
                    gettext("Updating translation component…"),
                    reverse(
                        "component_progress", kwargs=component.get_reverse_url_kwargs()
                    )
                    + "?info=1",
                )
            )
    elif project:
        if project.has_alerts:
            result.append(
                (
                    "state/alert.svg",
                    gettext("Some of the components within this project have alerts."),
                    None,
                )
            )

        if project.locked:
            result.append(
                ("state/lock.svg", gettext("This translation is locked."), None)
            )
    if getattr(obj, "is_ghost", False):
        result.append(
            ("state/ghost.svg", gettext("This translation does not yet exist."), None)
        )

    return {"icons": result, "component": component, "project": project}


@register.filter
def replace_english(value, language):
    return value.replace("English", force_str(language))


@register.filter
def markdown(text):
    return render_markdown(text)


@register.filter
def choiceval(boundfield):
    """Get literal value from field's choices.

    Empty value is returned if value is not selected or invalid.
    """
    value = boundfield.value()
    if value is None:
        return ""
    if value is True:
        return gettext("enabled")
    if not hasattr(boundfield.field, "choices"):
        return value
    choices = list(boundfield.field.choices)
    if choices and hasattr(choices[0][0], "value"):
        # Django 3.1+ yields ModelChoiceIteratorValue
        choices = {choice.value: value for choice, value in choices}
    else:
        # Django 3.0
        choices = dict(choices)
    if isinstance(value, list):
        return ", ".join(choices.get(val, val) for val in value)
    return choices.get(value, value)


@register.filter
def format_commit_author(commit):
    users = User.objects.filter(
        social_auth__verifiedemail__email=commit["author_email"]
    ).distinct()
    if len(users) == 1:
        return get_user_display(users[0], True, True)
    return commit["author_name"]


@register.filter
def percent_format(number):
    return pgettext("Translated percents", "%(percent)s%%") % {
        "percent": intcomma(int(number))
    }


@register.filter
def hash_text(name):
    """Hash text for use in HTML id."""
    return hash_to_checksum(siphash("Weblate URL hash", name.encode()))
