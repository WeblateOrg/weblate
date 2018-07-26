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

from copy import copy
import functools
import traceback
import multiprocessing
import sys

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from django.utils.translation import ugettext as _

import six

from weblate.checks import CHECKS
from weblate.checks.models import Check
from weblate.trans.models.source import Source
from weblate.trans.models.comment import Comment
from weblate.trans.models.suggestion import Suggestion
from weblate.trans.models.change import Change
from weblate.trans.search import Fulltext
from weblate.trans.signals import unit_pre_create
from weblate.trans.mixins import LoggerMixin
from weblate.utils.errors import report_error
from weblate.trans.util import (
    is_plural, split_plural, join_plural, get_distinct_translations,
)
from weblate.utils.hash import calculate_hash, hash_to_checksum
from weblate.utils.state import (
    STATE_TRANSLATED, STATE_FUZZY, STATE_APPROVED, STATE_EMPTY,
    STATE_CHOICES
)

SIMPLE_FILTERS = {
    'fuzzy': {'state': STATE_FUZZY},
    'approved': {'state': STATE_APPROVED},
    'approved_suggestions': {
        'state': STATE_APPROVED, 'has_suggestion': True
    },
    'unapproved': {'state': STATE_TRANSLATED},
    'untranslated': {'state__lt': STATE_TRANSLATED},
    'todo': {'state__lt': STATE_TRANSLATED},
    'nottranslated': {'state': STATE_EMPTY},
    'translated': {'state__gte': STATE_TRANSLATED},
    'suggestions': {'has_suggestion': True},
    'nosuggestions': {'has_suggestion': False},
    'comments': {'has_comment': True},
}

SEARCH_FILTERS = ('source', 'target', 'context', 'location', 'comment')


def more_like_queue(pk, source, top, queue):
    """
    Multiprocess wrapper around more_like.
    """
    result = Fulltext().more_like(pk, source, top)
    queue.put(result)


class UnitManager(models.Manager):
    @staticmethod
    def update_from_unit(translation, unit, pos):
        """
        Process translation toolkit unit and stores/updates database entry.
        """
        # Get basic unit data
        src = unit.get_source()
        ctx = unit.get_context()
        id_hash = unit.get_id_hash()
        content_hash = unit.get_content_hash()
        created = False

        # Try getting existing unit
        created = False
        try:
            dbunit = translation.unit_set.get(id_hash=id_hash)
        except Unit.MultipleObjectsReturned:
            # Some inconsistency (possibly race condition), try to recover
            translation.unit_set.filter(id_hash=id_hash).delete()
            dbunit = None
        except Unit.DoesNotExist:
            dbunit = None

        # Create unit if it does not exist
        if dbunit is None:
            dbunit = Unit(
                translation=translation,
                id_hash=id_hash,
                content_hash=content_hash,
                source=src,
                context=ctx
            )
            created = True

        # Update all details
        dbunit.update_from_unit(unit, pos, created)

        # Return result
        return dbunit, created


