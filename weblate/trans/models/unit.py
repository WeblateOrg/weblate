# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import ugettext as _
from django.utils.encoding import python_2_unicode_compatible
from django.core.cache import cache

from weblate.utils import messages
from weblate.trans.checks import CHECKS
from weblate.trans.models.source import Source
from weblate.trans.models.check import Check
from weblate.trans.models.comment import Comment
from weblate.trans.models.suggestion import Suggestion
from weblate.trans.models.change import Change
from weblate.trans.search import update_index_unit, fulltext_search, more_like
from weblate.accounts.notifications import (
    notify_new_contributor, notify_new_translation
)
from weblate.trans.filelock import FileLockException
from weblate.trans.mixins import LoggerMixin
from weblate.trans.util import (
    is_plural, split_plural, join_plural, get_distinct_translations,
)
from weblate.utils.hash import calculate_hash, hash_to_checksum


SIMPLE_FILTERS = {
    'fuzzy': {'fuzzy': True},
    'untranslated': {'translated': False},
    'todo': {'translated': False},
    'nottranslated': {'translated': False, 'fuzzy': False},
    'translated': {'translated': True},
    'suggestions': {'has_suggestion': True},
    'comments': {'has_comment': True},
}

SEARCH_FILTERS = ('source', 'target', 'context', 'location', 'comment')


def more_like_queue(pk, source, top, queue):
    """
    Multiprocess wrapper around more_like.
    """
    result = more_like(pk, source, top)
    queue.put(result)


