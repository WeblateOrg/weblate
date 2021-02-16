#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
from collections import defaultdict
from datetime import date
from uuid import uuid4

from diff_match_patch import diff_match_patch
from django import template
from django.contrib.humanize.templatetags.humanize import intcomma
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext
from siphashc import siphash

from weblate.accounts.avatar import get_user_display
from weblate.accounts.models import Profile
from weblate.auth.models import User
from weblate.checks.models import CHECKS
from weblate.checks.utils import highlight_string
from weblate.trans.filter import FILTERS, get_filter_choice
from weblate.trans.models import (
    Announcement,
    Component,
    ContributorAgreement,
    Project,
    Translation,
)
from weblate.trans.models.translation import GhostTranslation
from weblate.trans.util import get_state_css, split_plural
from weblate.utils.docs import get_doc_url
from weblate.utils.hash import hash_to_checksum
from weblate.utils.markdown import render_markdown
from weblate.utils.messages import get_message_kind as get_message_kind_impl
from weblate.utils.stats import BaseStats, GhostProjectLanguageStats, ProjectLanguage
from weblate.utils.views import SORT_CHOICES

register = template.Library()

HIGHLIGTH_SPACE = '<span class="hlspace">{}</span>{}'
SPACE_TEMPLATE = '<span class="{}"><span class="sr-only">{}</span></span>'
SPACE_SPACE = SPACE_TEMPLATE.format("space-space", " ")
SPACE_NL = HIGHLIGTH_SPACE.format(SPACE_TEMPLATE.format("space-nl", ""), "<br />")

GLOSSARY_TEMPLATE = """<span class="glossary-term" title="{}">"""

WHITESPACE_RE = re.compile(r"(  +| $|^ )")
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
    class="wrap-text" dir="ltr">{1}</a>