class UnitQuerySet(models.QuerySet):
    def filter_checks(self, rqtype, project, language, ignored=False,
                      strict=False):
        """Filtering for checks."""

        # Filter checks for current project
        checks = Check.objects.filter(
            ignore=ignored
        )

        if project is not None:
            checks = checks.filter(project=project)

        # Filter by language
        if rqtype == 'allchecks':
            return self.filter(has_failing_check=True)
        elif rqtype == 'sourcechecks':
            checks = checks.filter(language=None)
        elif rqtype.startswith('check:'):
            check_id = rqtype[6:]
            if check_id not in CHECKS:
                if strict:
                    raise ValueError('Unknown check: {}'.format(check_id))
                return self.all()
            if CHECKS[check_id].source:
                checks = checks.filter(language=None)
            elif CHECKS[check_id].target and language is not None:
                checks = checks.filter(language=language)
            # Filter by check type
            checks = checks.filter(check=check_id)

        checks = checks.values_list('content_hash', flat=True)
        return self.filter(content_hash__in=checks)

    def filter_type(self, rqtype, project, language, ignored=False,
                    strict=False):
        """Basic filtering based on unit state or failed checks."""
        if rqtype in SIMPLE_FILTERS:
            return self.filter(**SIMPLE_FILTERS[rqtype])
        elif rqtype == 'sourcecomments':
            coms = Comment.objects.filter(
                language=None,
            )
            if project is not None:
                coms = coms.filter(project=project)
            coms = coms.values_list('content_hash', flat=True)
            return self.filter(content_hash__in=coms)
        elif (rqtype.startswith('check:') or
              rqtype in ['allchecks', 'sourcechecks']):
            return self.filter_checks(
                rqtype,
                project,
                language,
                ignored,
                strict=strict
            )
        elif rqtype == 'all':
            return self.all()
        elif strict:
            raise ValueError('Unknown filter: {}'.format(rqtype))
        else:
            # Catch anything not matching
            return self.all()

    def review(self, date, exclude_user, only_user,
               project=None, component=None, language=None, translation=None):
        """Return units touched by other users since given time."""
        # Filter out changes we're interested in
        changes = Change.objects.content()
        if date:
            changes = changes.filter(timestamp__gte=date)
        if exclude_user:
            changes = changes.exclude(user=exclude_user)
        if only_user:
            changes = changes.filter(user=only_user)
        if translation:
            changes = changes.filter(translation=translation)
        else:
            if component:
                changes = changes.filter(component=component)
            elif project:
                changes = changes.filter(component__project=project)
            if language:
                changes = changes.filter(translation__language=language)
        # Filter units for these changes
        return self.filter(change__in=changes).distinct()

    def prefetch(self):
        return self.prefetch_related(
            'translation',
            'translation__language',
            'translation__plural',
            'translation__component',
            'translation__component__project',
            'translation__component__project__source_language',
        )

    def search(self, params, project=None, component=None,
               language=None, translation=None):
        """High level wrapper for searching."""
        if translation is not None:
            component = translation.component
            language = translation.language
        if component is not None:
            project = component.project

        base = self.prefetch()
        if params['type'] != 'all':
            base = self.filter_type(
                params['type'],
                project,
                language,
                params.get('ignored', False)
            )

        if (params.get('date') or
                params.get('exclude_user') or
                params.get('only_user')):
            base = base.review(
                params.get('date'),
                params.get('exclude_user'),
                params.get('only_user'),
                project, component, language, translation
            )

        if 'lang' in params and params['lang']:
            base = base.filter(translation__language__code__in=params['lang'])

        if 'q' not in params or not params['q']:
            result = base

        elif params['search'] in ('exact', 'substring'):
            queries = []

            modifier = ''
            if params['search'] != 'exact':
                modifier = '__icontains'

            for param in SEARCH_FILTERS:
                if param in params and params[param]:
                    queries.append(param)

            query = functools.reduce(
                lambda q, value:
                q | Q(**{'{0}{1}'.format(value, modifier): params['q']}),
                queries,
                Q()
            )

            result = base.filter(query)
        else:
            langs = set(self.values_list(
                'translation__language__code', flat=True
            ))
            result = base.filter(
                pk__in=Fulltext().search(
                    params['q'],
                    langs,
                    params
                )
            )
        return result

    def more_like_this(self, unit, top=5):
        """Find closely similar units."""
        if settings.MT_WEBLATE_LIMIT >= 0:
            queue = multiprocessing.Queue()
            proc = multiprocessing.Process(
                target=more_like_queue,
                args=(unit.pk, unit.source, top, queue)
            )
            proc.start()
            proc.join(settings.MT_WEBLATE_LIMIT)
            if proc.is_alive():
                proc.terminate()

            if queue.empty():
                raise Exception(
                    'Request for more like {0} timed out.'.format(unit.pk)
                )

            more_results = queue.get()
        else:
            more_results = Fulltext().more_like(unit.pk, unit.source, top)

        return self.filter(
            pk__in=more_results,
            translation__language=unit.translation.language,
            state__gte=STATE_TRANSLATED,
        )

    def same(self, unit, exclude=True):
        """Unit with same source within same project."""
        project = unit.translation.component.project
        result = self.prefetch().filter(
            content_hash=unit.content_hash,
            translation__component__project=project,
            translation__language=unit.translation.language
        )
        if exclude:
            result = result.exclude(
                pk=unit.id
            )
        return result

    def get_unit(self, ttunit):
        """Find unit matching translate-toolkit unit

        This is used for import, so kind of fuzzy matching is expected.
        """
        source = ttunit.get_source()
        context = ttunit.get_context()

        params = [{'source': source, 'context': context}, {'source': source}]
        # Try empty context first before matching any context
        if context != '':
            params.insert(1, {'source': source, 'context': ''})
        # Special case for XLIFF
        if '///' in context:
            params.insert(
                1, {'source': source, 'context': context.split('///', 1)[1]}
            )

        for param in params:
            try:
                return self.get(**param)
            except (Unit.DoesNotExist, Unit.MultipleObjectsReturned):
                continue

        raise Unit.DoesNotExist('No matching unit found!')