class UnitManager(models.Manager):
    # pylint: disable=W0232

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

    def filter_checks(self, rqtype, translation, ignored=False):
        """Filtering for checks."""

        # Filter checks for current project
        checks = Check.objects.filter(
            ignore=ignored
        )

        if translation is not None:
            checks = checks.filter(
                project=translation.subproject.project,
            )

        filter_translated = True

        # Filter by language
        if rqtype == 'allchecks':
            return self.filter(has_failing_check=True)
        elif rqtype == 'sourcechecks':
            checks = checks.filter(language=None)
            filter_translated = False
        elif rqtype.startswith('check:'):
            check_id = rqtype[6:]
            if check_id not in CHECKS:
                return self.all()
            if CHECKS[check_id].source:
                checks = checks.filter(language=None)
                filter_translated = False
            elif CHECKS[check_id].target and translation is not None:
                checks = checks.filter(language=translation.language)
            # Filter by check type
            checks = checks.filter(check=check_id)

        checks = checks.values_list('content_hash', flat=True)
        ret = self.filter(content_hash__in=checks)
        if filter_translated:
            ret = ret.filter(translated=True)
        return ret

    def filter_type(self, rqtype, translation, ignored=False):
        """Basic filtering based on unit state or failed checks."""
        if rqtype in SIMPLE_FILTERS:
            return self.filter(**SIMPLE_FILTERS[rqtype])
        elif rqtype == 'random':
            return self.filter(translated=True).order_by('?')
        elif rqtype == 'sourcecomments':
            coms = Comment.objects.filter(
                language=None,
            )
            if translation is not None:
                coms = coms.filter(
                    project=translation.subproject.project
                )
            coms = coms.values_list('content_hash', flat=True)
            return self.filter(content_hash__in=coms)
        elif rqtype.startswith('check:'):
            return self.filter_checks(rqtype, translation, ignored)
        elif rqtype in ['allchecks', 'sourcechecks']:
            return self.filter_checks(rqtype, translation, ignored)
        else:
            # Catch anything not matching including 'all'
            return self.all()

    def count_type(self, rqtype, translation):
        """Cached counting of failing checks (and other stats)."""
        # Try to get value from cache
        cache_key = 'counts-{0}-{1}-{2}'.format(
            translation.subproject.get_full_slug(),
            translation.language.code,
            rqtype
        )
        ret = cache.get(cache_key)
        if ret is not None:
            return ret

        # Actually count units
        ret = self.filter_type(rqtype, translation).count()

        # Update cache
        cache.set(cache_key, ret)
        return ret

    def review(self, date, user):
        """Return units touched by other users since given time."""
        if user.is_anonymous:
            return self.none()
        try:
            sample = self.all()[0]
        except IndexError:
            return self.none()
        changes = Change.objects.content().filter(
            translation=sample.translation,
            timestamp__gte=date
        ).exclude(user=user)
        return self.filter(id__in=changes.values_list('unit__id', flat=True))

    def prefetch(self):
        return self.prefetch_related(
            'translation',
            'translation__language',
            'translation__subproject',
            'translation__subproject__project',
            'translation__subproject__project__source_language',
        )

    def search(self, translation, params):
        """High level wrapper for searching."""
        base = self.prefetch()
        if params['type'] != 'all':
            base = self.filter_type(
                params['type'],
                translation,
                params['ignored']
            )

        if 'lang' in params and params['lang']:
            base = base.filter(translation__language__code=params['lang'])

        if not params['q']:
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
            lang = self.values_list(
                'translation__language__code', flat=True
            )[0]
            result = base.filter(
                pk__in=fulltext_search(
                    params['q'],
                    lang,
                    params
                )
            )
        return result

    def same_source(self, unit):
        """Find units with same source."""
        pks = fulltext_search(
            unit.get_source_plurals()[0],
            unit.translation.language.code,
            {'source': True}
        )

        return self.filter(
            pk__in=pks,
            translation__language=unit.translation.language,
            translated=True
        ).exclude(
            pk=unit.id
        )

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
                raise Exception('Request timed out.')

            more_results = queue.get()
        else:
            more_results = more_like(unit.pk, unit.source, top)

        same_results = fulltext_search(
            unit.get_source_plurals()[0],
            unit.translation.language.code,
            {'source': True}
        )

        return self.filter(
            pk__in=more_results - same_results,
            translation__language=unit.translation.language,
            translated=True
        ).exclude(
            pk=unit.id
        )

    def same(self, unit, exclude=True):
        """Unit with same source within same project."""
        project = unit.translation.subproject.project
        result = self.prefetch().filter(
            content_hash=unit.content_hash,
            translation__subproject__project=project,
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
        if context != '':
            params.insert(1, {'source': source, 'context': ''})

        for param in params:
            try:
                return self.get(**param)
            except (Unit.DoesNotExist, Unit.MultipleObjectsReturned):
                continue

        raise Unit.DoesNotExist('No matching unit found!')


@python_2_unicode_compatible
class Unit(models.Model, LoggerMixin):
    translation = models.ForeignKey('Translation')
    id_hash = models.BigIntegerField(db_index=True)
    content_hash = models.BigIntegerField(db_index=True)
    location = models.TextField(default='', blank=True)
    context = models.TextField(default='', blank=True)
    comment = models.TextField(default='', blank=True)
    flags = models.TextField(default='', blank=True)
    source = models.TextField()
    previous_source = models.TextField(default='', blank=True)
    target = models.TextField(default='', blank=True)
    fuzzy = models.BooleanField(default=False, db_index=True)
    translated = models.BooleanField(default=False, db_index=True)
    position = models.IntegerField(db_index=True)

    has_suggestion = models.BooleanField(default=False, db_index=True)
    has_comment = models.BooleanField(default=False, db_index=True)
    has_failing_check = models.BooleanField(default=False, db_index=True)

    num_words = models.IntegerField(default=0)

    priority = models.IntegerField(default=100, db_index=True)

    objects = UnitManager()

    class Meta(object):
        permissions = (
            ('save_translation', "Can save translation"),
            ('save_template', "Can save template"),
        )
        ordering = ['priority', 'position']
        app_label = 'trans'
        unique_together = ('translation', 'id_hash')

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super(Unit, self).__init__(*args, **kwargs)
        self._all_flags = None
        self._source_info = None
        self._suggestions = None
        self.old_unit = copy(self)

    def __str__(self):
        return '{0} on {1}'.format(
            self.checksum,
            self.translation
        )

    @property
    def log_prefix(self):
        return '/'.join((
            self.translation.subproject.project.slug,
            self.translation.subproject.slug,
            self.translation.language.code,
            str(self.pk)
        ))

    def get_absolute_url(self):
        return '{0}?checksum={1}'.format(
            self.translation.get_translate_url(), self.checksum
        )

    def get_unit_status(self, unit, target, created):
        """Calculate translated and fuzzy status"""
        all_flags = self.translation.subproject.all_flags

        if 'skip-review-flag' in all_flags:
            return bool(target), False

        translated = unit.is_translated()
        if translated and created:
            is_template = self.translation.is_template()
            if is_template and 'add-source-review' in all_flags:
                return translated, True
            elif not is_template and 'add-review' in all_flags:
                return translated, True
        return translated, unit.is_fuzzy()

    def update_from_unit(self, unit, pos, created):
        """Update Unit from ttkit unit."""
        # Get unit attributes
        location = unit.get_locations()
        flags = unit.get_flags()
        target = unit.get_target()
        source = unit.get_source()
        comment = unit.get_comments()
        translated, fuzzy = self.get_unit_status(unit, target, created)
        previous_source = unit.get_previous_source()
        content_hash = unit.get_content_hash()

        # Monolingual files handling (without target change)
        if unit.template is not None and target == self.target:
            if source != self.source and translated:
                if self.previous_source == self.source and self.fuzzy:
                    # Source change was reverted
                    previous_source = ''
                    fuzzy = False
                    translated = True
                else:
                    # Store previous source and fuzzy flag for monolingual
                    if previous_source == '':
                        previous_source = self.source
                    fuzzy = True
                    translated = False
            else:
                # We should keep calculated flags if translation was
                # not changed outside
                previous_source = self.previous_source
                fuzzy = self.fuzzy
                translated = self.translated

        # Update checks on fuzzy update or on content change
        same_content = (
            target == self.target and source == self.source
        )
        same_state = (
            fuzzy == self.fuzzy and
            translated == self.translated and
            not created
        )

        # Check if we actually need to change anything
        # pylint: disable=R0916
        if (not created and
                location == self.location and
                flags == self.flags and
                same_content and same_state and
                translated == self.translated and
                comment == self.comment and
                pos == self.position and
                content_hash == self.content_hash and
                previous_source == self.previous_source):
            return

        # Ensure we track source string
        source_info, source_created = Source.objects.get_or_create(
            id_hash=self.id_hash,
            subproject=self.translation.subproject
        )
        contentsum_changed = self.content_hash != content_hash

        # Store updated values
        self.position = pos
        self.location = location
        self.flags = flags
        self.source = source
        self.target = target
        self.fuzzy = fuzzy
        self.translated = translated
        self.comment = comment
        self.content_hash = content_hash
        self.previous_source = previous_source
        self.priority = source_info.priority
        self.save(
            force_insert=created,
            backend=True,
            same_content=same_content,
            same_state=same_state
        )

        # Create change object for new source string
        if source_created:
            Change.objects.create(
                translation=self.translation,
                action=Change.ACTION_NEW_SOURCE,
                unit=self,
            )
        if contentsum_changed:
            self.update_has_failing_check(recurse=False, update_stats=False)
            self.update_has_comment(update_stats=False)
            self.update_has_suggestion(update_stats=False)

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
        plurals = self.translation.language.nplurals
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
            translation__subproject__allow_translation_propagation=True
        )
        for unit in allunits:
            unit.target = self.target
            unit.fuzzy = self.fuzzy
            unit.save_backend(request, False, change_action=change_action)

    def update_lock(self, request, user, change_action):
        """Lock updating wrapper"""
        if change_action != Change.ACTION_UPLOAD:
            if request is not None:
                self.translation.update_lock(request.user)
            else:
                self.translation.update_lock(user)

    def save_backend(self, request, propagate=True, gen_change=True,
                     change_action=None, user=None):
        """
        Stores unit to backend.

        Optional user parameters defines authorship of a change.
        """
        # For case when authorship specified, use user from request
        if user is None or user.is_anonymous:
            user = request.user

        # Update lock timestamp
        self.update_lock(request, user, change_action)

        # Store to backend
        try:
            (saved, pounit) = self.translation.update_unit(self, request, user)
        except FileLockException:
            self.log_error('failed to lock backend for %s!', self)
            messages.error(
                request,
                _(
                    'Failed to store message in the backend, '
                    'lock timeout occurred!'
                )
            )
            return False

        # Handle situation when backend did not find the message
        if pounit is None:
            self.log_error('message %s disappeared!', self)
            messages.error(
                request,
                _(
                    'Message not found in backend storage, '
                    'it is probably corrupted.'
                )
            )
            # Try reloading from backend
            self.translation.check_sync(True)
            return False

        # Return if there was no change
        # We have to explicitly check for fuzzy flag change on monolingual
        # files, where we handle it ourselves without storing to backend
        if (not saved and
                self.old_unit.fuzzy == self.fuzzy and
                self.old_unit.target == self.target):
            # Propagate if we should
            if propagate:
                self.propagate(request, change_action)
            return False

        # Update translated flag
        self.translated = pounit.is_translated()

        # Update comments as they might have been changed (eg, fuzzy flag
        # removed)
        self.flags = pounit.get_flags()

        # Propagate to other projects
        # This has to be done before changing source/content_hash for template
        if propagate:
            self.propagate(request, change_action)

        if self.translation.is_template():
            self.source = self.target
            self.content_hash = calculate_hash(self.source, self.context)

        # Save updated unit to database
        self.save(backend=True)

        # Update translation stats
        old_translated = self.translation.translated
        if change_action != Change.ACTION_UPLOAD:
            self.translation.update_stats()

        # Notify subscribed users about new translation
        notify_new_translation(self, self.old_unit, user)

        # Update user stats
        user.profile.translated += 1
        user.profile.save()

        # Generate Change object for this change
        if gen_change:
            self.generate_change(request, user, self.old_unit, change_action)

        # Force commiting on completing translation
        if (old_translated < self.translation.translated and
                self.translation.translated == self.translation.total):
            self.translation.commit_pending(request)
            Change.objects.create(
                translation=self.translation,
                action=Change.ACTION_COMPLETE,
                user=user,
                author=user
            )

        # Update related source strings if working on a template
        if self.translation.is_template():
            self.update_source_units(self.old_unit.source)

        return True

    def update_source_units(self, previous_source):
        """Update source for units withing same component.

        This is needed when editing template translation for monolingual
        formats.
        """
        # Find relevant units
        same_source = Unit.objects.filter(
            translation__subproject=self.translation.subproject,
            context=self.context,
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
            translated=False,
            fuzzy=True,
            previous_source=self.source
        )
        reverted_ids = set(reverted.values_list('id', flat=True))
        reverted.update(
            translated=True,
            fuzzy=False,
            previous_source=''
        )
        # Set fuzzy on changed
        same_source.filter(
            translated=True
        ).exclude(
            id__in=reverted_ids
        ).update(
            translated=False,
            fuzzy=True,
            previous_source=previous_source,
        )
        # Update source index and stats
        for unit in same_source.iterator():
            update_index_unit(unit, True)
            unit.translation.update_stats()

    def generate_change(self, request, author, oldunit, change_action):
        """Create Change entry for saving unit."""
        # Notify about new contributor
        user_changes = Change.objects.filter(
            translation=self.translation,
            user=request.user
        )
        if not user_changes.exists():
            notify_new_contributor(self, request.user)

        # Action type to store
        if change_action is not None:
            action = change_action
        elif oldunit.translated:
            action = Change.ACTION_CHANGE
        else:
            action = Change.ACTION_NEW

        kwargs = {}

        # Should we store history of edits?
        if self.translation.subproject.save_history:
            kwargs['target'] = self.target
            kwargs['old'] = self.old_unit.target

        # Create change object
        Change.objects.create(
            unit=self,
            translation=self.translation,
            action=action,
            user=request.user,
            author=author,
            **kwargs
        )

    def save(self, *args, **kwargs):
        """
        Wrapper around save to warn when save did not come from
        git backend (eg. commit or by parsing file).
        """
        # Warn if request is not coming from backend
        if 'backend' not in kwargs:
            self.log_error(
                'Unit.save called without backend sync: %s',
                ''.join(traceback.format_stack())
            )
        else:
            del kwargs['backend']

        # Pop parameter indicating that we don't have to process content
        same_content = kwargs.pop('same_content', False)
        same_state = kwargs.pop('same_state', False)
        # Keep the force_insert for parent save
        force_insert = kwargs.get('force_insert', False)

        # Store number of words
        if not same_content or not self.num_words:
            self.num_words = len(self.get_source_plurals()[0].split())

        # Actually save the unit
        super(Unit, self).save(*args, **kwargs)

        # Update checks if content or fuzzy flag has changed
        if not same_content or not same_state:
            self.run_checks(same_state, same_content, force_insert)

        # Update fulltext index if content has changed or this is a new unit
        if force_insert or not same_content:
            update_index_unit(self, force_insert)

    def suggestions(self):
        """Return all suggestions for this unit."""
        if self._suggestions is None:
            self._suggestions = Suggestion.objects.filter(
                content_hash=self.content_hash,
                project=self.translation.subproject.project,
                language=self.translation.language
            )
        return self._suggestions

    def cleanup_checks(self, source, target):
        """Cleanup listed source and target checks."""
        if len(source) == 0 and len(target) == 0:
            return False
        todelete = Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.subproject.project
        ).filter(
            (Q(language=self.translation.language) & Q(check__in=target)) |
            (Q(language=None) & Q(check__in=source))
        )
        if todelete.exists():
            todelete.delete()
            return True
        return False

    def checks(self):
        """Return all checks for this unit (even ignored)."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.subproject.project,
            language=self.translation.language
        )

    def source_checks(self):
        """Return all source checks for this unit (even ignored)."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.subproject.project,
            language=None
        )

    def active_checks(self):
        """Return all active (not ignored) checks for this unit."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.subproject.project,
            language=self.translation.language,
            ignore=False
        )

    def active_source_checks(self):
        """Return all active (not ignored) source checks for this unit."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.subproject.project,
            language=None,
            ignore=False
        )

    def get_comments(self):
        """Return list of target comments."""
        return Comment.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.subproject.project,
        ).filter(
            Q(language=self.translation.language) | Q(language=None),
        )

    def get_source_comments(self):
        """Return list of target comments."""
        return Comment.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.subproject.project,
            language=None,
        )

    def get_checks_to_run(self, same_state, is_new):
        """
        Returns list of checks to run on state change.

        Returns tuple of checks to run and whether to do cleanup.
        """
        if self.translation.is_template():
            return {}, True

        checks_to_run = CHECKS.data
        cleanup_checks = True

        if (not same_state or is_new) and not self.translated:
            # Check whether there is any message with same source
            project = self.translation.subproject.project
            same_source = Unit.objects.filter(
                translation__language=self.translation.language,
                translation__subproject__project=project,
                content_hash=self.content_hash,
                translated=True,
            ).exclude(
                id=self.id,
                translation__subproject__allow_translation_propagation=False,
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

        # Run all source checks
        for check, check_obj in checks_to_run.items():
            if check_obj.target and check_obj.check_target(src, tgt, self):
                if check in old_target_checks:
                    # We already have this check
                    old_target_checks.remove(check)
                else:
                    # Create new check
                    Check.objects.create(
                        content_hash=self.content_hash,
                        project=self.translation.subproject.project,
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
                        project=self.translation.subproject.project,
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

    def update_has_failing_check(self, recurse=False, update_stats=True):
        """Update flag counting failing checks."""
        has_failing_check = self.translated and self.active_checks().exists()

        # Change attribute if it has changed
        if has_failing_check != self.has_failing_check:
            self.has_failing_check = has_failing_check
            self.save(backend=True, same_content=True, same_state=True)

            # Update translation stats
            if update_stats:
                self.translation.update_stats()

        # Invalidate checks cache if there was any change
        # (above code cares only about whether there is failing check
        # while here we care about any changed in checks)
        self.translation.invalidate_cache()

        if recurse:
            for unit in Unit.objects.same(self):
                unit.update_has_failing_check(False)

    def update_has_suggestion(self, update_stats=True):
        """Update flag counting suggestions."""
        has_suggestion = len(self.suggestions()) > 0
        if has_suggestion != self.has_suggestion:
            self.has_suggestion = has_suggestion
            self.save(backend=True, same_content=True, same_state=True)

            # Update translation stats
            if update_stats:
                self.translation.update_stats()

    def update_has_comment(self, update_stats=True):
        """Update flag counting comments."""
        has_comment = len(self.get_comments()) > 0
        if has_comment != self.has_comment:
            self.has_comment = has_comment
            self.save(backend=True, same_content=True, same_state=True)

            # Update translation stats
            if update_stats:
                self.translation.update_stats()

    def nearby(self):
        """Return list of nearby messages based on location."""
        return Unit.objects.prefetch().filter(
            translation=self.translation,
            position__gte=self.position - settings.NEARBY_MESSAGES,
            position__lte=self.position + settings.NEARBY_MESSAGES,
        )

    def translate(self, request, new_target, new_fuzzy, change_action=None,
                  propagate=True):
        """Store new translation of a unit."""
        # Update unit and save it
        self.target = join_plural(new_target)
        self.fuzzy = new_fuzzy
        saved = self.save_backend(
            request,
            change_action=change_action,
            propagate=propagate
        )

        return saved

    @property
    def all_flags(self):
        """Return union of own and subproject flags."""
        if self._all_flags is None:
            self._all_flags = set(
                self.flags.split(',') +
                self.source_info.check_flags.split(',') +
                self.translation.subproject.all_flags
            )
            self._all_flags.discard('')
        return self._all_flags

    @property
    def source_info(self):
        """Return related source string object."""
        if self._source_info is None:
            self._source_info = Source.objects.get(
                id_hash=self.id_hash,
                subproject=self.translation.subproject
            )
        return self._source_info

    def get_secondary_units(self, user):
        """Return list of secondary units."""
        secondary_langs = user.profile.secondary_languages.exclude(
            id=self.translation.language.id
        )
        return get_distinct_translations(
            Unit.objects.filter(
                id_hash=self.id_hash,
                translated=True,
                translation__subproject=self.translation.subproject,
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

    def get_other_units(self):
        """Returns other units to show while translating."""
        kwargs = {
            'translation__subproject__project':
                self.translation.subproject.project,
            'translation__language':
                self.translation.language,
            'translated': True,
        }

        same = Unit.objects.same(self, False)
        same_id = Unit.objects.prefetch().filter(
            id_hash=self.id_hash,
            **kwargs
        )
        same_source = Unit.objects.prefetch().filter(
            source=self.source,
            **kwargs
        )

        result = same | same_id | same_source

        # Is it only this unit?
        if result.count() == 1:
            return Unit.objects.none()

        return result
