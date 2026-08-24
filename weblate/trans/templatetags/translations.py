# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from django import template
from django.contrib.auth.models import AnonymousUser
from django.contrib.humanize.templatetags.humanize import intcomma
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import escape, format_html, format_html_join, urlize
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext
from siphashc import siphash

from weblate.accounts.avatar import get_user_display
from weblate.accounts.models import DEFAULT_LISTING_COLUMNS, Profile
from weblate.auth.models import User
from weblate.checks.models import CHECKS
from weblate.trans.filter import FILTERS, get_filter_choice
from weblate.trans.formatting import (
    format_language_string,
    format_source_string,
    format_unit_source,
    format_unit_target,
    get_breadcrumbs,
    get_glossary_badge,
    try_linkify_filename,
    unit_state_class,
    unit_state_title,
)
from weblate.trans.forms import FieldDocsMixin
from weblate.trans.models import (
    Announcement,
    Component,
    ContributorAgreement,
    Project,
    Translation,
    Unit,
)
from weblate.trans.models.translation import GhostTranslation
from weblate.trans.util import translation_percent
from weblate.utils.docs import get_doc_url
from weblate.utils.formatting import (
    format_json,
    number_format,
    render_documentation_icon,
)
from weblate.utils.hash import hash_to_checksum
from weblate.utils.markdown import render_markdown
from weblate.utils.messages import get_message_kind as get_message_kind_impl
from weblate.utils.random import get_random_identifier
from weblate.utils.stats import (
    BaseStats,
    ProjectLanguage,
)
from weblate.utils.templatetags.icons import icon
from weblate.utils.views import SORT_CHOICES

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django import forms
    from django.db.models import QuerySet
    from django.template.context import Context
    from django.utils.safestring import SafeString
    from django_stubs_ext import StrOrPromise

    from weblate.lang.models import Language
    from weblate.metrics.wrapper import MetricsWrapper
    from weblate.trans.models import (
        Alert,
        Change,
        ComponentList,
    )
    from weblate.utils.stats import (
        GhostCategoryLanguageStats,
        GhostProjectLanguageStats,
    )
    from weblate.workspaces.models import Workspace

register = template.Library()

TYPE_MAPPING = {True: "yes", False: "no", None: "unknown"}
# Mapping of status report flags to names
NAME_MAPPING = {
    True: gettext_lazy("Good configuration"),
    False: gettext_lazy("Bad configuration"),
    None: gettext_lazy("Possible configuration"),
}

FLAG_TEMPLATE = '<span title="{0}" class="{1}">{2}</span>'

PRIORITY_ICONS = {
    60: ("double_arrow_up", "text-danger", gettext_lazy("Priority: Very high")),
    80: ("single_arrow_up", "text-warning", gettext_lazy("Priority: High")),
    120: ("single_arrow_down", "text-muted", gettext_lazy("Priority: Low")),
    140: ("double_arrow_down", "text-secondary", gettext_lazy("Priority: Very low")),
}

format_unit_target = register.inclusion_tag("snippets/format-translation.html")(
    format_unit_target
)
format_unit_source = register.inclusion_tag("snippets/format-translation.html")(
    format_unit_source
)
format_source_string = register.inclusion_tag("snippets/format-translation.html")(
    format_source_string
)
format_language_string = register.inclusion_tag("snippets/format-translation.html")(
    format_language_string
)


@register.simple_tag
def search_name(query):
    """Return name for a query string."""
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
def documentation(context: Context, page, anchor=""):
    """Return link to Weblate documentation."""
    # User might not be present on error pages
    user = context.get("user")
    # Alert documentation can differ from other help resources
    if hasattr(page, "get_documentation_url"):
        return page.get_documentation_url(user=user)
    # Use object method get_doc_url if present
    if hasattr(page, "get_doc_url"):
        return page.get_doc_url(user=user)
    return get_doc_url(page, anchor, user=user)


@register.simple_tag(takes_context=True)
def documentation_icon(
    context: Context, page: str, anchor: str = "", right: bool = False
):
    return render_documentation_icon(documentation(context, page, anchor), right=right)


