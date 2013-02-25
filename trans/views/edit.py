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

from django.shortcuts import render_to_response, get_object_or_404
from django.utils.translation import ugettext as _
from django.template import RequestContext
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q

from trans.models import SubProject, Unit, Suggestion, Change, Comment
from trans.forms import (
    TranslationForm,
    MergeForm, AutoForm, ReviewForm,
    AntispamForm, CommentForm
)
from trans.views.helper import (
    get_translation, SearchOptions, bool2str, get_filter_name
)
from trans.util import join_plural
from accounts.models import Profile, send_notification_email

import logging

logger = logging.getLogger('weblate')


def translate(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    # Check locks
    project_locked, user_locked, own_lock = obj.is_locked(request, True)
    locked = project_locked or user_locked

    if request.user.is_authenticated():
        profile = request.user.get_profile()
        antispam = None
    else:
        profile = None
        antispam = AntispamForm()

    secondary = None
    unit = None

    search_options = SearchOptions(request)

    # Any form submitted?
    if request.method == 'POST':

        # Antispam protection
        if not request.user.is_authenticated():
            antispam = AntispamForm(request.POST)
            if not antispam.is_valid():
                # Silently redirect to next entry
                return HttpResponseRedirect('%s?type=%s&pos=%d%s' % (
                    obj.get_translate_url(),
                    search_options.rqtype,
                    search_options.pos,
                    search_options.url
                ))

        form = TranslationForm(request.POST)
        if form.is_valid() and not project_locked:
            # Check whether translation is not outdated
            obj.check_sync()
            try:
                try:
                    unit = Unit.objects.get(
                        checksum=form.cleaned_data['checksum'],
                        translation=obj
                    )
                except Unit.MultipleObjectsReturned:
                    # Possible temporary inconsistency caused by ongoing update
                    # of repo, let's pretend everyting is okay
                    unit = Unit.objects.filter(
                        checksum=form.cleaned_data['checksum'],
                        translation=obj
                    )[0]
                if 'suggest' in request.POST:
                    # Handle suggesion saving
                    user = request.user
                    if isinstance(user, AnonymousUser):
                        user = None
                    if form.cleaned_data['target'] == len(form.cleaned_data['target']) * ['']:
                        messages.error(request, _('Your suggestion is empty!'))
                        # Stay on same entry
                        return HttpResponseRedirect(
                            '%s?type=%s&pos=%d&dir=stay%s' % (
                                obj.get_translate_url(),
                                search_options.rqtype,
                                search_options.pos,
                                search_options.url
                            )
                        )
                    # Create the suggestion
                    sug = Suggestion.objects.create(
                        target=join_plural(form.cleaned_data['target']),
                        checksum=unit.checksum,
                        language=unit.translation.language,
                        project=unit.translation.subproject.project,
                        user=user
                    )
                    # Record in change
                    Change.objects.create(
                        unit=unit,
                        action=Change.ACTION_SUGGESTION,
                        translation=unit.translation,
                        user=user
                    )
                    # Invalidate counts cache
                    unit.translation.invalidate_cache('suggestions')
                    # Invite user to become translator if there is nobody else
                    recent_changes = Change.objects.content().filter(
                        translation=unit.translation,
                    ).exclude(
                        user=None
                    )
                    if not recent_changes.exists():
                        messages.info(
                            request,
                            _('There is currently no active translator for this translation, please consider becoming a translator as your suggestion might otherwise remain unreviewed.')
                        )
                    # Notify subscribed users
                    subscriptions = Profile.objects.subscribed_new_suggestion(
                        obj.subproject.project,
                        obj.language,
                        request.user
                    )
                    for subscription in subscriptions:
                        subscription.notify_new_suggestion(obj, sug, unit)
                    # Update suggestion stats
                    if profile is not None:
                        profile.suggested += 1
                        profile.save()
                elif not request.user.is_authenticated():
                    # We accept translations only from authenticated
                    messages.error(
                        request,
                        _('You need to log in to be able to save translations!')
                    )
                elif not request.user.has_perm('trans.save_translation'):
                    # Need privilege to save
                    messages.error(
                        request,
                        _('You don\'t have privileges to save translations!')
                    )
                elif not user_locked:
                    # Remember old checks
                    oldchecks = set(
                        unit.active_checks().values_list('check', flat=True)
                    )
                    # Update unit and save it
                    unit.target = join_plural(form.cleaned_data['target'])
                    unit.fuzzy = form.cleaned_data['fuzzy']
                    saved = unit.save_backend(request)

                    if saved:
                        # Get new set of checks
                        newchecks = set(
                            unit.active_checks().values_list('check', flat=True)
                        )
                        # Did we introduce any new failures?
                        if newchecks > oldchecks:
                            # Show message to user
                            messages.error(
                                request,
                                _('Some checks have failed on your translation!')
                            )
                            # Stay on same entry
                            return HttpResponseRedirect(
                                '%s?type=%s&pos=%d&dir=stay%s' % (
                                    obj.get_translate_url(),
                                    search_options.rqtype,
                                    search_options.pos,
                                    search_options.url
                                )
                            )

                # Redirect to next entry
                return HttpResponseRedirect('%s?type=%s&pos=%d%s' % (
                    obj.get_translate_url(),
                    search_options.rqtype,
                    search_options.pos,
                    search_options.url
                ))
            except Unit.DoesNotExist:
                logger.error(
                    'message %s disappeared!',
                    form.cleaned_data['checksum']
                )
                messages.error(
                    request,
                    _('Message you wanted to translate is no longer available!')
                )

    # Handle translation merging
    if 'merge' in request.GET and not locked:
        if not request.user.has_perm('trans.save_translation'):
            # Need privilege to save
            messages.error(
                request,
                _('You don\'t have privileges to save translations!')
            )
        else:
            try:
                mergeform = MergeForm(request.GET)
                if mergeform.is_valid():
                    try:
                        unit = Unit.objects.get(
                            checksum=mergeform.cleaned_data['checksum'],
                            translation=obj
                        )
                    except Unit.MultipleObjectsReturned:
                        # Possible temporary inconsistency caused by ongoing
                        # update of repo, let's pretend everyting is okay
                        unit = Unit.objects.filter(
                            checksum=mergeform.cleaned_data['checksum'],
                            translation=obj
                        )[0]

                    merged = Unit.objects.get(
                        pk=mergeform.cleaned_data['merge']
                    )

                    if unit.checksum != merged.checksum:
                        messages.error(
                            request,
                            _('Can not merge different messages!')
                        )
                    else:
                        # Store unit
                        unit.target = merged.target
                        unit.fuzzy = merged.fuzzy
                        saved = unit.save_backend(request)
                        # Update stats if there was change
                        if saved:
                            profile.translated += 1
                            profile.save()
                        # Redirect to next entry
                        return HttpResponseRedirect('%s?type=%s&pos=%d%s' % (
                            obj.get_translate_url(),
                            search_options.rqtype,
                            search_options.pos,
                            search_options.url
                        ))
            except Unit.DoesNotExist:
                logger.error(
                    'message %s disappeared!',
                    form.cleaned_data['checksum']
                )
                messages.error(
                    request,
                    _('Message you wanted to translate is no longer available!')
                )

    # Handle accepting/deleting suggestions
    if not locked and ('accept' in request.GET or 'delete' in request.GET):
        # Check for authenticated users
        if not request.user.is_authenticated():
            messages.error(request, _('You need to log in to be able to manage suggestions!'))
            return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                obj.get_translate_url(),
                search_options.rqtype,
                search_options.pos,
                search_options.url
            ))

        # Parse suggestion ID
        if 'accept' in request.GET:
            if not request.user.has_perm('trans.accept_suggestion'):
                messages.error(request, _('You do not have privilege to accept suggestions!'))
                return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                    obj.get_translate_url(),
                    search_options.rqtype,
                    search_options.pos,
                    search_options.url
                ))
            sugid = request.GET['accept']
        else:
            if not request.user.has_perm('trans.delete_suggestion'):
                messages.error(request, _('You do not have privilege to delete suggestions!'))
                return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                    obj.get_translate_url(),
                    search_options.rqtype,
                    search_options.pos,
                    search_options.url
                ))
            sugid = request.GET['delete']
        try:
            sugid = int(sugid)
            suggestion = Suggestion.objects.get(pk=sugid)
        except:
            suggestion = None

        if suggestion is not None:
            if 'accept' in request.GET:
                # Accept suggesiont
                suggestion.accept(request)
            # Invalidate caches
            for unit in Unit.objects.filter(checksum=suggestion.checksum):
                unit.translation.invalidate_cache('suggestions')
            # Delete suggestion in both cases (accepted ones are no longer
            # needed)
            suggestion.delete()
        else:
            messages.error(request, _('Invalid suggestion!'))

        # Redirect to same entry for possible editing
        return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
            obj.get_translate_url(),
            search_options.rqtype,
            search_options.pos,
            search_options.url
        ))

    reviewform = ReviewForm(request.GET)

    if reviewform.is_valid():
        allunits = obj.unit_set.review(
            reviewform.cleaned_data['date'],
            request.user
        )
        # Review
        if search_options.direction == 'stay':
            units = allunits.filter(
                position=search_options.pos
            )
        elif search_options.direction == 'back':
            units = allunits.filter(
                position__lt=search_options.pos
            ).order_by('-position')
        else:
            units = allunits.filter(
                position__gt=search_options.pos
            )
    elif search_options.query != '':
        # Apply search conditions
        if search_options.type == 'exact':
            query = Q()
            if search_options.source:
                query |= Q(source=search_options.query)
            if search_options.target:
                query |= Q(target=search_options.query)
            if search_options.context:
                query |= Q(context=search_options.query)
            allunits = obj.unit_set.filter(query)
        elif search_options.type == 'substring':
            query = Q()
            if search_options.source:
                query |= Q(source__icontains=search_options.query)
            if search_options.target:
                query |= Q(target__icontains=search_options.query)
            if search_options.context:
                query |= Q(context__icontains=search_options.query)
            allunits = obj.unit_set.filter(query)
        else:
            allunits = obj.unit_set.search(
                search_options.query,
                search_options.source,
                search_options.context,
                search_options.target
            )
        if search_options.direction == 'stay':
            units = obj.unit_set.filter(
                position=search_options.pos
            )
        elif search_options.direction == 'back':
            units = allunits.filter(
                position__lt=search_options.pos
            ).order_by('-position')
        else:
            units = allunits.filter(
                position__gt=search_options.pos
            )
    elif 'checksum' in request.GET:
        allunits = obj.unit_set.filter(checksum=request.GET['checksum'])
        units = allunits
    else:
        allunits = obj.unit_set.filter_type(search_options.rqtype, obj)
        # What unit set is about to show
        if search_options.direction == 'stay':
            units = obj.unit_set.filter(
                position=search_options.pos
            )
        elif search_options.direction == 'back':
            units = allunits.filter(
                position__lt=search_options.pos
            ).order_by('-position')
        else:
            units = allunits.filter(
                position__gt=search_options.pos
            )

    # If we failed to get unit above or on no POST
    if unit is None:
        # Grab actual unit
        try:
            unit = units[0]
        except IndexError:
            messages.info(request, _('You have reached end of translating.'))
            return HttpResponseRedirect(obj.get_absolute_url())

        # Show secondary languages for logged in users
        if profile:
            secondary_langs = profile.secondary_languages.exclude(
                id=unit.translation.language.id
            )
            project = unit.translation.subproject.project
            secondary = Unit.objects.filter(
                checksum=unit.checksum,
                translated=True,
                translation__subproject__project=project,
                translation__language__in=secondary_langs,
            )
            # distinct('target') works with Django 1.4 so let's emulate that
            # based on presumption we won't get too many results
            targets = {}
            res = []
            for lang in secondary:
                if lang.target in targets:
                    continue
                targets[lang.target] = 1
                res.append(lang)
            secondary = res

        # Prepare form
        form = TranslationForm(initial={
            'checksum': unit.checksum,
            'target': (unit.translation.language, unit.get_target_plurals()),
            'fuzzy': unit.fuzzy,
        })

    total = obj.unit_set.all().count()
    filter_count = allunits.count()

    return render_to_response(
        'translate.html',
        RequestContext(
            request,
            {
                'object': obj,
                'unit': unit,
                'last_changes': unit.change_set.all()[:10],
                'total': total,
                'type': search_options.rqtype,
                'filter_name': get_filter_name(
                    search_options.rqtype, search_options.query
                ),
                'filter_count': filter_count,
                'filter_pos': filter_count + 1 - units.count(),
                'form': form,
                'antispam': antispam,
                'comment_form': CommentForm(),
                'target_language': obj.language.code.replace('_', '-').lower(),
                'update_lock': own_lock,
                'secondary': secondary,
                'search_query': search_options.query,
                'search_url': search_options.url,
                'search_source': bool2str(search_options.source),
                'search_type': search_options.type,
                'search_target': bool2str(search_options.target),
                'search_context': bool2str(search_options.context),
                'locked': locked,
                'user_locked': user_locked,
                'project_locked': project_locked,
            },
        )
    )