"""


class Formatter:
    def __init__(self, idx, value, unit, terms, diff, search_match, match):
        # Inputs
        self.idx = idx
        self.value = value
        self.unit = unit
        self.terms = terms
        self.diff = diff
        self.search_match = search_match
        self.match = match
        # Tags output
        self.tags = [[] for i in range(len(value) + 1)]
        self.dmp = diff_match_patch()

    def parse(self):
        if self.diff:
            self.parse_diff()
        if self.unit:
            self.parse_highlight()
        if self.terms:
            self.parse_glossary()
        if self.search_match:
            self.parse_search()
        self.parse_whitespace()

    def parse_diff(self):
        """Highlights diff, including extra whitespace."""
        dmp = self.dmp
        diff = dmp.diff_main(self.diff[self.idx], self.value)
        dmp.diff_cleanupSemantic(diff)
        offset = 0
        for op, data in diff:
            if op == dmp.DIFF_DELETE:
                self.tags[offset].append(
                    "<del>{}</del>".format(SPACE_SPACE if data == " " else escape(data))
                )
            elif op == dmp.DIFF_INSERT:
                self.tags[offset].append("<ins>")
                if data == " ":
                    # This matches SPACE_SPACE
                    self.tags[offset].append(
                        '<span class="space-space"><span class="sr-only">'
                    )
                offset += len(data)
                if data == " ":
                    self.tags[offset].append("</span></span>")
                self.tags[offset].append("</ins>")
            elif op == dmp.DIFF_EQUAL:
                offset += len(data)

    def parse_highlight(self):
        """Highlights unit placeables."""
        highlights = highlight_string(self.value, self.unit)
        for start, end, _content in highlights:
            self.tags[start].append(
                '<span class="hlcheck"><span class="highlight-number"></span>'
            )
            self.tags[end].append("</span>")

    @staticmethod
    def format_terms(terms):
        forbidden = []
        nontranslatable = []
        translations = []
        for term in terms:
            flags = term.all_flags
            target = escape(term.target)
            if "forbidden" in flags:
                forbidden.append(target)
            elif "read-only" in flags:
                nontranslatable.append(target)
            else:
                translations.append(target)

        output = []
        if forbidden:
            output.append(gettext("Forbidden translation: %s") % ", ".join(forbidden))
        if nontranslatable:
            output.append(gettext("Not-translatable: %s") % ", ".join(nontranslatable))
        if translations:
            output.append(gettext("Glossary translation: %s") % ", ".join(translations))
        return "; ".join(output)

    def parse_glossary(self):
        """Highlights glossary entries."""
        for htext, entries in self.terms.items():
            for match in re.finditer(
                r"\b{}\b".format(re.escape(htext)), self.value, re.IGNORECASE
            ):
                self.tags[match.start()].append(
                    GLOSSARY_TEMPLATE.format(self.format_terms(entries))
                )
                self.tags[match.end()].append("</span>")

    def parse_search(self):
        """Highlights search matches."""
        tag = self.match
        if self.match == "search":
            tag = "hlmatch"

        start_tag = f'<span class="{tag}">'
        end_tag = "</span>"

        for match in re.finditer(
            re.escape(self.search_match), self.value, flags=re.IGNORECASE
        ):
            self.tags[match.start()].append(start_tag)
            self.tags[match.end()].append(end_tag)

    def parse_whitespace(self):
        """Highlight whitespaces."""
        for match in WHITESPACE_RE.finditer(self.value):
            self.tags[match.start()].append(
                '<span class="hlspace"><span class="space-space"><span class="sr-only">'
            )
            self.tags[match.end()].append("</span></span></span>")

        for match in re.finditer("\t", self.value):
            self.tags[match.start()].append(
                '<span class="hlspace"><span class="space-tab"><span class="sr-only">'
            )
            self.tags[match.end()].append("</span></span></span>")

    def format(self):
        tags = self.tags
        value = self.value
        newline = SPACE_NL.format(gettext("New line"))
        output = []
        was_cr = False
        newlines = {"\r", "\n"}
        for pos, char in enumerate(value):
            output.append("".join(tags[pos]))
            if char in newlines:
                is_cr = char == "\r"
                if was_cr and not is_cr:
                    # treat "\r\n" as single newline
                    continue
                was_cr = is_cr
                output.append(newline)
            else:
                output.append(escape(char))
        # Trailing tags
        output.append("".join(tags[len(value)]))
        return mark_safe("".join(output))


@register.inclusion_tag("snippets/format-translation.html")
def format_translation(
    value,
    language,
    plural=None,
    diff=None,
    search_match=None,
    simple=False,
    wrap=False,
    num_plurals=2,
    unit=None,
    match="search",
    glossary=None,
):
    """Nicely formats translation text possibly handling plurals or diff."""
    # Split plurals to separate strings
    plurals = split_plural(value)

    if plural is None:
        plural = language.plural

    # Show plurals?
    if int(num_plurals) <= 1:
        plurals = plurals[-1:]

    # Split diff plurals
    if diff is not None:
        diff = split_plural(diff)
        # Previous message did not have to be a plural
        while len(diff) < len(plurals):
            diff.append(diff[0])

    terms = defaultdict(list)
    for term in glossary or []:
        terms[term.source].append(term)

    # We will collect part for each plural
    parts = []
    has_content = False

    for idx, value in enumerate(plurals):
        formatter = Formatter(idx, value, unit, terms, diff, search_match, match)
        formatter.parse()

        # Show label for plural (if there are any)
        title = ""
        if len(plurals) > 1:
            title = plural.get_plural_name(idx)

        # Join paragraphs
        content = formatter.format()

        parts.append({"title": title, "content": content, "copy": escape(value)})
        has_content |= bool(content)

    return {
        "simple": simple,
        "wrap": wrap,
        "items": parts,
        "language": language,
        "unit": unit,
        "has_content": has_content,
    }


@register.simple_tag
def search_name(query):
    """Returns name for a query string."""
    return FILTERS.get_search_name(query)


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


@register.simple_tag(takes_context=True)
def documentation(context, page, anchor=""):
    """Return link to Weblate documentation."""
    # User might not be present on error pages
    user = context.get("user")
    # Use object method get_doc_url if present
    if hasattr(page, "get_doc_url"):
        return page.get_doc_url(user=user)
    return get_doc_url(page, anchor, user=user)


@register.inclusion_tag("documentation-icon.html", takes_context=True)
def documentation_icon(context, page, anchor="", right=False):
    return {"right": right, "doc_url": documentation(context, page, anchor)}


@register.inclusion_tag("documentation-icon.html", takes_context=True)
def form_field_doc_link(context, form, field):
    if hasattr(form, "get_field_doc"):
        return {
            "right": False,
            "doc_url": get_doc_url(*form.get_field_doc(field), user=context["user"]),
        }
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
        '<span title="{}">{}</span>'.format(
            escape(value.replace(microsecond=0).isoformat()), escape(text)
        )
    )


def get_stats(obj):
    if isinstance(obj, BaseStats):
        return obj
    return obj.stats


def translation_progress_data(readonly, approved, translated, fuzzy, checks):
    return {
        "readonly": f"{readonly:.1f}",
        "approved": f"{approved:.1f}",
        "good": "{:.1f}".format(max(translated - checks - approved - readonly, 0)),
        "checks": f"{checks:.1f}",
        "fuzzy": f"{fuzzy:.1f}",
        "percent": f"{translated:.1f}",
    }


@register.inclusion_tag("progress.html")
def translation_progress(obj):
    stats = get_stats(obj)
    return translation_progress_data(
        stats.readonly_percent,
        stats.approved_percent,
        stats.translated_percent,
        stats.fuzzy_percent,
        stats.translated_checks_percent,
    )


@register.inclusion_tag("progress.html")
def words_progress(obj):
    stats = get_stats(obj)
    return translation_progress_data(
        stats.readonly_words_percent,
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

    # Fallback to source unit if it has more information
    if not unit.location and unit.source_unit.location:
        unit = unit.source_unit

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
        ret.append(
            render_to_string(
                "message.html",
                {
                    "tags": " ".join((announcement.category, "announcement")),
                    "message": render_markdown(announcement.message),
                    "announcement": announcement,
                    "can_delete": user.has_perm("announcement.delete", announcement),
                },
            )
        )

    return mark_safe("\n".join(ret))


@register.simple_tag(takes_context=True)
def active_tab(context, slug):
    active = "active" if slug == context["active_tab_slug"] else ""
    return mark_safe(f'class="tab-pane {active}" id="{slug}"')


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
        "snippets/component/contributor-agreement.html",
        {"object": component, "next": context["request"].get_full_path()},
    )


@register.simple_tag(takes_context=True)
def get_translate_url(context, obj):
    """Get translate URL based on user preference."""
    if isinstance(obj, BaseStats) or not hasattr(obj, "get_translate_url"):
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


def translation_alerts(translation):
    if translation.is_source:
        yield (
            "state/source.svg",
            gettext("This translation is used for source strings."),
            None,
        )


def component_alerts(component):
    if component.is_repo_link:
        yield (
            "state/link.svg",
            gettext("This component is linked to the %(target)s repository.")
            % {"target": component.linked_component},
            None,
        )

    if component.all_alerts:
        yield (
            "state/alert.svg",
            gettext("Fix this component to clear its alerts."),
            component.get_absolute_url() + "#alerts",
        )

    if component.locked:
        yield ("state/lock.svg", gettext("This translation is locked."), None)

    if component.in_progress():
        yield (
            "state/update.svg",
            gettext("Updating translation component…"),
            reverse("component_progress", kwargs=component.get_reverse_url_kwargs())
            + "?info=1",
        )


def project_alerts(project):
    if project.has_alerts:
        yield (
            "state/alert.svg",
            gettext("Some of the components within this project have alerts."),
            None,
        )

    if project.locked:
        yield ("state/lock.svg", gettext("This translation is locked."), None)


@register.inclusion_tag("trans/embed-alert.html", takes_context=True)
def indicate_alerts(context, obj):
    result = []

    translation = None
    component = None
    project = None

    global_base = context.get("global_base")

    if isinstance(obj, (Translation, GhostTranslation)):
        translation = obj
        component = obj.component
        project = component.project
    elif isinstance(obj, Component):
        component = obj
        project = component.project
    elif isinstance(obj, Project):
        project = obj
    elif isinstance(obj, ProjectLanguage):
        project = obj.project
    elif isinstance(obj, GhostProjectLanguageStats):
        component = obj.component
        project = component.project

    if project is not None and context["user"].has_perm("project.edit", project):
        result.append(
            ("state/admin.svg", gettext("You administrate this project."), None)
        )

    if translation is not None:
        result.extend(translation_alerts(translation))

    if component is not None:
        result.extend(component_alerts(component))
    elif project is not None:
        result.extend(project_alerts(project))

    if getattr(obj, "is_ghost", False):
        result.append(
            ("state/ghost.svg", gettext("This translation does not yet exist."), None)
        )
    elif global_base:
        if isinstance(global_base, str):
            global_base = getattr(obj, global_base)
        stats = get_stats(obj)

        count = global_base.source_strings - stats.all
        if count:
            result.append(
                (
                    "state/ghost.svg",
                    ngettext(
                        "%(count)s string is not being translated here.",
                        "%(count)s strings are not being translated here.",
                        count,
                    )
                    % {"count": count},
                    None,
                )
            )

    if getattr(obj, "is_shared", False):
        result.append(
            (
                "state/share.svg",
                gettext("Shared from the %s project.") % obj.is_shared,
                None,
            )
        )

    return {"icons": result, "component": component, "project": project}


@register.filter
def markdown(text):
    return render_markdown(text)


@register.filter
def choiceval(boundfield):
    """Get literal value from a field's choices.

    Empty value is returned if value is not selected or invalid.
    """
    value = boundfield.value()
    if value is None:
        return ""
    if value is True:
        return gettext("enabled")
    if not hasattr(boundfield.field, "choices"):
        return value
    choices = {str(choice): value for choice, value in boundfield.field.choices}
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


@register.simple_tag
def sort_choices():
    return SORT_CHOICES.items()


@register.simple_tag(takes_context=True)
def render_alert(context, alert):
    return alert.render(user=context["user"])


@register.simple_tag
def get_message_kind(tags):
    return get_message_kind_impl(tags)