@register.simple_tag(takes_context=True)
def form_field_doc_link(context: Context, form: forms.Form, field: forms.Field) -> str:
    if isinstance(form, FieldDocsMixin) and (field_doc := form.get_field_doc(field)):
        return render_documentation_icon(
            get_doc_url(*field_doc, user=context.get("user"))
        )
    return ""


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
    return {
        "tags": " ".join(final),
        "task_id": task_id,
        "message": message,
        "progress": 0,
    }


@register.filter(is_safe=True)
def naturaltime(value: float | datetime, microseconds: bool = False) -> SafeString:
    """
    Render date and time values for JavaScript relative-time formatting.

    The returned markup includes the absolute timestamp in the data-datetime
    attribute. The page JavaScript replaces the visible fallback date with a
    relative value for recent timestamps.
    """
    # float is what time() returns
    if isinstance(value, float):
        value = datetime.fromtimestamp(value, tz=timezone.get_current_timezone())
    # datetime is a subclass of date
    if not isinstance(value, date):
        return value

    # Strip microseconds
    if isinstance(value, datetime) and not microseconds:
        value = value.replace(microsecond=0)

    return format_html(
        '<span title="{}" data-datetime="{}" class="naturaltime">{}</span>',
        date_format(value, "SHORT_DATETIME_FORMAT"),
        timezone.localtime(value).isoformat(),
        date_format(value, "SHORT_DATE_FORMAT"),
    )


def _get_naturaltime_bucket(
    value: float | datetime, now: datetime
) -> tuple[str, int | str] | None:
    """Return the relative-time display bucket used by JavaScript."""
    if isinstance(value, float):
        value = datetime.fromtimestamp(value, tz=timezone.get_current_timezone())
    if not isinstance(value, datetime):
        return None

    value = timezone.localtime(value).replace(microsecond=0)
    difference = (timezone.localtime(now) - value).total_seconds()
    if abs(difference) < 2:
        return ("now", 0)
    if difference > 0:
        if difference < 60:
            return ("seconds", int(difference))
        if difference < 60 * 60:
            return ("minutes", int(difference / 60))
        if difference < 60 * 60 * 24:
            return ("hours", int(difference / (60 * 60)))
    return ("date", value.isoformat())


@register.filter
def same_naturaltime(value: float | datetime, other: float | datetime) -> bool:
    """Return whether two values render to the same relative-time label."""
    now = timezone.now()
    first = _get_naturaltime_bucket(value, now)
    second = _get_naturaltime_bucket(other, now)
    if first is None or second is None:
        return value == other
    return first == second


def get_stats(obj):
    if isinstance(obj, BaseStats):
        return obj
    return obj.stats


@register.simple_tag
def review_percent(obj):
    stats = get_stats(obj)
    return list_objects_percent(
        value=stats.approved + stats.readonly,
        percent=stats.approved_percent + stats.readonly_percent,
        query="q=state:>=approved",
        total=stats.all,
        checks=stats.allchecks,
        css="zero-width-540",
    )


def translation_progress_render(
    total: int, readonly: int, approved: int, translated: int, has_review: bool
) -> StrOrPromise:
    if has_review:
        translated -= approved
        approved += readonly
        translated -= readonly

    approved_percent = translation_percent(approved, total, False)
    good_percent = translation_percent(translated, total)

    approved_tag = ""
    good_tag = ""
    if approved_percent > 0.1:
        approved_tag = format_html(
            """
            <div class="progress"
                 role="progressbar"
                 aria-valuenow="{approved}"
                 aria-valuemin="0"
                 aria-valuemax="100"
                 style="width: {approved}%"
                 title="{title}">
                    <div class="progress-bar"></div>
            </div>
            """,
            approved=f"{approved_percent:.1f}",
            title=gettext("Approved"),
        )
    if good_percent > 0.1:
        good_tag = format_html(
            """
            <div class="progress"
                 role="progressbar"
                 aria-valuenow="{good}"
                 aria-valuemin="0"
                 aria-valuemax="100"
                 style="width: {good}%"
                 title="{title}">
                    <div class="progress-bar progress-bar-success"></div>
            </div>
            """,
            good=f"{good_percent:.1f}",
            title=gettext("Translated without any problems"),
        )

    return format_html(
        """<div class="progress-stacked" title="{}">{}{}</div>""",
        gettext("Needs attention"),
        approved_tag,
        good_tag,
    )


