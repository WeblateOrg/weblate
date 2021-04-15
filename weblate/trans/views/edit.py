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

import json
import time
from math import ceil

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, Q, When
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop
from django.views.decorators.http import require_POST

from weblate.checks.models import CHECKS, get_display_checks
from weblate.glossary.forms import TermForm
from weblate.glossary.models import get_glossary_terms
from weblate.lang.models import Language
from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.screenshots.forms import ScreenshotForm
from weblate.trans.forms import (
    AutoForm,
    ChecksumForm,
    CommentForm,
    ContextForm,
    MergeForm,
    PositionSearchForm,
    RevertForm,
    TranslationForm,
    ZenTranslationForm,
    get_new_unit_form,
)
from weblate.trans.models import Change, Comment, Suggestion, Unit, Vote
from weblate.trans.tasks import auto_translate
from weblate.trans.templatetags.translations import unit_state_class, unit_state_title
from weblate.trans.util import join_plural, redirect_next, render, split_plural
from weblate.utils import messages
from weblate.utils.antispam import is_spam
from weblate.utils.hash import hash_to_checksum
from weblate.utils.messages import get_message_kind
from weblate.utils.ratelimit import revert_rate_limit, session_ratelimit_post
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED
from weblate.utils.stats import ProjectLanguage
from weblate.utils.views import (
    get_project,
    get_sort_name,
    get_translation,
    show_form_errors,
)


def parse_params(request, project, component, lang):
    """Parses base object and unit set from request."""
    if component == "-":
        project = get_project(request, project)
        language = get_object_or_404(Language, code=lang)
        obj = ProjectLanguage(project, language)
        unit_set = Unit.objects.filter(
            translation__component__project=project, translation__language=language
        )
    else:
        # Translation case
        obj = get_translation(request, project, component, lang)
        unit_set = obj.unit_set
        project = obj.component.project

    return obj, project, unit_set


def get_other_units(unit):
    """Returns other units to show while translating."""
    result = {
        "total": 0,
        "skipped": False,
        "same": [],
        "matching": [],
        "context": [],
        "source": [],
    }

    allow_merge = False
    untranslated = False
    translation = unit.translation
    component = translation.component
    propagation = component.allow_translation_propagation
    same = None

    if unit.source and unit.context:
        match = Q(source=unit.source) & Q(context=unit.context)
        if component.has_template():
            query = Q(source=unit.source) | Q(context=unit.context)
        else:
            query = Q(source=unit.source)
    elif unit.source:
        match = Q(source=unit.source) & Q(context="")
        query = Q(source=unit.source)
    elif unit.context:
        match = Q(context=unit.context)
        query = Q(context=unit.context)
    else:
        return result

    units = (
        Unit.objects.filter(
            query,
            translation__component__project=component.project,
            translation__language=translation.language,
        )
        .annotate(
            matches_current=Case(
                When(condition=match, then=1), default=0, output_field=IntegerField()
            )
        )
        .order_by("-matches_current")
    )

    units_count = units.count()

    # Is it only this unit?
    if units_count == 1:
        return result

    result["total"] = units_count
    result["skipped"] = units_count > 20

    for item in units[:20]:
        item.allow_merge = item.differently_translated = (
            item.translated and item.target != unit.target
        )
        item.is_propagated = (
            propagation and item.source == unit.source and item.context == unit.context
        )
        untranslated |= not item.translated
        allow_merge |= item.allow_merge
        if item.pk == unit.pk:
            same = item
            result["same"].append(item)
        elif item.source == unit.source and item.context == unit.context:
            result["matching"].append(item)
        elif item.source == unit.source:
            result["source"].append(item)
        elif item.context == unit.context:
            result["context"].append(item)

    # Slightly different logic to allow applying current translation to
    # the propagated strings
    if same is not None:
        same.allow_merge = (
            (untranslated or allow_merge) and same.translated and propagation
        )
        allow_merge |= same.allow_merge

    result["total"] = sum(len(result[x]) for x in ("matching", "source", "context"))
    result["allow_merge"] = allow_merge

    return result


def cleanup_session(session):
    """Delete old search results from session storage."""
    now = int(time.time())
    keys = list(session.keys())
    for key in keys:
        if not key.startswith("search_"):
            continue
        value = session[key]
        if not isinstance(value, dict) or value["ttl"] < now or "items" not in value:
            del session[key]


