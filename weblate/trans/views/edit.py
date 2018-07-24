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

import time

from django.contrib.messages import get_messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.utils.translation import ugettext as _, ungettext
from django.utils.encoding import force_text
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string

from weblate.utils import messages
from weblate.utils.antispam import is_spam
from weblate.trans.models import Unit, Change, Comment, Suggestion, Dictionary
from weblate.trans.autofixes import fix_target
from weblate.trans.forms import (
    TranslationForm, ZenTranslationForm, SearchForm, InlineWordForm,
    MergeForm, AutoForm, AntispamForm, CommentForm, RevertForm, NewUnitForm,
)
from weblate.trans.views.helper import (
    get_translation, import_message, show_form_errors,
)
from weblate.checks import CHECKS
from weblate.trans.util import join_plural, render, redirect_next
from weblate.trans.autotranslate import AutoTranslate
from weblate.utils.hash import hash_to_checksum


def get_other_units(unit):
    """Returns other units to show while translating."""
    result = {
        'count': 0,
        'exists': False,
        'same': [],
        'matching': [],
        'context': [],
        'source': [],
    }

    kwargs = {
        'translation__component__project':
            unit.translation.component.project,
        'translation__language':
            unit.translation.language,
    }

    same = Unit.objects.same(unit, False)
    same_id = Unit.objects.prefetch().filter(
        id_hash=unit.id_hash,
        **kwargs
    )
    same_source = Unit.objects.prefetch().filter(
        source=unit.source,
        **kwargs
    )

    units = same | same_id | same_source
    units = units.distinct()

    # Is it only this unit?
    if len(units) == 1:
        return result

    for item in units:
        if item.pk == unit.pk:
            result['same'].append(item)
        elif item.source == unit.source and item.context == unit.context:
            result['matching'].append(item)
        elif item.source == unit.source:
            result['source'].append(item)
        elif item.context == unit.context:
            result['context'].append(item)

    result['count'] = len(result['matching'])
    result['exists'] = sum(
        [len(result[x]) for x in ('matching', 'source', 'context')]
    )

    return result


def cleanup_session(session):
    """Delete old search results from session storage."""
    now = int(time.time())
    keys = list(session.keys())
    for key in keys:
        if not key.startswith('search_'):
            continue
        value = session[key]
        if not isinstance(value, dict) or value['ttl'] < now:
            del session[key]


def search(translation, request):
    """Perform search or returns cached search results."""
    # Possible new search
    form = SearchForm(request.GET)

    # Process form
    if not form.is_valid():
        show_form_errors(request, form)

    search_result = {
        'form': form,
        'offset': form.cleaned_data.get('offset', 1),
        'checksum': form.cleaned_data.get('checksum'),
    }
    search_url = form.urlencode()
    session_key = 'search_{0}_{1}'.format(translation.pk, search_url)

    if session_key in request.session and 'offset' in request.GET:
        search_result.update(request.session[session_key])
        return search_result

    allunits = translation.unit_set.search(
        form.cleaned_data,
        translation=translation,
    )

    search_query = form.get_search_query()
    name = form.get_name()

    # Grab unit IDs
    unit_ids = list(allunits.values_list('id', flat=True))

    # Check empty search results
    if not unit_ids:
        messages.warning(request, _('No string matched your search!'))
        return redirect(translation)

    # Remove old search results
    cleanup_session(request.session)

    store_result = {
        'query': search_query,
        'url': search_url,
        'key': session_key,
        'name': force_text(name),
        'ids': unit_ids,
        'ttl': int(time.time()) + 86400,
    }
    request.session[session_key] = store_result

    search_result.update(store_result)
    return search_result


def perform_suggestion(unit, form, request):
    """Handle suggesion saving."""
    if form.cleaned_data['target'][0] == '':
        messages.error(request, _('Your suggestion is empty!'))
        # Stay on same entry
        return False
    elif not request.user.has_perm('suggestion.add', unit.translation):
        # Need privilege to add
        messages.error(
            request,
            _('You don\'t have privileges to add suggestions!')
        )
        # Stay on same entry
        return False
    elif not request.user.is_authenticated:
        # Spam check
        if is_spam('\n'.join(form.cleaned_data['target']), request):
            messages.error(
                request,
                _('Your suggestion has been identified as spam!')
            )
            return False

    # Create the suggestion
    result = Suggestion.objects.add(
        unit,
        join_plural(form.cleaned_data['target']),
        request,
        request.user.has_perm('suggestion.vote', unit)
    )
    if not result:
        messages.error(request, _('Your suggestion already exists!'))
    return result