@register.simple_tag
def translation_progress(obj):
    stats = get_stats(obj)
    return translation_progress_render(
        stats.all,
        stats.readonly,
        stats.approved,
        stats.translated_without_checks,
        stats.has_review,
    )


@register.simple_tag
def words_progress(obj):
    stats = get_stats(obj)
    return translation_progress_render(
        stats.all_words,
        stats.readonly_words,
        stats.approved_words,
        stats.translated_without_checks_words,
        stats.has_review,
    )


@register.simple_tag
def chars_progress(obj):
    stats = get_stats(obj)
    return translation_progress_render(
        stats.all_chars,
        stats.readonly_chars,
        stats.approved_chars,
        stats.translated_without_checks_chars,
        stats.has_review,
    )


unit_state_class = register.simple_tag(unit_state_class)
unit_state_title = register.simple_tag(unit_state_title)


@register.simple_tag
def get_location_links(user: User | None, unit):
    """Generate links to source files where translation was used."""
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
    return format_html_join(
        mark_safe('\n<span class="divisor">•</span>\n'),
        "{}",
        (
            (try_linkify_filename(location, filename, line, unit, user, "wrap-text"),)
            for location, filename, line in unit.get_locations()
        ),
    )


@register.simple_tag(takes_context=True)
def announcements(
    context: Context, project=None, component=None, language=None, category=None
):
    """Display announcement messages for given context."""
    user = context["user"]

    return format_html_join(
        "\n",
        "{}",
        (
            (
                render_to_string(
                    "message.html",
                    {
                        "tags": f"{announcement.severity} announcement",
                        "message": render_markdown(announcement.message),
                        "announcement": announcement,
                        "can_delete": user.has_perm(
                            "announcement.delete", announcement
                        ),
                    },
                ),
            )
            for announcement in Announcement.objects.context_filter(
                project=project,
                component=component,
                language=language,
                category=category,
            )
        ),
    )


@register.simple_tag(takes_context=True)
def active_tab(context: Context, slug):
    active = "active" if slug == context["active_tab_slug"] else ""
    return format_html('class="tab-pane {}" id="{}"', active, slug)


@register.simple_tag(takes_context=True)
def active_link(context: Context, slug):
    active = "active" if slug == context["active_tab_slug"] else ""
    return format_html('class="nav-link {}"', active)


def _needs_agreement(component, user: User) -> bool:
    if not component.effective_agreement:
        return False
    return not ContributorAgreement.objects.has_agreed(user, component)


@register.simple_tag(takes_context=True)
def needs_agreement(context: Context, component):
    return _needs_agreement(component, context["user"])


@register.simple_tag(takes_context=True)
def show_contributor_agreement(context: Context, component):
    if not _needs_agreement(component, context["user"]):
        return ""

    return render_to_string(
        "snippets/component/contributor-agreement.html",
        {
            "object": component,
            "next": context["request"].get_full_path(),
            "user": context["user"],
        },
    )


@register.simple_tag(takes_context=True)
def get_translate_url(context: Context, obj, glossary_browse=True) -> str:
    """Get translate URL based on user preference."""
    if isinstance(obj, BaseStats) or not hasattr(obj, "get_translate_url"):
        return ""
    if glossary_browse and hasattr(obj, "component") and obj.component.is_glossary:
        name = "browse"
    elif context["user"].profile.translate_mode == Profile.TRANSLATE_ZEN:
        name = "zen"
    else:
        name = "translate"
    return reverse(name, kwargs={"path": obj.get_url_path()})