def search(base, project, unit_set, request, blank: bool = False):
    """Perform search or returns cached search results."""
    # Possible new search
    form = PositionSearchForm(user=request.user, data=request.GET, show_builder=False)

    # Process form
    form_valid = form.is_valid()
    if form_valid:
        cleaned_data = form.cleaned_data
        search_url = form.urlencode()
        search_query = form.get_search_query()
        name = form.get_name()
        search_items = form.items()
    else:
        cleaned_data = {}
        show_form_errors(request, form)
        search_url = ""
        search_query = ""
        name = ""
        search_items = ()

    search_result = {
        "form": form,
        "offset": cleaned_data.get("offset", 1),
    }
    session_key = f"search_{base.cache_key}_{search_url}"

    if (
        session_key in request.session
        and "offset" in request.GET
        and "items" in request.session[session_key]
    ):
        search_result.update(request.session[session_key])
        return search_result

    allunits = unit_set.search(cleaned_data.get("q", ""), project=project).distinct()

    # Grab unit IDs
    unit_ids = list(
        allunits.order_by_request(cleaned_data, base).values_list("id", flat=True)
    )

    # Check empty search results
    if not unit_ids and not blank:
        messages.warning(request, _("No string matched your search!"))
        return redirect(base)

    # Remove old search results
    cleanup_session(request.session)

    store_result = {
        "query": search_query,
        "url": search_url,
        "items": search_items,
        "key": session_key,
        "name": str(name),
        "ids": unit_ids,
        "ttl": int(time.time()) + 86400,
    }
    request.session[session_key] = store_result

    search_result.update(store_result)
    return search_result


def perform_suggestion(unit, form, request):
    """Handle suggesion saving."""
    if form.cleaned_data["target"][0] == "":
        messages.error(request, _("Your suggestion is empty!"))
        # Stay on same entry
        return False
    if not request.user.has_perm("suggestion.add", unit):
        # Need privilege to add
        messages.error(request, _("You don't have privileges to add suggestions!"))
        # Stay on same entry
        return False
    if not request.user.is_authenticated:
        # Spam check
        if is_spam("\n".join(form.cleaned_data["target"]), request):
            messages.error(request, _("Your suggestion has been identified as spam!"))
            return False

    # Create the suggestion
    result = Suggestion.objects.add(
        unit,
        join_plural(form.cleaned_data["target"]),
        request,
        request.user.has_perm("suggestion.vote", unit),
    )
    if not result:
        messages.error(request, _("Your suggestion already exists!"))
    return result


def perform_translation(unit, form, request):
    """Handle translation and stores it to a backend."""
    user = request.user
    profile = user.profile
    project = unit.translation.component.project
    # Remember old checks
    oldchecks = unit.all_checks_names

    # Update explanation for glossary
    if unit.translation.component.is_glossary:
        unit.explanation = form.cleaned_data["explanation"]
    # Save
    saved = unit.translate(
        user, form.cleaned_data["target"], form.cleaned_data["state"]
    )

    # Warn about applied fixups
    if unit.fixups:
        messages.info(
            request,
            _("Following fixups were applied to translation: %s")
            % ", ".join(str(f) for f in unit.fixups),
        )

    # No change edit - should we skip to next entry
    if not saved:
        revert_rate_limit("translate", request)
        return True

    # Auto subscribe user
    if not profile.languages.exists():
        language = unit.translation.language
        profile.languages.add(language)
        messages.info(
            request,
            _(
                "Added %(language)s to your translated languages. "
                "You can adjust them in the settings."
            )
            % {"language": language},
        )
    if profile.auto_watch and not profile.watched.filter(pk=project.pk).exists():
        profile.watched.add(project)
        messages.info(
            request,
            _(
                "Added %(project)s to your watched projects. "
                "You can adjust them and this behavior in the settings."
            )
            % {"project": project},
        )

    # Get new set of checks
    newchecks = unit.all_checks_names

    # Did we introduce any new failures?
    if (
        saved
        and form.cleaned_data["state"] >= STATE_TRANSLATED
        and newchecks > oldchecks
    ):
        # Show message to user
        messages.error(
            request,
            _(
                "The translation has been saved, however there "
                "are some newly failing checks: {0}"
            ).format(", ".join(str(CHECKS[check].name) for check in newchecks)),
        )
        # Stay on same entry
        return False

    return True