def perform_translation(unit, form, request):
    """Handle translation and stores it to a backend."""
    # Remember old checks
    oldchecks = set(
        unit.active_checks().values_list('check', flat=True)
    )

    # Run AutoFixes on user input
    if not unit.translation.is_template:
        new_target, fixups = fix_target(form.cleaned_data['target'], unit)
    else:
        new_target = form.cleaned_data['target']
        fixups = []

    # Save
    saved = unit.translate(
        request,
        new_target,
        form.cleaned_data['state']
    )

    # Warn about applied fixups
    if fixups:
        messages.info(
            request,
            _('Following fixups were applied to translation: %s') %
            ', '.join([force_text(f) for f in fixups])
        )

    # Get new set of checks
    newchecks = set(
        unit.active_checks().values_list('check', flat=True)
    )

    # Did we introduce any new failures?
    if saved and newchecks > oldchecks:
        # Show message to user
        messages.error(
            request,
            _(
                'Some checks have failed on your translation: {0}'
            ).format(
                ', '.join(
                    [force_text(CHECKS[check].name) for check in newchecks]
                )
            )
        )
        # Stay on same entry
        return False

    return True


def handle_translate(translation, request, this_unit_url, next_unit_url):
    """Save translation or suggestion to database and backend."""
    # Antispam protection
    antispam = AntispamForm(request.POST)
    if not antispam.is_valid():
        # Silently redirect to next entry
        return HttpResponseRedirect(next_unit_url)

    form = TranslationForm(
        request.user, translation, None, request.POST
    )
    if not form.is_valid():
        show_form_errors(request, form)
        return None

    unit = form.cleaned_data['unit']
    go_next = True

    if 'suggest' in request.POST:
        go_next = perform_suggestion(unit, form, request)
    elif not request.user.has_perm('unit.edit', unit):
        messages.error(
            request,
            _('Insufficient privileges for saving translations.')
        )
    else:
        # Custom commit message
        message = request.POST.get('commit_message')
        if message is not None and message != unit.translation.commit_message:
            # Commit pending changes so that they don't get new message
            unit.translation.commit_pending(request)
            # Store new commit message
            unit.translation.commit_message = message
            unit.translation.save()

        go_next = perform_translation(unit, form, request)

    # Redirect to next entry
    if go_next:
        return HttpResponseRedirect(next_unit_url)
    return HttpResponseRedirect(this_unit_url)


def handle_merge(translation, request, next_unit_url):
    """Handle unit merging."""
    mergeform = MergeForm(translation, request.GET)
    if not mergeform.is_valid():
        messages.error(request, _('Invalid merge request!'))
        return None

    unit = mergeform.cleaned_data['unit']
    merged = mergeform.cleaned_data['merge_unit']

    if not request.user.has_perm('unit.edit', unit):
        messages.error(
            request,
            _('Insufficient privileges for saving translations.')
        )
        return None

    # Store unit
    saved = unit.translate(request, merged.target, merged.state)
    # Update stats if there was change
    if saved:
        request.user.profile.translated += 1
        request.user.profile.save()
    # Redirect to next entry
    return HttpResponseRedirect(next_unit_url)


def handle_revert(translation, request, next_unit_url):
    revertform = RevertForm(translation, request.GET)
    if not revertform.is_valid():
        messages.error(request, _('Invalid revert request!'))
        return None

    unit = revertform.cleaned_data['unit']
    change = revertform.cleaned_data['revert_change']

    if not request.user.has_perm('unit.edit', unit):
        messages.error(
            request,
            _('Insufficient privileges for saving translations.')
        )
        return None

    if change.target == "":
        messages.error(request, _('Can not revert to empty translation!'))
        return None
    # Store unit
    unit.translate(
        request, change.target, unit.state,
        change_action=Change.ACTION_REVERT
    )
    # Redirect to next entry
    return HttpResponseRedirect(next_unit_url)