@register.simple_tag
def get_listing_columns(user: User | AnonymousUser) -> set[str]:
    """Get columns to show in object listings based on user preference."""
    if user.is_authenticated:
        return set(user.profile.listing_columns)
    return set(DEFAULT_LISTING_COLUMNS)


@register.simple_tag
def get_search_url(obj) -> str:
    """Get translate URL based on user preference."""
    if not hasattr(obj, "get_url_path"):
        # Ghost translation
        return ""
    return reverse("search", kwargs={"path": obj.get_url_path()})


@register.simple_tag(takes_context=True)
def get_browse_url(context: Context, obj):
    """Get translate URL based on user preference."""
    # Project listing on language page
    if "language" in context and isinstance(obj, Project):
        project_language = ProjectLanguage(obj, context["language"])
        return project_language.get_absolute_url()

    return obj.get_absolute_url()


@register.simple_tag(takes_context=True)
def init_unique_row_id(context) -> str:
    context["row_uuid"] = get_random_identifier()
    return ""


@register.simple_tag(takes_context=True)
def get_unique_row_id(context: Context, obj):
    """Get unique row ID for multiline tables."""
    return f"{context['row_uuid']}-{obj.pk}"


@register.simple_tag
def get_filter_name(name: str) -> str:
    names = dict(get_filter_choice())
    return names[name]


def get_alert_css_class(icon_name: str, css_class: str = "") -> str:
    if css_class:
        return css_class
    if icon_name == "state/ghost.svg":
        return "grey"
    if icon_name == "state/alert.svg":
        return "red"
    return ""


def translation_alerts(
    translation: Translation | ProjectLanguage | GhostTranslation,
) -> Iterable[tuple[str, StrOrPromise, str | None, str]]:
    if translation.is_source:
        yield (
            "state/source.svg",
            gettext("This language is used for source strings."),
            None,
            "",
        )


def component_alerts(
    component: Component,
) -> Iterable[tuple[str, StrOrPromise, str | None, str]]:
    if component.is_repo_link:
        yield (
            "state/link.svg",
            gettext("This component is linked to the %(target)s repository.")
            % {"target": component.linked_component},
            None,
            "",
        )

    if component.all_problem_alerts:
        yield (
            "state/alert.svg",
            gettext("Fix this component to clear its diagnostics."),
            f"{component.get_absolute_url()}#alerts",
            "",
        )

    if component.locked:
        yield ("state/lock.svg", gettext("This translation is locked."), None, "")

    if component.in_progress():
        yield (
            "state/update.svg",
            gettext("Updating translation component…"),
            f"{reverse('show_progress', kwargs={'path': component.get_url_path()})}?info=1",
            "",
        )


def project_alerts(
    project: Project,
) -> Iterable[tuple[str, StrOrPromise, str | None, str]]:
    if project.has_alerts:
        yield (
            "state/alert.svg",
            gettext("Some of the components within this project have diagnostics."),
            None,
            "",
        )

    if project.locked:
        yield ("state/lock.svg", gettext("This translation is locked."), None, "")


def get_alerts(
    *,
    context: Context,
    obj: Translation
    | Component
    | ProjectLanguage
    | Project
    | Workspace
    | GhostProjectLanguageStats
    | GhostCategoryLanguageStats,
    translation: Translation | GhostTranslation | None,
    component: Component | None,
    project: Project | None,
    project_language: ProjectLanguage | None,
) -> Iterable[tuple[str, StrOrPromise, str | None, str]]:
    global_base = context.get("global_base")

    if isinstance(obj, Component) and (priority := obj.priority) in PRIORITY_ICONS:
        selected_svg, css_class, title_text = PRIORITY_ICONS[priority]
        yield f"priorities/{selected_svg}.svg", title_text, None, css_class

    if project_language is not None:
        # For source language
        yield from translation_alerts(project_language)

    if project is not None and context["user"].has_perm("project.edit", project):
        yield ("state/admin.svg", gettext("You administrate this project."), None, "")

    if translation is not None:
        yield from translation_alerts(translation)

    if isinstance(obj, Component) and obj.restricted:
        yield ("state/shield.svg", gettext("Restricted component"), None, "")

    if component is not None:
        yield from (component_alerts(component))
    elif project is not None:
        yield from (project_alerts(project))

    if getattr(obj, "is_ghost", False):
        yield (
            (
                "state/ghost.svg",
                gettext("This translation does not yet exist."),
                None,
                "",
            )
        )
    elif global_base:
        if isinstance(global_base, str):
            global_base = getattr(obj, global_base)
        stats = get_stats(obj)

        count = global_base.source_strings - stats.all
        if count:
            yield (
                (
                    "state/ghost.svg",
                    ngettext(
                        "%(count)s string is not being translated here.",
                        "%(count)s strings are not being translated here.",
                        count,
                    )
                    % {"count": intcomma(count)},
                    None,
                    "",
                )
            )

    if is_shared := getattr(obj, "is_shared", False):
        yield (
            (
                "state/share.svg",
                gettext("Shared from the %s project.") % is_shared,
                None,
                "",
            )
        )