@login_required
@permission_required('trans.automatic_translation')
def auto_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)
    obj.commit_pending()
    autoform = AutoForm(obj, request.POST)
    change = None
    if not obj.subproject.locked and autoform.is_valid():
        if autoform.cleaned_data['inconsistent']:
            units = obj.unit_set.filter_type('inconsistent', obj)
        elif autoform.cleaned_data['overwrite']:
            units = obj.unit_set.all()
        else:
            units = obj.unit_set.filter(translated=False)

        sources = Unit.objects.filter(
            translation__language=obj.language,
            translated=True
        )
        if autoform.cleaned_data['subproject'] == '':
            sources = sources.filter(
                translation__subproject__project=obj.subproject.project
            ).exclude(
                translation=obj
            )
        else:
            subprj = SubProject.objects.get(
                project=obj.subproject.project,
                slug=autoform.cleaned_data['subproject']
            )
            sources = sources.filter(translation__subproject=subprj)

        for unit in units.iterator():
            update = sources.filter(checksum=unit.checksum)
            if update.exists():
                # Get first entry
                update = update[0]
                # No save if translation is same
                if unit.fuzzy == update.fuzzy and unit.target == update.target:
                    continue
                # Copy translation
                unit.fuzzy = update.fuzzy
                unit.target = update.target
                # Create signle change object for whole merge
                if change is None:
                    change = Change.objects.create(
                        unit=unit,
                        translation=unit.translation,
                        user=request.user
                    )
                # Save unit to backend
                unit.save_backend(request, False, False)

        messages.info(request, _('Automatic translation completed.'))
    else:
        messages.error(request, _('Failed to process form!'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
def comment(request, pk):
    '''
    Adds new comment.
    '''
    obj = get_object_or_404(Unit, pk=pk)
    obj.check_acl(request)
    if request.POST.get('type', '') == 'source':
        lang = None
    else:
        lang = obj.translation.language

    form = CommentForm(request.POST)

    if form.is_valid():
        new_comment = Comment.objects.create(
            user=request.user,
            checksum=obj.checksum,
            project=obj.translation.subproject.project,
            comment=form.cleaned_data['comment'],
            language=lang
        )
        Change.objects.create(
            unit=obj,
            action=Change.ACTION_COMMENT,
            translation=obj.translation,
            user=request.user
        )

        # Invalidate counts cache
        if lang is None:
            obj.translation.invalidate_cache('sourcecomments')
        else:
            obj.translation.invalidate_cache('targetcomments')
        messages.info(request, _('Posted new comment'))
        # Notify subscribed users
        subscriptions = Profile.objects.subscribed_new_comment(
            obj.translation.subproject.project,
            lang,
            request.user
        )
        for subscription in subscriptions:
            subscription.notify_new_comment(obj, new_comment)
        # Notify upstream
        report_source_bugs = obj.translation.subproject.report_source_bugs
        if lang is None and report_source_bugs != '':
            send_notification_email(
                'en',
                report_source_bugs,
                'new_comment',
                obj.translation,
                {
                    'unit': obj,
                    'comment': new_comment,
                    'subproject': obj.translation.subproject,
                },
                from_email=request.user.email,
            )
    else:
        messages.error(request, _('Failed to add comment!'))

    return HttpResponseRedirect(obj.get_absolute_url())