def check_suggest_permissions(request, mode, translation, suggestion):
    """Check permission for suggestion handling."""
    user = request.user
    if mode in ('accept', 'accept_edit'):
        if not user.has_perm('suggestion.accept', translation):
            messages.error(
                request,
                _('You do not have privilege to accept suggestions!')
            )
            return False
    elif mode == 'delete':
        if not user.has_perm('suggestion.delete', suggestion, translation):
            messages.error(
                request,
                _('You do not have privilege to delete suggestions!')
            )
            return False
    elif mode in ('upvote', 'downvote'):
        if not user.has_perm('suggestion.vote', translation):
            messages.error(
                request,
                _('You do not have privilege to vote for suggestions!')
            )
            return False
    return True


def handle_suggestions(translation, request, this_unit_url, next_unit_url):
    """Handle suggestion deleting/accepting."""
    sugid = ''
    params = ('accept', 'accept_edit', 'delete', 'upvote', 'downvote')
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
        suggestion = Suggestion.objects.get(
            pk=int(sugid),
            project=translation.component.project,
            language=translation.language
        )
    except (Suggestion.DoesNotExist, ValueError):
        messages.error(request, _('Invalid suggestion!'))
        return HttpResponseRedirect(this_unit_url)

    # Permissions check
    if not check_suggest_permissions(request, mode, translation, suggestion):
        return HttpResponseRedirect(this_unit_url)

    # Perform operation
    if 'accept' in request.POST or 'accept_edit' in request.POST:
        suggestion.accept(translation, request)
        if 'accept' in request.POST:
            redirect_url = next_unit_url
    elif 'delete' in request.POST:
        suggestion.delete_log(request.user)
    elif 'upvote' in request.POST:
        suggestion.add_vote(translation, request, True)
        redirect_url = next_unit_url
    elif 'downvote' in request.POST:
        suggestion.add_vote(translation, request, False)

    return HttpResponseRedirect(redirect_url)


def translate(request, project, component, lang):
    """Generic entry point for translating, suggesting and searching."""
    translation = get_translation(request, project, component, lang)

    # Check locks
    locked = translation.component.locked

    # Search results
    search_result = search(translation, request)

    # Handle redirects
    if isinstance(search_result, HttpResponse):
        return search_result

    # Get numer of results
    num_results = len(search_result['ids'])

    # Search offset
    offset = search_result['offset']

    # Checksum unit access
    if search_result['checksum']:
        try:
            unit = translation.unit_set.get(id_hash=search_result['checksum'])
            offset = search_result['ids'].index(unit.id) + 1
        except (Unit.DoesNotExist, ValueError):
            messages.warning(request, _('No string matched your search!'))
            return redirect(translation)

    # Check boundaries
    if not 0 < offset <= num_results:
        messages.info(request, _('The translation has come to an end.'))
        # Delete search
        del request.session[search_result['key']]
        # Redirect to translation
        return redirect(translation)

    # Some URLs we will most likely use
    base_unit_url = '{0}?{1}&offset='.format(
        translation.get_translate_url(),
        search_result['url']
    )
    this_unit_url = base_unit_url + str(offset)
    next_unit_url = base_unit_url + str(offset + 1)

    response = None

    # Any form submitted?
    if 'skip' in request.POST:
        return redirect(next_unit_url)
    elif (request.method == 'POST' and
          (not locked or 'delete' in request.POST)):

        if ('accept' not in request.POST and
                'accept_edit' not in request.POST and
                'delete' not in request.POST and
                'upvote' not in request.POST and
                'downvote' not in request.POST):
            # Handle translation
            response = handle_translate(
                translation, request,
                this_unit_url, next_unit_url
            )
        elif not locked or 'delete' in request.POST:
            # Handle accepting/deleting suggestions
            response = handle_suggestions(
                translation, request, this_unit_url, next_unit_url,
            )

    # Handle translation merging
    elif 'merge' in request.GET and not locked:
        response = handle_merge(
            translation, request, next_unit_url
        )

    # Handle reverting
    elif 'revert' in request.GET and not locked:
        response = handle_revert(
            translation, request, this_unit_url
        )

    # Pass possible redirect further
    if response is not None:
        return response

    # Grab actual unit
    try:
        unit = translation.unit_set.get(pk=search_result['ids'][offset - 1])
    except Unit.DoesNotExist:
        # Can happen when using SID for other translation
        messages.error(request, _('Invalid search string!'))
        return redirect(translation)

    # Show secondary languages for logged in users
    if request.user.is_authenticated:
        secondary = unit.get_secondary_units(request.user)
    else:
        secondary = None

    # Spam protection
    antispam = AntispamForm()

    # Prepare form
    form = TranslationForm(request.user, translation, unit)

    return render(
        request,
        'translate.html',
        {
            'this_unit_url': this_unit_url,
            'first_unit_url': base_unit_url + '1',
            'last_unit_url': base_unit_url + str(num_results),
            'next_unit_url': next_unit_url,
            'prev_unit_url': base_unit_url + str(offset - 1),
            'object': translation,
            'project': translation.component.project,
            'unit': unit,
            'others': get_other_units(unit),
            'total': translation.unit_set.all().count(),
            'search_url': search_result['url'],
            'search_query': search_result['query'],
            'offset': offset,
            'filter_name': search_result['name'],
            'filter_count': num_results,
            'filter_pos': offset,
            'form': form,
            'antispam': antispam,
            'comment_form': CommentForm(),
            'search_form': search_result['form'].reset_offset(),
            'secondary': secondary,
            'locked': locked,
            'glossary': Dictionary.objects.get_words(unit),
            'addword_form': InlineWordForm(),
        }
    )