@register.simple_tag(takes_context=True)
def indicate_alerts(
    context: Context,
    obj: Translation
    | Component
    | ProjectLanguage
    | Project
    | Workspace
    | GhostProjectLanguageStats
    | GhostCategoryLanguageStats,
) -> str:
    translation: Translation | GhostTranslation | None = None
    component: Component | None = None
    project: Project | None = None
    project_language: ProjectLanguage | None = None

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
        project_language = obj
    # There is intentionally no project-level alerts for
    # GhostProjectLanguageStats and GhostCategoryLanguageStats as these would
    # be confusing (showing alert or admin icon on ghost containers).

    icons = format_html_join(
        "\n",
        '{}<span class="state-icon {}" title="{}" alt="{}">{}</span>{}',
        (
            (
                format_html('<a href="{}">', url) if url else "",
                get_alert_css_class(icon_name, css_class),
                text,
                text,
                icon(icon_name),
                mark_safe("</a>") if url else "",
            )
            for icon_name, text, url, css_class in get_alerts(
                context=context,
                translation=translation,
                component=component,
                project=project,
                project_language=project_language,
                obj=obj,
            )
        ),
    )

    license_badge = ""
    if (
        component
        and component.effective_license
        and component.effective_license != "proprietary"
    ):
        license_badge = format_html(
            ' <span title="{}" class="license badge">{}</span>',
            component.get_license_display(),
            component.effective_license,
        )

    return format_html("{}{}", icons, license_badge)


@register.filter(is_safe=True)
def markdown(text: str) -> str:
    return format_html('<div class="markdown">{}</div>', render_markdown(text))


@register.filter
def can_dismiss_alert(alert: Alert, user: User) -> bool:
    return alert.can_user_dismiss(user)


@register.filter
def format_commit_author(commit) -> str:
    users = User.objects.filter(
        social_auth__verifiedemail__email=commit["author_email"]
    )
    user = users.first()
    if user is None:
        return commit["author_name"]
    return get_user_display(user, True, True)


@register.filter
def percent_format(number: float) -> str:
    if number < 0.1:
        percent = 0
    elif number < 1:
        percent = 1
    elif number >= 99.999999:
        percent = 100
    elif number > 99:
        percent = 99
    else:
        percent = int(number)
    return mark_safe(  # ruff: ignore[suspicious-mark-safe-usage]
        # Translators: Formatting of the translation percent, insert non-breakable space if
        # your language expects it before the percent sign.
        pgettext("Translated percents", "%(percent)s%%")
        % {"percent": intcomma(percent)}
    )


number_format = register.filter(number_format)


@register.filter
def trend_format(number: int) -> str:
    if number < 0:
        prefix = "−"
        trend = "trend-down"
    else:
        prefix = "+"
        trend = "trend-up"
    number = abs(number)
    if number < 0.1:
        return "—"
    return format_html(
        '{}{} <span class="{}"></span>',
        prefix,
        percent_format(number),
        trend,
    )


@register.filter
def hash_text(name: str) -> str:
    """Hash text for use in HTML id."""
    return hash_to_checksum(siphash("Weblate URL hash", name.encode()))