@python_2_unicode_compatible
class Unit(models.Model, LoggerMixin):

    translation = models.ForeignKey(
        'Translation', on_delete=models.deletion.CASCADE
    )
    id_hash = models.BigIntegerField()
    content_hash = models.BigIntegerField(db_index=True)
    location = models.TextField(default='', blank=True)
    context = models.TextField(default='', blank=True)
    comment = models.TextField(default='', blank=True)
    flags = models.TextField(default='', blank=True)
    source = models.TextField()
    previous_source = models.TextField(default='', blank=True)
    target = models.TextField(default='', blank=True)
    state = models.IntegerField(
        default=STATE_EMPTY,
        db_index=True,
        choices=STATE_CHOICES,
    )

    position = models.IntegerField()

    has_suggestion = models.BooleanField(default=False, db_index=True)
    has_comment = models.BooleanField(default=False, db_index=True)
    has_failing_check = models.BooleanField(default=False, db_index=True)

    num_words = models.IntegerField(default=0)

    priority = models.IntegerField(default=100)

    pending = models.BooleanField(default=False)

    objects = UnitManager.from_queryset(UnitQuerySet)()

    class Meta(object):
        ordering = ['priority', 'position']
        app_label = 'trans'
        unique_together = ('translation', 'id_hash')
        index_together = [
            ('translation', 'pending'),
            ('priority', 'position'),
        ]

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super(Unit, self).__init__(*args, **kwargs)
        self.old_unit = copy(self)

    def __str__(self):
        return _('{translation}, string {position}').format(
            translation=self.translation,
            position=self.position,
        )

    @property
    def approved(self):
        return self.state == STATE_APPROVED

    @property
    def translated(self):
        return self.state >= STATE_TRANSLATED

    @property
    def fuzzy(self):
        return self.state == STATE_FUZZY

    @cached_property
    def log_prefix(self):
        return '/'.join((
            self.translation.component.project.slug,
            self.translation.component.slug,
            self.translation.language.code,
            str(self.pk)
        ))

    def get_absolute_url(self):
        return '{0}?checksum={1}'.format(
            self.translation.get_translate_url(), self.checksum
        )

    def get_unit_state(self, unit, created):
        """Calculate translated and fuzzy status"""
        translated = unit.is_translated()
        # We need to keep approved/fuzzy state for formats which do not
        # support saving it
        fuzzy = unit.is_fuzzy(self.fuzzy)
        approved = unit.is_approved(self.approved)

        if fuzzy:
            return STATE_FUZZY
        if not translated:
            return STATE_EMPTY
        elif approved and self.translation.component.project.enable_review:
            return STATE_APPROVED
        return STATE_TRANSLATED

    def update_from_unit(self, unit, pos, created):
        """Update Unit from ttkit unit."""
        # Get unit attributes
        location = unit.get_locations()
        flags = unit.get_flags()
        target = unit.get_target()
        source = unit.get_source()
        comment = unit.get_comments()
        state = self.get_unit_state(unit, created)
        previous_source = unit.get_previous_source()
        content_hash = unit.get_content_hash()

        # Monolingual files handling (without target change)
        if unit.template is not None and target == self.target:
            if source != self.source and state == STATE_TRANSLATED:
                if self.previous_source == self.source and self.fuzzy:
                    # Source change was reverted
                    previous_source = ''
                    state = STATE_TRANSLATED
                else:
                    # Store previous source and fuzzy flag for monolingual
                    if previous_source == '':
                        previous_source = self.source
                    state = STATE_FUZZY
            else:
                # We should keep calculated flags if translation was
                # not changed outside
                previous_source = self.previous_source
                state = self.state

        # Update checks on fuzzy update or on content change
        same_content = (
            target == self.target and source == self.source
        )
        same_state = (state == self.state and not created)

        # Check if we actually need to change anything
        # pylint: disable=too-many-boolean-expressions
        if (not created and
                location == self.location and
                flags == self.flags and
                same_content and same_state and
                comment == self.comment and
                pos == self.position and
                content_hash == self.content_hash and
                previous_source == self.previous_source):
            return

        # Ensure we track source string
        source_info, source_created = Source.objects.get_or_create(
            id_hash=self.id_hash,
            component=self.translation.component
        )
        contentsum_changed = self.content_hash != content_hash

        # Store updated values
        self.position = pos
        self.location = location
        self.flags = flags
        self.source = source
        self.target = target
        self.state = state
        self.comment = comment
        self.content_hash = content_hash
        self.previous_source = previous_source
        self.priority = source_info.priority

        # Sanitize number of plurals
        if self.is_plural():
            self.target = join_plural(self.get_target_plurals())

        if created:
            unit_pre_create.send(sender=self.__class__, unit=self)

        # Save into database
        self.save(
            force_insert=created,
            backend=True,
            same_content=same_content,
            same_state=same_state,
        )

        # Create change object for new source string
        if source_created:
            Change.objects.create(
                action=Change.ACTION_NEW_SOURCE,
                unit=self,
            )
        if contentsum_changed:
            self.update_has_failing_check(recurse=False)
            self.update_has_comment()
            self.update_has_suggestion()

    def is_plural(self):
        """Check whether message is plural."""
        return is_plural(self.source) or is_plural(self.target)

    def get_source_plurals(self):
        """Return source plurals in array."""
        return split_plural(self.source)

    def get_target_plurals(self):
        """Return target plurals in array."""
        # Is this plural?
        if not self.is_plural():
            return [self.target]

        # Split plurals
        ret = split_plural(self.target)

        # Check if we have expected number of them
        plurals = self.translation.plural.number
        if len(ret) == plurals:
            return ret

        # Pad with empty translations
        while len(ret) < plurals:
            ret.append('')

        # Delete extra plurals
        while len(ret) > plurals:
            del ret[-1]

        return ret

    def propagate(self, request, change_action=None):
        """Propagate current translation to all others."""
        allunits = Unit.objects.same(self).filter(
            translation__component__allow_translation_propagation=True
        )
        for unit in allunits:
            if not request.user.has_perm('unit.edit', unit):
                continue
            unit.target = self.target
            unit.state = self.state
            unit.save_backend(request, False, change_action=change_action)

    def save_backend(self, request, propagate=True, change_action=None,
                     user=None):
        """
        Stores unit to backend.

        Optional user parameters defines authorship of a change.

        This should be always called in a trasaction with updated unit
        locked for update.
        """
        # For case when authorship specified, use user from request
        if user is None or (user.is_anonymous and request):
            user = request.user

        # Commit possible previous changes on this unit
        if self.pending:
            try:
                change = self.change_set.content().order_by('-timestamp')[0]
            except IndexError as error:
                # This is probably bug in the change data, fallback by using
                # any change entry
                report_error(error, sys.exc_info(), request)
                change = self.change_set.all().order_by('-timestamp')[0]
            if change.author_id != request.user.id:
                self.translation.commit_pending(request)

        # Return if there was no change
        # We have to explicitly check for fuzzy flag change on monolingual
        # files, where we handle it ourselves without storing to backend
        if (self.old_unit.state == self.state and
                self.old_unit.target == self.target):
            # Propagate if we should
            if propagate:
                self.propagate(request, change_action)
            return False

        # Propagate to other projects
        # This has to be done before changing source/content_hash for template
        if propagate:
            self.propagate(request, change_action)

        if self.translation.is_template:
            self.source = self.target
            self.content_hash = calculate_hash(self.source, self.context)

        # Unit is pending for write
        self.pending = True
        # Update translated flag (not fuzzy and at least one translation)
        translation = bool(max(self.get_target_plurals()))
        if self.state == STATE_TRANSLATED and not translation:
            self.state = STATE_EMPTY
        elif self.state == STATE_EMPTY and translation:
            self.state = STATE_TRANSLATED

        # Save updated unit to database
        self.save(backend=True)

        old_translated = self.translation.stats.translated

        if change_action not in (Change.ACTION_UPLOAD, Change.ACTION_AUTO):
            # Update translation stats
            self.translation.invalidate_cache()

            # Update user stats
            user.profile.translated += 1
            user.profile.save()

        # Notify subscribed users about new translation
        from weblate.accounts.notifications import notify_new_translation
        notify_new_translation(self, self.old_unit, user)

        # Generate Change object for this change
        self.generate_change(request, user, change_action)

        # Force commiting on completing translation
        translated = self.translation.stats.translated
        if (old_translated < translated and
                translated == self.translation.stats.all):
            Change.objects.create(
                translation=self.translation,
                action=Change.ACTION_COMPLETE,
                user=user,
                author=user
            )
            self.translation.commit_pending(request)

        # Update related source strings if working on a template
        if self.translation.is_template:
            self.update_source_units(self.old_unit.source, user)

        return True

    def update_source_units(self, previous_source, user):
        """Update source for units withing same component.

        This is needed when editing template translation for monolingual
        formats.
        """
        # Find relevant units
        same_source = Unit.objects.filter(
            translation__component=self.translation.component,
            id_hash=self.id_hash,
        ).exclude(
            id=self.id
        )
        # Update source, number of words and content_hash
        same_source.update(
            source=self.source,
            num_words=self.num_words,
            content_hash=self.content_hash
        )
        # Find reverted units
        reverted = same_source.filter(
            state=STATE_FUZZY,
            previous_source=self.source
        )
        reverted_ids = set(reverted.values_list('id', flat=True))
        reverted.update(
            state=STATE_TRANSLATED,
            previous_source=''
        )
        # Set fuzzy on changed
        same_source.filter(
            state=STATE_TRANSLATED
        ).exclude(
            id__in=reverted_ids
        ).update(
            state=STATE_FUZZY,
            previous_source=previous_source,
        )
        # Update source index and stats
        for unit in same_source.iterator():
            unit.update_has_comment()
            unit.update_has_suggestion()
            unit.run_checks(False, False)
            Fulltext.update_index_unit(unit)
            Change.objects.create(
                unit=unit,
                action=Change.ACTION_SOURCE_CHANGE,
                user=user,
                author=user,
                old=previous_source,
                target=self.source,
            )
            unit.translation.invalidate_cache()

    def generate_change(self, request, author, change_action):
        """Create Change entry for saving unit."""
        user = request.user if request else author
        # Notify about new contributor
        user_changes = Change.objects.filter(
            translation=self.translation,
            user=user
        )
        if not user_changes.exists():
            from weblate.accounts.notifications import notify_new_contributor
            notify_new_contributor(self, user)

        # Action type to store
        if change_action is not None:
            action = change_action
        elif self.old_unit.state >= STATE_TRANSLATED:
            action = Change.ACTION_CHANGE
        else:
            action = Change.ACTION_NEW

        kwargs = {}

        # Should we store history of edits?
        if self.translation.component.save_history:
            kwargs['target'] = self.target
            kwargs['old'] = self.old_unit.target

        # Create change object
        Change.objects.create(
            unit=self,
            action=action,
            user=user,
            author=author,
            **kwargs
        )

    def save(self, same_content=False, same_state=False, force_insert=False,
             backend=False, **kwargs):
        """
        Wrapper around save to warn when save did not come from
        git backend (eg. commit or by parsing file).
        """
        # Warn if request is not coming from backend
        if not backend:
            self.log_error(
                'Unit.save called without backend sync: %s',
                ''.join(traceback.format_stack())
            )

        # Store number of words
        if not same_content or not self.num_words:
            self.num_words = len(self.get_source_plurals()[0].split())

        # Actually save the unit
        super(Unit, self).save(**kwargs)

        # Update checks if content or fuzzy flag has changed
        if not same_content or not same_state:
            self.run_checks(same_state, same_content, force_insert)

        # Update fulltext index if content has changed or this is a new unit
        if force_insert or not same_content:
            Fulltext.update_index_unit(self)

    @cached_property
    def suggestions(self):
        """Return all suggestions for this unit."""
        return Suggestion.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=self.translation.language
        )

    def cleanup_checks(self, source, target):
        """Cleanup listed source and target checks."""
        # Short circuit if there is nothing to cleanup
        if not source and not target:
            return False
        todelete = Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project
        ).filter(
            (Q(language=self.translation.language) & Q(check__in=target)) |
            (Q(language=None) & Q(check__in=source))
        )
        result = todelete.delete()
        return result[0] > 0

    def checks(self):
        """Return all checks for this unit (even ignored)."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=self.translation.language
        )

    def source_checks(self):
        """Return all source checks for this unit (even ignored)."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=None
        )

    def active_checks(self):
        """Return all active (not ignored) checks for this unit."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=self.translation.language,
            ignore=False
        )

    def active_source_checks(self):
        """Return all active (not ignored) source checks for this unit."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=None,
            ignore=False
        )

    def get_comments(self):
        """Return list of target comments."""
        return Comment.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
        ).filter(
            Q(language=self.translation.language) | Q(language=None),
        )

    def get_source_comments(self):
        """Return list of target comments."""
        return Comment.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=None,
        )

    def get_checks_to_run(self, same_state, is_new):
        """
        Returns list of checks to run on state change.

        Returns tuple of checks to run and whether to do cleanup.
        """
        # Run only source checks on template
        if self.translation.is_template:
            return {x: y for x, y in CHECKS.data.items() if y.source}, True

        checks_to_run = CHECKS.data
        cleanup_checks = True

        if (not same_state or is_new) and self.state < STATE_TRANSLATED:
            # Check whether there is any message with same source
            project = self.translation.component.project
            same_source = Unit.objects.filter(
                translation__language=self.translation.language,
                translation__component__project=project,
                content_hash=self.content_hash,
                state__gte=STATE_TRANSLATED,
            ).exclude(
                id=self.id,
                translation__component__allow_translation_propagation=False,
            )

            # We run only checks which span across more units
            checks_to_run = {}

            # Delete all checks if only message with this source is fuzzy
            if not same_source.exists():
                checks = self.checks()
                if checks.exists():
                    checks.delete()
                    self.update_has_failing_check(True)
            elif 'inconsistent' in CHECKS:
                # Consistency check checks across more translations
                checks_to_run['inconsistent'] = CHECKS['inconsistent']

            # Run source checks as well
            for check in CHECKS:
                if CHECKS[check].source:
                    checks_to_run[CHECKS[check].check_id] = CHECKS[check]

            cleanup_checks = False

        return checks_to_run, cleanup_checks

    def run_checks(self, same_state=True, same_content=True, is_new=False):
        """Update checks for this unit."""
        was_change = False

        checks_to_run, cleanup_checks = self.get_checks_to_run(
            same_state, is_new
        )

        src = self.get_source_plurals()
        tgt = self.get_target_plurals()
        old_target_checks = set(
            self.checks().values_list('check', flat=True)
        )
        old_source_checks = set(
            self.source_checks().values_list('check', flat=True)
        )

        # Run all target checks
        for check, check_obj in checks_to_run.items():
            if check_obj.target and check_obj.check_target(src, tgt, self):
                if check in old_target_checks:
                    # We already have this check
                    old_target_checks.remove(check)
                else:
                    # Create new check
                    Check.objects.create(
                        content_hash=self.content_hash,
                        project=self.translation.component.project,
                        language=self.translation.language,
                        ignore=False,
                        check=check,
                        for_unit=self.pk
                    )
                    was_change = True
        # Run all source checks
        for check, check_obj in checks_to_run.items():
            if check_obj.source and check_obj.check_source(src, self):
                if check in old_source_checks:
                    # We already have this check
                    old_source_checks.remove(check)
                else:
                    # Create new check
                    Check.objects.create(
                        content_hash=self.content_hash,
                        project=self.translation.component.project,
                        language=None,
                        ignore=False,
                        check=check
                    )
                    was_change = True

        # Delete no longer failing checks
        if cleanup_checks:
            was_change |= self.cleanup_checks(
                old_source_checks, old_target_checks
            )

        # Update failing checks flag
        if was_change or is_new or not same_content:
            self.update_has_failing_check(was_change)

    def update_has_failing_check(self, recurse=False):
        """Update flag counting failing checks."""
        has_failing_check = (
            self.state >= STATE_TRANSLATED and
            self.active_checks().exists()
        )

        # Change attribute if it has changed
        if has_failing_check != self.has_failing_check:
            self.has_failing_check = has_failing_check
            self.save(
                backend=True, same_content=True, same_state=True,
                update_fields=['has_failing_check']
            )

        if recurse:
            for unit in Unit.objects.same(self):
                unit.update_has_failing_check(False)

    def update_has_suggestion(self):
        """Update flag counting suggestions."""
        if 'suggestions' in self.__dict__:
            del self.__dict__['suggestions']
        has_suggestion = len(self.suggestions) > 0
        if has_suggestion != self.has_suggestion:
            self.has_suggestion = has_suggestion
            self.save(
                backend=True, same_content=True, same_state=True,
                update_fields=['has_suggestion']
            )

    def update_has_comment(self):
        """Update flag counting comments."""
        has_comment = len(self.get_comments()) > 0
        if has_comment != self.has_comment:
            self.has_comment = has_comment
            self.save(
                backend=True, same_content=True, same_state=True,
                update_fields=['has_comment']
            )

    def nearby(self):
        """Return list of nearby messages based on location."""
        return Unit.objects.prefetch().filter(
            translation=self.translation,
            position__gte=self.position - settings.NEARBY_MESSAGES,
            position__lte=self.position + settings.NEARBY_MESSAGES,
        )

    @transaction.atomic
    def translate(self, request, new_target, new_state, change_action=None,
                  propagate=True):
        """Store new translation of a unit."""
        # Fetch current copy from database and lock it for update
        self.old_unit = Unit.objects.select_for_update().get(pk=self.pk)

        # Update unit and save it
        if isinstance(new_target, six.string_types):
            self.target = new_target
            not_empty = bool(new_target)
        else:
            self.target = join_plural(new_target)
            not_empty = bool(max(new_target))
        if not_empty:
            self.state = new_state
        else:
            self.state = STATE_EMPTY
        saved = self.save_backend(
            request,
            change_action=change_action,
            propagate=propagate
        )

        return saved

    @cached_property
    def all_flags(self):
        """Return union of own and component flags."""
        flags = set(
            self.flags.split(',') +
            self.source_info.check_flags.split(',') +
            self.translation.component.all_flags
        )
        flags.discard('')
        return flags

    @property
    def source_info(self):
        """Return related source string object."""
        return Source.objects.get(
            id_hash=self.id_hash,
            component=self.translation.component
        )

    def get_secondary_units(self, user):
        """Return list of secondary units."""
        secondary_langs = user.profile.secondary_languages.exclude(
            id=self.translation.language.id
        )
        return get_distinct_translations(
            Unit.objects.filter(
                id_hash=self.id_hash,
                state__gte=STATE_TRANSLATED,
                translation__component=self.translation.component,
                translation__language__in=secondary_langs,
            )
        )

    @property
    def checksum(self):
        """Return unique hex identifier

        It's unsigned representation of id_hash in hex.
        """
        return hash_to_checksum(self.id_hash)

    def same_units(self):
        return Unit.objects.same(self)

    def get_max_length(self):
        """Returns maximal translation length."""
        if not self.pk:
            return 10000
        for flag in self.all_flags:
            if flag.startswith('max-length:'):
                try:
                    return int(flag[11:])
                except ValueError:
                    continue
        # Fallback to reasonably big value
        return len(self.get_source_plurals()[0]) * 10

    def get_target_hash(self):
        return calculate_hash(None, self.target)