@session_ratelimit_post("translate")
def handle_translate(request, unit, this_unit_url, next_unit_url):
    """Save translation or suggestion to database and backend."""
    form = TranslationForm(request.user, unit, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return None

    go_next = True

    if "suggest" in request.POST:
        go_next = perform_suggestion(unit, form, request)
    elif not request.user.has_perm("unit.edit", unit):
        messages.error(request, _("Insufficient privileges for saving translations."))
    else:
        go_next = perform_translation(unit, form, request)

    # Redirect to next entry
    if go_next:
        return HttpResponseRedirect(next_unit_url)
    return HttpResponseRedirect(this_unit_url)


def handle_merge(unit, request, next_unit_url):
    """Handle unit merging."""
    mergeform = MergeForm(unit, request.POST)
    if not mergeform.is_valid():
        messages.error(request, _("Invalid merge request!"))
        return None

    merged = mergeform.cleaned_data["merge_unit"]

    if not request.user.has_perm("unit.edit", unit):
        messages.error(request, _("Insufficient privileges for saving translations."))
        return None

    # Store unit
    unit.translate(request.user, merged.target, merged.state)
    # Redirect to next entry
    return HttpResponseRedirect(next_unit_url)


def handle_revert(unit, request, next_unit_url):
    revertform = RevertForm(unit, request.GET)
    if not revertform.is_valid():
        messages.error(request, _("Invalid revert request!"))
        return None

    change = revertform.cleaned_data["revert_change"]

    if not request.user.has_perm("unit.edit", unit):
        messages.error(request, _("Insufficient privileges for saving translations."))
        return None

    if not change.can_revert():
        messages.error(request, _("Can not revert to empty translation!"))
        return None
    # Store unit
    unit.translate(
        request.user,
        split_plural(change.old),
        STATE_FUZZY if change.action == Change.ACTION_MARKED_EDIT else unit.state,
        change_action=Change.ACTION_REVERT,
    )
    # Redirect to next entry
    return HttpResponseRedirect(next_unit_url)


def check_suggest_permissions(request, mode, unit, suggestion):
    """Check permission for suggestion handling."""
    user = request.user
    if mode in ("accept", "accept_edit"):
        if not user.has_perm("suggestion.accept", unit):
            messages.error(
                request, _("You do not have privilege to accept suggestions!")
            )
            return False
    elif mode in ("delete", "spam"):
        if not user.has_perm("suggestion.delete", suggestion):
            messages.error(
                request, _("You do not have privilege to delete suggestions!")
            )
            return False
    elif mode in ("upvote", "downvote"):
        if not user.has_perm("suggestion.vote", unit):
            messages.error(
                request, _("You do not have privilege to vote for suggestions!")
            )
            return False
    return True


def handle_suggestions(request, unit, this_unit_url, next_unit_url):
    """Handle suggestion deleting/accepting."""
    sugid = ""
    params = ("accept", "accept_edit", "delete", "spam", "upvote", "downvote")
    redirect_url = this_unit_url
    mode = None

    # Parse suggestion ID
    for param in params:
        if param in request.POST:
            sugid = request.POST[param]
            mode = param
            break

    # Fetch suggestion
    try:
        suggestion = Suggestion.objects.get(pk=int(sugid), unit=unit)
    except (Suggestion.DoesNotExist, ValueError):
        messages.error(request, _("Invalid suggestion!"))
        return HttpResponseRedirect(this_unit_url)

    # Permissions check
    if not check_suggest_permissions(request, mode, unit, suggestion):
        return HttpResponseRedirect(this_unit_url)

    # Perform operation
    if "accept" in request.POST or "accept_edit" in request.POST:
        suggestion.accept(request)
        if "accept" in request.POST:
            redirect_url = next_unit_url
    elif "delete" in request.POST or "spam" in request.POST:
        suggestion.delete_log(request.user, is_spam="spam" in request.POST)
    elif "upvote" in request.POST:
        suggestion.add_vote(request, Vote.POSITIVE)
        redirect_url = next_unit_url
    elif "downvote" in request.POST:
        suggestion.add_vote(request, Vote.NEGATIVE)

    return HttpResponseRedirect(redirect_url)


def translate(request, project, component, lang):  # noqa: C901
    """Generic entry point for translating, suggesting and searching."""
    obj, project, unit_set = parse_params(request, project, component, lang)

    # Search results
    search_result = search(obj, project, unit_set, request)

    # Handle redirects
    if isinstance(search_result, HttpResponse):
        return search_result

    # Get numer of results
    num_results = len(search_result["ids"])

    # Search offset
    offset = search_result["offset"]

    # Checksum unit access
    checksum_form = ChecksumForm(unit_set, request.GET or request.POST)
    if checksum_form.is_valid():
        unit = checksum_form.cleaned_data["unit"]
        try:
            offset = search_result["ids"].index(unit.id) + 1
        except ValueError:
            messages.warning(request, _("No string matched your search!"))
            return redirect(obj)
    else:
        # Check boundaries
        if not 0 < offset <= num_results:
            messages.info(request, _("The translation has come to an end."))
            # Delete search
            del request.session[search_result["key"]]
            return redirect(obj)

        # Grab actual unit
        try:
            unit = unit_set.get(pk=search_result["ids"][offset - 1])
        except Unit.DoesNotExist:
            # Can happen when using SID for other translation
            messages.error(request, _("Invalid search string!"))
            return redirect(obj)

    # Check locks
    locked = unit.translation.component.locked

    # Some URLs we will most likely use
    base_unit_url = "{}?{}&offset=".format(
        obj.get_translate_url(), search_result["url"]
    )
    this_unit_url = base_unit_url + str(offset)
    next_unit_url = base_unit_url + str(offset + 1)

    response = None

    # Any form submitted?
    if "skip" in request.POST:
        return redirect(next_unit_url)
    if request.method == "POST" and "merge" not in request.POST:
        if (
            not locked
            and "accept" not in request.POST
            and "accept_edit" not in request.POST
            and "delete" not in request.POST
            and "spam" not in request.POST
            and "upvote" not in request.POST
            and "downvote" not in request.POST
        ):
            # Handle translation
            response = handle_translate(request, unit, this_unit_url, next_unit_url)
        elif not locked or "delete" in request.POST or "spam" in request.POST:
            # Handle accepting/deleting suggestions
            response = handle_suggestions(request, unit, this_unit_url, next_unit_url)

    # Handle translation merging
    elif "merge" in request.POST and not locked:
        response = handle_merge(unit, request, next_unit_url)

    # Handle reverting
    elif "revert" in request.GET and not locked:
        response = handle_revert(unit, request, this_unit_url)

    # Pass possible redirect further
    if response is not None:
        return response

    # Show secondary languages for signed in users
    if request.user.is_authenticated:
        secondary = unit.get_secondary_units(request.user)
    else:
        secondary = None

    # Prepare form
    form = TranslationForm(request.user, unit)
    sort = get_sort_name(request, obj)

    screenshot_form = None
    if request.user.has_perm("screenshot.add", unit.translation):
        screenshot_form = ScreenshotForm(
            unit.translation.component, initial={"translation": unit.translation}
        )

    return render(
        request,
        "translate.html",
        {
            "this_unit_url": this_unit_url,
            "first_unit_url": base_unit_url + "1",
            "last_unit_url": base_unit_url + str(num_results),
            "next_unit_url": next_unit_url,
            "prev_unit_url": base_unit_url + str(offset - 1),
            "object": obj,
            "project": project,
            "unit": unit,
            "nearby": unit.nearby(request.user.profile.nearby_strings),
            "nearby_keys": unit.nearby_keys(request.user.profile.nearby_strings),
            "others": get_other_units(unit),
            "search_url": search_result["url"],
            "search_items": search_result["items"],
            "search_query": search_result["query"],
            "offset": offset,
            "sort_name": sort["name"],
            "sort_query": sort["query"],
            "filter_name": search_result["name"],
            "filter_count": num_results,
            "filter_pos": offset,
            "form": form,
            "comment_form": CommentForm(
                project,
                initial={"scope": "global" if unit.is_source else "translation"},
            ),
            "context_form": ContextForm(instance=unit.source_unit, user=request.user),
            "search_form": search_result["form"].reset_offset(),
            "secondary": secondary,
            "locked": locked,
            "glossary": get_glossary_terms(unit),
            "addterm_form": TermForm(unit),
            "last_changes": unit.change_set.prefetch().order()[:10],
            "screenshots": (
                unit.source_unit.screenshots.all() | unit.screenshots.all()
            ).order,
            "last_changes_url": urlencode(unit.translation.get_reverse_url_kwargs()),
            "display_checks": list(get_display_checks(unit)),
            "machinery_services": json.dumps(list(MACHINE_TRANSLATION_SERVICES.keys())),
            "new_unit_form": get_new_unit_form(
                unit.translation, request.user, initial={"variant": unit.source}
            ),
            "screenshot_form": screenshot_form,
        },
    )


@require_POST
@login_required
def auto_translation(request, project, component, lang):
    translation = get_translation(request, project, component, lang)
    project = translation.component.project
    if not request.user.has_perm("translation.auto", project):
        raise PermissionDenied()

    autoform = AutoForm(translation.component, request.POST)

    if translation.component.locked or not autoform.is_valid():
        messages.error(request, _("Failed to process form!"))
        show_form_errors(request, autoform)
        return redirect(translation)

    args = (
        request.user.id,
        translation.id,
        autoform.cleaned_data["mode"],
        autoform.cleaned_data["filter_type"],
        autoform.cleaned_data["auto_source"],
        autoform.cleaned_data["component"],
        autoform.cleaned_data["engines"],
        autoform.cleaned_data["threshold"],
    )

    if settings.CELERY_TASK_ALWAYS_EAGER:
        messages.success(request, auto_translate(*args, translation=translation))
    else:
        task = auto_translate.delay(*args)
        messages.success(
            request, _("Automatic translation in progress"), f"task:{task.id}"
        )

    return redirect(translation)


@login_required
@session_ratelimit_post("comment")
def comment(request, pk):
    """Add new comment."""
    scope = unit = get_object_or_404(Unit, pk=pk)
    component = unit.translation.component

    if not request.user.has_perm("comment.add", unit.translation):
        raise PermissionDenied()

    form = CommentForm(component.project, request.POST)

    if form.is_valid():
        # Is this source or target comment?
        if form.cleaned_data["scope"] in ("global", "report"):
            scope = unit.source_unit
        # Create comment object
        Comment.objects.add(scope, request, form.cleaned_data["comment"])
        # Add review label/flag
        if form.cleaned_data["scope"] == "report":
            if component.has_template():
                if scope.translated and not scope.readonly:
                    scope.translate(
                        request.user,
                        scope.target,
                        STATE_FUZZY,
                        change_action=Change.ACTION_MARKED_EDIT,
                    )
            else:
                label = component.project.label_set.get_or_create(
                    name=gettext_noop("Source needs review"), defaults={"color": "red"}
                )[0]
                scope.labels.add(label)
        messages.success(request, _("Posted new comment"))
    else:
        messages.error(request, _("Failed to add comment!"))

    return redirect_next(request.POST.get("next"), unit)


@login_required
@require_POST
def delete_comment(request, pk):
    """Delete comment."""
    comment_obj = get_object_or_404(Comment, pk=pk)

    if not request.user.has_perm("comment.delete", comment_obj):
        raise PermissionDenied()

    fallback_url = comment_obj.unit.get_absolute_url()

    if "spam" in request.POST:
        comment_obj.report_spam()
    comment_obj.delete()
    messages.info(request, _("Translation comment has been deleted."))

    return redirect_next(request.POST.get("next"), fallback_url)


@login_required
@require_POST
def resolve_comment(request, pk):
    """Resolve comment."""
    comment_obj = get_object_or_404(Comment, pk=pk)

    if not request.user.has_perm("comment.delete", comment_obj):
        raise PermissionDenied()

    fallback_url = comment_obj.unit.get_absolute_url()

    comment_obj.resolved = True
    comment_obj.save(update_fields=["resolved"])
    messages.info(request, _("Translation comment has been resolved."))

    return redirect_next(request.POST.get("next"), fallback_url)


def get_zen_unitdata(obj, project, unit_set, request):
    """Load unit data for zen mode."""
    # Search results
    search_result = search(obj, project, unit_set, request)

    # Handle redirects
    if isinstance(search_result, HttpResponse):
        return search_result, None

    offset = search_result["offset"] - 1
    search_result["last_section"] = offset + 20 >= len(search_result["ids"])

    units = unit_set.prefetch_full().get_ordered(
        search_result["ids"][offset : offset + 20]
    )

    unitdata = [
        {
            "unit": unit,
            "secondary": (
                unit.get_secondary_units(request.user)
                if request.user.is_authenticated
                and request.user.profile.secondary_in_zen
                else None
            ),
            "form": ZenTranslationForm(
                request.user, unit, tabindex=100 + (unit.position * 10)
            ),
            "offset": offset + pos + 1,
            "glossary": get_glossary_terms(unit),
        }
        for pos, unit in enumerate(units)
    ]

    return search_result, unitdata


def zen(request, project, component, lang):
    """Generic entry point for translating, suggesting and searching."""
    obj, project, unit_set = parse_params(request, project, component, lang)

    search_result, unitdata = get_zen_unitdata(obj, project, unit_set, request)
    sort = get_sort_name(request, obj)

    # Handle redirects
    if isinstance(search_result, HttpResponse):
        return search_result

    return render(
        request,
        "zen.html",
        {
            "object": obj,
            "project": project,
            "unitdata": unitdata,
            "search_query": search_result["query"],
            "filter_name": search_result["name"],
            "filter_count": len(search_result["ids"]),
            "sort_name": sort["name"],
            "sort_query": sort["query"],
            "last_section": search_result["last_section"],
            "search_url": search_result["url"],
            "offset": search_result["offset"],
            "search_form": search_result["form"].reset_offset(),
            "is_zen": True,
        },
    )


def load_zen(request, project, component, lang):
    """Load additional units for zen editor."""
    obj, project, unit_set = parse_params(request, project, component, lang)

    search_result, unitdata = get_zen_unitdata(obj, project, unit_set, request)

    # Handle redirects
    if isinstance(search_result, HttpResponse):
        return search_result

    return render(
        request,
        "zen-units.html",
        {
            "object": obj,
            "project": project,
            "unitdata": unitdata,
            "search_query": search_result["query"],
            "search_url": search_result["url"],
            "last_section": search_result["last_section"],
        },
    )


@login_required
@require_POST
def save_zen(request, project, component, lang):
    """Save handler for zen mode."""
    _obj, _project, unit_set = parse_params(request, project, component, lang)

    checksum_form = ChecksumForm(unit_set, request.POST)
    if not checksum_form.is_valid():
        show_form_errors(request, checksum_form)
        return HttpResponseBadRequest("Invalid checksum")

    unit = checksum_form.cleaned_data["unit"]
    translationsum = ""

    form = TranslationForm(request.user, unit, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
    elif not request.user.has_perm("unit.edit", unit):
        messages.error(request, _("Insufficient privileges for saving translations."))
    else:
        perform_translation(unit, form, request)

        translationsum = hash_to_checksum(unit.get_target_hash())

    response = {
        "messages": [],
        "state": "success",
        "translationsum": translationsum,
        "unit_state_class": unit_state_class(unit) if unit else "",
        "unit_state_title": unit_state_title(unit) if unit else "",
    }

    storage = get_messages(request)
    if storage:
        response["messages"] = [
            {"tags": m.tags, "kind": get_message_kind(m.tags), "text": m.message}
            for m in storage
        ]
        tags = {m.tags for m in storage}
        if "error" in tags:
            response["state"] = "danger"
        elif "warning" in tags:
            response["state"] = "warning"
        elif "info" in tags:
            response["state"] = "info"

    return JsonResponse(data=response)


@require_POST
@login_required
def new_unit(request, project, component, lang):
    translation = get_translation(request, project, component, lang)
    if not request.user.has_perm("unit.add", translation):
        raise PermissionDenied()

    form = get_new_unit_form(translation, request.user, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
    else:
        new_unit = translation.add_unit(request, **form.as_kwargs())
        messages.success(request, _("New string has been added."))
        return redirect(new_unit)

    return redirect(translation)


@login_required
@require_POST
def delete_unit(request, unit_id):
    """Delete unit."""
    unit = get_object_or_404(Unit, pk=unit_id)

    if not request.user.has_perm("unit.delete", unit):
        raise PermissionDenied()

    unit.translation.delete_unit(request, unit)
    return redirect(unit.translation)


def browse(request, project, component, lang):
    """Strings browsing."""
    obj, project, unit_set = parse_params(request, project, component, lang)
    search_result = search(obj, project, unit_set, request, blank=True)
    offset = search_result["offset"]
    page = 20
    units = unit_set.prefetch_full().get_ordered(
        search_result["ids"][(offset - 1) * page : (offset - 1) * page + page]
    )

    base_unit_url = "{}?{}&offset=".format(
        reverse("browse", kwargs=obj.get_reverse_url_kwargs()),
        search_result["url"],
    )
    num_results = ceil(len(search_result["ids"]) / page)
    sort = get_sort_name(request, obj)

    return render(
        request,
        "browse.html",
        {
            "object": obj,
            "project": project,
            "units": units,
            "search_query": search_result["query"],
            "search_url": search_result["url"],
            "search_form": search_result["form"].reset_offset(),
            "filter_count": num_results,
            "filter_pos": offset,
            "filter_name": search_result["name"],
            "first_unit_url": base_unit_url + "1",
            "last_unit_url": base_unit_url + str(num_results),
            "next_unit_url": base_unit_url + str(offset + 1)
            if offset < num_results
            else None,
            "prev_unit_url": base_unit_url + str(offset - 1) if offset > 1 else None,
            "sort_name": sort["name"],
            "sort_query": sort["query"],
        },
    )