@register.simple_tag
def sort_choices():
    return SORT_CHOICES.items()


@register.simple_tag(takes_context=True)
def render_alert(context: Context, alert: Alert) -> str:
    return alert.render(user=context["user"])


@register.simple_tag
def get_message_kind(tags) -> str:
    return get_message_kind_impl(tags)


@register.simple_tag
def any_unit_has_context(units: Iterable[Unit]) -> bool:
    return any(unit.context for unit in units)


@register.filter(is_safe=True, needs_autoescape=True)
def urlize_ugc(value: str, autoescape: bool = True) -> str:
    """Convert URLs in plain text into clickable links."""
    html = urlize(value, nofollow=True, autoescape=autoescape)
    return mark_safe(html.replace('rel="nofollow"', 'rel="ugc" target="_blank"'))  # ruff: ignore[suspicious-mark-safe-usage]


get_glossary_badge = register.simple_tag(get_glossary_badge)


@register.simple_tag
def path_object_breadcrumbs(path_object, flags: bool = True):
    return format_html_join(
        "\n",
        '<li class="breadcrumb-item"><a href="{}">{}</a></li>',
        get_breadcrumbs(path_object, flags=flags),
    )


@register.simple_tag
def path_object_links(path_object, flags: bool = True):
    return format_html_join(
        "/",
        '<a href="{}">{}</a>',
        get_breadcrumbs(path_object, flags=flags),
    )


@register.simple_tag
def get_projectlanguage(project: Project, language: Language) -> ProjectLanguage:
    return ProjectLanguage(project=project, language=language)


@register.simple_tag
def get_workflow_flags(translation: Translation | None, component: Component):
    if translation:
        return {
            "suggestion_voting": translation.suggestion_voting,
            "suggestion_autoaccept": translation.suggestion_autoaccept,
            "enable_suggestions": translation.enable_suggestions,
            "restrict_direct_editing": translation.restrict_direct_editing,
            "translation_review": translation.enable_review,
        }
    return {
        "suggestion_voting": component.suggestion_voting,
        "suggestion_autoaccept": component.suggestion_autoaccept,
        "enable_suggestions": component.enable_suggestions,
        "restrict_direct_editing": False,
        "translation_review": component.project.translation_review,
    }


@register.simple_tag
def list_objects_number(
    value: int,
    search_url: str | None = None,
    translate_url: str | None = None,
    query: str = "",
    css: str | None = None,
    show_zero: bool = False,
):
    value_formatted: str | SafeString
    url_start: str | SafeString
    url_end: str | SafeString
    url_start = url_end = ""
    if value == 0 and not show_zero:
        value_formatted = format_html(
            """<span class="visually-hidden">{}</span>""", value
        )
    else:
        if search_url or translate_url:
            url_start = format_html(
                '<a href="{url}?{query}">',
                url=translate_url or search_url,
                query=query,
            )
            url_end = mark_safe("</a>")
        value_formatted = intcomma(value)
    return format_html(
        """
        <td class="number {css}" data-value="{value}">
            {url_start}
            {value_formatted}
            {url_end}
        </td>
        """,
        url_start=url_start,
        url_end=url_end,
        css=css if css is not None else "",
        value=value,
        value_formatted=value_formatted,
    )