@require_POST
@login_required
def auto_translation(request, project, component, lang):
    translation = get_translation(request, project, component, lang)
    project = translation.component.project
    if not request.user.has_perm('translation.auto', project):
        raise PermissionDenied()

    autoform = AutoForm(translation, request.user, request.POST)

    if translation.component.locked or not autoform.is_valid():
        messages.error(request, _('Failed to process form!'))
        show_form_errors(request, autoform)
        return redirect(translation)

    auto = AutoTranslate(
        request.user,
        translation,
        autoform.cleaned_data['type'],
        request=request
    )

    if autoform.cleaned_data['auto_source'] == 'mt':
        auto.process_mt(
            autoform.cleaned_data['engines'],
            autoform.cleaned_data['threshold'],
        )
    else:
        auto.process_others(
            autoform.cleaned_data['component'],
        )

    import_message(
        request, auto.updated,
        _('Automatic translation completed, no strings were updated.'),
        ungettext(
            'Automatic translation completed, %d string was updated.',
            'Automatic translation completed, %d strings were updated.',
            auto.updated
        )
    )

    return redirect(translation)


@login_required
def comment(request, pk):
    """Add new comment."""
    unit = get_object_or_404(Unit, pk=pk)
    request.user.check_access(unit.translation.component.project)

    if not request.user.has_perm('comment.add', unit.translation):
        raise PermissionDenied()

    form = CommentForm(request.POST)

    if form.is_valid():
        if form.cleaned_data['scope'] == 'global':
            lang = None
        else:
            lang = unit.translation.language
        Comment.objects.add(
            unit,
            request.user,
            lang,
            form.cleaned_data['comment']
        )
        messages.success(request, _('Posted new comment'))
    else:
        messages.error(request, _('Failed to add comment!'))

    return redirect_next(request.POST.get('next'), unit)


@login_required
@require_POST
def delete_comment(request, pk):
    """Delete comment."""
    comment_obj = get_object_or_404(Comment, pk=pk)
    request.user.check_access(comment_obj.project)

    if not request.user.has_perm('comment.delete', comment_obj, comment_obj.project):
        raise PermissionDenied()

    units = comment_obj.related_units
    if units.exists():
        fallback_url = units[0].get_absolute_url()
    else:
        fallback_url = comment_obj.project.get_absolute_url()

    comment_obj.delete()
    messages.info(request, _('Translation comment has been deleted.'))

    return redirect_next(request.POST.get('next'), fallback_url)