@register.simple_tag
def list_objects_percent(
    percent: float,
    value: int,
    total: int,
    checks: int,
    search_url: str | None = None,
    translate_url: str | None = None,
    query: str = "",
    css: str | None = None,
):
    url_start: str | SafeString
    url_end: str | SafeString
    percent_formatted: str | SafeString
    if search_url or translate_url:
        url_start = format_html(
            '<a href="{url}?{query}">',
            url=translate_url or search_url,
            query=query,
        )
        url_end = mark_safe("</a>")
    else:
        url_start = url_end = ""

    if value and value == total and checks == 0:
        percent_formatted = format_html(
            """<span class="green" title="{}">{}</span>""",
            ngettext(
                "Completed translation with %(count)s string",
                "Completed translation with %(count)s strings",
                total,
            )
            % {"count": intcomma(total)},
            icon("check.svg"),
        )
    elif value == 0 and total == 0:
        percent_formatted = format_html(
            """<span class="green" title="{}">{}</span>""",
            gettext("No strings to translate"),
            icon("check.svg"),
        )
    else:
        percent_formatted = percent_format(percent)
    return format_html(
        """
        <td class="number {css}" data-value="{percent}" title="{value_formatted}">
            {url_start}
            {percent_formatted}
            {url_end}
        </td>
        """,
        url_start=url_start,
        url_end=url_end,
        css=css,
        percent=f"{percent:f}",
        percent_formatted=percent_formatted,
        value_formatted=gettext("%(value)s of %(all)s")
        % {"value": intcomma(value), "all": intcomma(total)},
    )


@register.inclusion_tag("snippets/info.html", takes_context=True)
def show_info(  # ruff: ignore[too-many-arguments]
    context: Context,
    *,
    workspace: Workspace | None = None,
    project: Project | None = None,
    component: Component | None = None,
    translation: Translation | None = None,
    language: Language | None = None,
    componentlist: ComponentList | None = None,
    stats: BaseStats | None = None,
    metrics: MetricsWrapper | None = None,
    show_source: bool = False,
    show_global: bool = False,
    show_full_language: bool = True,
    top_users: QuerySet[Profile] | None = None,
    total_translations: int | None = None,
):
    """
    Render project information table.

    This merely exists to be able to pass default values to {% include %}.
    """
    return {
        "user": context["user"],
        "workspace": workspace,
        "project": project,
        "component": component,
        "translation": translation,
        "language": language,
        "componentlist": componentlist,
        "stats": stats,
        "metrics": metrics,
        "show_source": show_source,
        "show_global": show_global,
        "show_full_language": show_full_language,
        "top_users": top_users,
        "total_translations": total_translations,
    }


format_json = register.filter(is_safe=True)(format_json)


@register.filter(is_safe=True)
def format_headers(value: dict[str, str]) -> str:
    return format_html_join(mark_safe("<br>"), "<b>{}</b>: {}", value.items())


@register.inclusion_tag("snippets/last-changes-content.html")
def format_last_changes_content(
    last_changes: Iterable[Change],
    user: str | User | AnonymousUser,
    in_email: bool = False,
    debug: bool = False,
    search_url: str | None = None,
    offset: int | None = None,
    translate_url: str | None = None,
):
    """
    Format last changes content for display.

    This is a simplified version of the prepare_last_changes_context function.
    """
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.change_display import (
        get_change_history_context,
    )

    if isinstance(user, str):  # e.g in email digest
        user = AnonymousUser()

    processed_changes = []
    for change in last_changes:
        # Permissions
        can_revert = change.can_revert() and user.has_perm("unit.edit", change.unit)
        can_block_user = (
            change.user
            and not change.user.is_anonymous
            and change.project
            and change.user != user
            and user.has_perm("project.permissions", change.project)
        )

        processed_changes.append(
            {
                "change": change,
                "permissions": {
                    "can_revert": can_revert,
                    "can_block_user": can_block_user,
                },
                "ip_address": change.get_ip_address() if user.is_superuser else None,
                "history_data": get_change_history_context(
                    change, include_private_details=bool(user.is_authenticated)
                ),
            }
        )
    return {
        "changes_with_context": processed_changes,
        "in_email": in_email,
        "debug": debug,
        "search_url": search_url,
        "offset": offset,
        "translate_url": translate_url,
    }


@register.simple_tag
def get_git_export_example_url() -> str:
    url = reverse(
        "git-export",
        kwargs={
            "path": ["PROJECT", "COMPONENT"],
            "git_request": "info/refs",
        },
    )
    # Strip trailing info/refs part:
    return url[:-9]


@register.filter(is_safe=True)
def object_link(obj) -> str:
    return format_html('<a href="{}">{}</a>', obj.get_absolute_url(), str(obj))