def get_zen_unitdata(translation, request):
    """Load unit data for zen mode."""
    # Search results
    search_result = search(translation, request)

    # Handle redirects
    if isinstance(search_result, HttpResponse):
        return search_result, None

    offset = search_result['offset'] - 1
    search_result['last_section'] = offset + 20 >= len(search_result['ids'])

    units = translation.unit_set.filter(
        pk__in=search_result['ids'][offset:offset + 20]
    )

    unitdata = [
        {
            'unit': unit,
            'secondary': (
                unit.get_secondary_units(request.user)
                if request.user.is_authenticated and
                request.user.profile.secondary_in_zen
                else None
            ),
            'form': ZenTranslationForm(
                request.user,
                translation,
                unit,
                tabindex=100 + (unit.position * 10),
            ),
            'offset': offset + pos + 1,
        }
        for pos, unit in enumerate(units)
    ]

    return search_result, unitdata


def zen(request, project, component, lang):
    """Generic entry point for translating, suggesting and searching."""
    translation = get_translation(request, project, component, lang)
    search_result, unitdata = get_zen_unitdata(translation, request)

    # Handle redirects
    if isinstance(search_result, HttpResponse):
        return search_result

    return render(
        request,
        'zen.html',
        {
            'object': translation,
            'project': translation.component.project,
            'unitdata': unitdata,
            'search_query': search_result['query'],
            'filter_name': search_result['name'],
            'filter_count': len(search_result['ids']),
            'last_section': search_result['last_section'],
            'search_url': search_result['url'],
            'offset': search_result['offset'],
            'search_form': search_result['form'].reset_offset(),
        }
    )


def load_zen(request, project, component, lang):
    """Load additional units for zen editor."""
    translation = get_translation(request, project, component, lang)
    search_result, unitdata = get_zen_unitdata(translation, request)

    # Handle redirects
    if isinstance(search_result, HttpResponse):
        return search_result

    return render(
        request,
        'zen-units.html',
        {
            'object': translation,
            'unitdata': unitdata,
            'search_query': search_result['query'],
            'search_url': search_result['url'],
            'last_section': search_result['last_section'],
        }
    )


@login_required
@require_POST
def save_zen(request, project, component, lang):
    """Save handler for zen mode."""
    def render_mesage(message):
        return render_to_string(
            'message.html',
            {'tags': message.tags, 'message': message.message}
        )

    translation = get_translation(request, project, component, lang)

    form = TranslationForm(
        request.user, translation, None, request.POST
    )
    translationsum = ''
    if not form.is_valid():
        show_form_errors(request, form)
    elif not request.user.has_perm('unit.edit', form.cleaned_data['unit']):
        messages.error(
            request, _('Insufficient privileges for saving translations.')
        )
    else:
        unit = form.cleaned_data['unit']

        perform_translation(unit, form, request)

        translationsum = hash_to_checksum(unit.get_target_hash())

    response = {
        'messages': '',
        'state': 'success',
        'translationsum': translationsum,
    }

    storage = get_messages(request)
    if storage:
        response['messages'] = '\n'.join([render_mesage(m) for m in storage])
        tags = set([m.tags for m in storage])
        if 'error' in tags:
            response['state'] = 'danger'
        elif 'warning' in tags:
            response['state'] = 'warning'
        elif 'info' in tags:
            response['state'] = 'info'

    return JsonResponse(data=response)


@require_POST
@login_required
def new_unit(request, project, component, lang):
    translation = get_translation(request, project, component, lang)
    if not request.user.has_perm('unit.add', translation):
        raise PermissionDenied()

    form = NewUnitForm(request.user, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
    else:
        key = form.cleaned_data['key']
        value = form.cleaned_data['value'][0]

        if translation.unit_set.filter(context=key).exists():
            messages.error(
                request, _('Translation with this key seem to already exist!')
            )
        else:
            translation.new_unit(request, key, value)
            messages.success(
                request, _('New string has been added.')
            )

    return redirect(translation)
