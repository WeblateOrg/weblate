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

from django.db import models
from weblate import appsettings
from django.db.models import Q
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from django.contrib import messages
from django.core.cache import cache
from whoosh import qparser
import traceback
from trans.checks import CHECKS
from trans.models.translation import Translation
from trans.search import FULLTEXT_INDEX, SOURCE_SCHEMA, TARGET_SCHEMA

from trans.filelock import FileLockException
from trans.util import is_plural, split_plural
import weblate


class UnitManager(models.Manager):
    def update_from_unit(self, translation, unit, pos):
        '''
        Process translation toolkit unit and stores/updates database entry.
        '''
        # Get basic unit data
        src = unit.get_source()
        ctx = unit.get_context()
        checksum = unit.get_checksum()

        # Try getting existing unit
        dbunit = None
        try:
            dbunit = translation.unit_set.get(
                checksum=checksum
            )
            created = False
        except Unit.MultipleObjectsReturned:
            # Some inconsistency (possibly race condition), try to recover
            dbunit = translation.unit_set.filter(
                checksum=checksum
            ).delete()
        except Unit.DoesNotExist:
            pass

        # Create unit if it does not exist
        if dbunit is None:
            dbunit = Unit(
                translation=translation,
                checksum=checksum,
                source=src,
                context=ctx
            )
            created = True

        # Update all details
        dbunit.update_from_unit(unit, pos, created)

        # Return result
        return dbunit, created

    def filter_checks(self, rqtype, translation):
        '''
        Filtering for checks.
        '''
        from trans.models.unitdata import Check

        # Filter checks for current project
        checks = Check.objects.filter(
            project=translation.subproject.project,
            ignore=False
        )

        filter_translated = True

        # Filter by language
        if rqtype == 'allchecks':
            return self.filter(has_failing_check=True)
        elif rqtype == 'sourcechecks':
            checks = checks.filter(language=None)
            filter_translated = False
        elif CHECKS[rqtype].source and CHECKS[rqtype].target:
            checks = checks.filter(
                Q(language=translation.language) | Q(language=None)
            )
            filter_translated = False
        elif CHECKS[rqtype].source:
            checks = checks.filter(language=None)
            filter_translated = False
        elif CHECKS[rqtype].target:
            checks = checks.filter(language=translation.language)

        # Filter by check type
        if not rqtype in ['allchecks', 'sourcechecks']:
            checks = checks.filter(check=rqtype)

        checks = checks.values_list('checksum', flat=True)
        ret = self.filter(checksum__in=checks)
        if filter_translated:
            ret = ret.filter(translated=True)
        return ret

    def filter_type(self, rqtype, translation):
        '''
        Basic filtering based on unit state or failed checks.
        '''
        from trans.models.unitdata import Comment

        if rqtype == 'fuzzy':
            return self.filter(fuzzy=True)
        elif rqtype == 'untranslated':
            return self.filter(translated=False)
        elif rqtype == 'suggestions':
            return self.filter(has_suggestion=True)
        elif rqtype == 'sourcecomments':
            coms = Comment.objects.filter(
                language=None,
                project=translation.subproject.project
            )
            coms = coms.values_list('checksum', flat=True)
            return self.filter(checksum__in=coms)
        elif rqtype == 'targetcomments':
            return self.filter(has_comment=True)
        elif rqtype in CHECKS or rqtype in ['allchecks', 'sourcechecks']:
            return self.filter_checks(rqtype, translation)
        else:
            # Catch anything not matching including 'all'
            return self.all()

    def count_type(self, rqtype, translation):
        '''
        Cached counting of failing checks (and other stats).
        '''
        # Use precalculated data if we can
        if rqtype == 'all':
            return translation.total
        elif rqtype == 'fuzzy':
            return translation.fuzzy
        elif rqtype == 'untranslated':
            return translation.total - translation.translated
        elif rqtype == 'allchecks':
            return translation.failing_checks
        elif rqtype == 'suggestions':
            return translation.have_suggestion

        # Try to get value from cache
        cache_key = 'counts-%s-%s-%s' % (
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
        '''
        Returns units touched by other users since given time.
        '''
        if user.is_anonymous():
            return self.none()
        from trans.models.changes import Change
        sample = self.all()[0]
        changes = Change.objects.filter(
            translation=sample.translation,
            timestamp__gte=date
        ).exclude(user=user)
        return self.filter(id__in=changes.values_list('unit__id', flat=True))

    def add_to_source_index(self, checksum, source, context, writer):
        '''
        Updates/Adds to source index given unit.
        '''
        writer.update_document(
            checksum=unicode(checksum),
            source=unicode(source),
            context=unicode(context),
        )

    def add_to_target_index(self, checksum, target, writer):
        '''
        Updates/Adds to target index given unit.
        '''
        writer.update_document(
            checksum=unicode(checksum),
            target=unicode(target),
        )

    def add_to_index(self, unit, source=True):
        '''
        Updates/Adds to all indices given unit.
        '''
        if appsettings.OFFLOAD_INDEXING:
            from trans.models.unitdata import IndexUpdate
            IndexUpdate.objects.get_or_create(unit=unit, source=source)
            return

        writer_target = FULLTEXT_INDEX.target_writer(
            unit.translation.language.code
        )
        writer_source = FULLTEXT_INDEX.source_writer()

        if source:
            self.add_to_source_index(
                unit.checksum,
                unit.source,
                unit.context,
                writer_source)
        self.add_to_target_index(
            unit.checksum,
            unit.target,
            writer_target)

    def __search(self, searcher, field, schema, query):
        '''
        Wrapper for fulltext search.
        '''
        parser = qparser.QueryParser(field, schema)
        parsed = parser.parse(query)
        return [searcher.stored_fields(d)['checksum']
                for d in searcher.docs_for_query(parsed)]

    def search(self, search_type, search_query,
               search_source=True, search_context=True, search_target=True):
        '''
        High level wrapper for searching.
        '''

        if search_type == 'exact':
            query = Q()
            if search_source:
                query |= Q(source=search_query)
            if search_target:
                query |= Q(target=search_query)
            if search_context:
                query |= Q(context=search_query)
            return self.filter(query)
        elif search_type == 'substring':
            query = Q()
            if search_source:
                query |= Q(source__icontains=search_query)
            if search_target:
                query |= Q(target__icontains=search_query)
            if search_context:
                query |= Q(context__icontains=search_query)
            return self.filter(query)
        else:
            return self.fulltext(
                search_query,
                search_source,
                search_context,
                search_target
            )

    def fulltext(self, query, source=True, context=True, translation=True,
                 checksums=False):
        '''
        Performs full text search on defined set of fields.

        Returns queryset unless checksums is set.
        '''
        ret = set()

        # Search in source or context
        if source or context:
            index = FULLTEXT_INDEX.source_searcher(
                not appsettings.OFFLOAD_INDEXING
            )
            with index as searcher:
                if source:
                    results = self.__search(
                        searcher,
                        'source',
                        SOURCE_SCHEMA,
                        query
                    )
                    ret = ret.union(results)
                if context:
                    results = self.__search(
                        searcher,
                        'context',
                        SOURCE_SCHEMA,
                        query
                    )
                    ret = ret.union(results)

        # Search in target
        if translation:
            sample = self.all()[0]
            index = FULLTEXT_INDEX.target_searcher(
                sample.translation.language.code,
                not appsettings.OFFLOAD_INDEXING
            )
            with index as searcher:
                results = self.__search(
                    searcher,
                    'target',
                    TARGET_SCHEMA,
                    query
                )
                ret = ret.union(results)

        if checksums:
            return ret

        return self.filter(checksum__in=ret)

    def same_source(self, unit):
        '''
        Finds units with same source.
        '''
        index = FULLTEXT_INDEX.source_searcher(
            not appsettings.OFFLOAD_INDEXING
        )
        source_string = unit.get_source_plurals()[0]
        parser = qparser.QueryParser('source', SOURCE_SCHEMA)
        parsed = parser.parse(source_string)
        checksums = set()
        with index as searcher:
            # Search for same string
            results = searcher.search(parsed)
            for result in results:
                checksums.add(result['checksum'])

        return self.filter(
            checksum__in=checksums,
            translation__language=unit.translation.language,
            translated=True
        ).exclude(
            pk=unit.id
        )

    def more_like_this(self, unit):
        '''
        Finds closely similar units.
        '''
        index = FULLTEXT_INDEX.source_searcher(
            not appsettings.OFFLOAD_INDEXING
        )
        source_string = unit.get_source_plurals()[0]
        parser = qparser.QueryParser('source', SOURCE_SCHEMA)
        parsed = parser.parse(source_string)
        checksums = set()
        with index as searcher:
            # Search for same string
            results = searcher.search(parsed)
            if len(results) == 0:
                return self.none()
            first_hit = results[0]
            # Find similar results to first one
            more_results = first_hit.more_like_this(
                'source',
                source_string,
                500
            )
            # Include all more like this results
            for result in more_results:
                checksums.add(result['checksum'])
            # Remove all original matches
            for result in results:
                checksums.discard(result['checksum'])

        return self.filter(
            checksum__in=checksums,
            translation__language=unit.translation.language,
            translated=True
        ).exclude(
            pk=unit.id
        )

    def same(self, unit):
        '''
        Units with same source withing same project.
        '''
        project = unit.translation.subproject.project
        return self.filter(
            checksum=unit.checksum,
            translation__subproject__project=project,
            translation__language=unit.translation.language
        )

    def get_checksum(self, request, translation, checksum):
        '''
        Returns unit based on checksum.
        '''
        try:
            return Unit.objects.filter(
                checksum=checksum,
                translation=translation
            )[0]
        except Unit.DoesNotExist:
            weblate.logger.error('message %s disappeared!', checksum)
            messages.error(
                request,
                _('Message you wanted to translate is no longer available!')
            )
            raise


class Unit(models.Model):
    translation = models.ForeignKey(Translation)
    checksum = models.CharField(max_length=40, db_index=True)
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

    objects = UnitManager()

    class Meta:
        permissions = (
            ('save_translation', "Can save translation"),
        )
        ordering = ['position']
        app_label = 'trans'

    def has_acl(self, user):
        '''
        Checks whether current user is allowed to access this
        subproject.
        '''
        return self.translation.subproject.project.has_acl(user)

    def check_acl(self, request):
        '''
        Raises an error if user is not allowed to acces s this project.
        '''
        self.translation.subproject.project.check_acl(request)

    def __unicode__(self):
        return '%s on %s' % (
            self.checksum,
            self.translation,
        )

    def get_absolute_url(self):
        return '%s?checksum=%s' % (
            self.translation.get_translate_url(), self.checksum
        )

    def update_from_unit(self, unit, pos, created):
        '''
        Updates Unit from ttkit unit.
        '''
        # Get unit attributes
        location = unit.get_locations()
        flags = unit.get_flags()
        target = unit.get_target()
        comment = unit.get_comments()
        fuzzy = unit.is_fuzzy()
        translated = unit.is_translated()
        previous_source = unit.get_previous_source()

        # Update checks on fuzzy update or on content change
        same_content = (target == self.target)
        same_state = (
            fuzzy == self.fuzzy
            and translated == self.translated
            and not created
        )

        # Check if we actually need to change anything
        if (not created and
                location == self.location and
                flags == self.flags and
                same_content and same_state and
                translated == self.translated and
                comment == self.comment and
                pos == self.position and
                previous_source == self.previous_source):
            return

        # Store updated values
        self.position = pos
        self.location = location
        self.flags = flags
        self.target = target
        self.fuzzy = fuzzy
        self.translated = translated
        self.comment = comment
        self.previous_source = previous_source
        self.save(
            force_insert=created,
            backend=True,
            same_content=same_content,
            same_state=same_state
        )

    def is_plural(self):
        '''
        Checks whether message is plural.
        '''
        return is_plural(self.source)

    def get_source_plurals(self):
        '''
        Retuns source plurals in array.
        '''
        return split_plural(self.source)

    def get_target_plurals(self):
        '''
        Returns target plurals in array.
        '''
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
            del(ret[-1])

        return ret

    def propagate(self, request):
        '''
        Propagates current translation to all others.
        '''
        allunits = Unit.objects.same(self).exclude(id=self.id).filter(
            translation__subproject__allow_translation_propagation=True
        )
        for unit in allunits:
            unit.target = self.target
            unit.fuzzy = self.fuzzy
            unit.save_backend(request, False)

    def save_backend(self, request, propagate=True, gen_change=True):
        '''
        Stores unit to backend.
        '''
        from accounts.models import (
            notify_new_translation, notify_new_contributor
        )
        from trans.models.changes import Change

        # Update lock timestamp
        self.translation.update_lock(request)

        # Store to backend
        try:
            (saved, pounit) = self.translation.update_unit(self, request)
        except FileLockException:
            weblate.logger.error('failed to lock backend for %s!', self)
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
            weblate.logger.error('message %s disappeared!', self)
            messages.error(
                request,
                _(
                    'Message not found in backend storage, '
                    'it is probably corrupted.'
                )
            )
            # Try reloading from backend
            self.translation.update_from_blob(True)
            return False

        # Return if there was no change
        if not saved:
            # Propagate if we should
            if propagate:
                self.propagate(request)
            return False

        # Update translated flag
        self.translated = pounit.is_translated()

        # Update comments as they might have been changed (eg, fuzzy flag
        # removed)
        self.flags = pounit.get_flags()

        # Get old unit from database (for notifications)
        oldunit = Unit.objects.get(id=self.id)

        # Save updated unit to database
        self.save(backend=True)

        # Update translation stats
        old_translated = self.translation.translated
        self.translation.update_stats()

        # Notify subscribed users about new translation
        notify_new_translation(self, oldunit, request.user)

        # Update user stats
        profile = request.user.get_profile()
        profile.translated += 1
        profile.save()

        # Notify about new contributor
        user_changes = Change.objects.filter(
            translation=self.translation,
            user=request.user
        )
        if not user_changes.exists():
            notify_new_contributor(self, request.user)

        # Generate Change object for this change
        if gen_change:
            if oldunit.translated:
                action = Change.ACTION_CHANGE
            else:
                action = Change.ACTION_NEW
            # Create change object
            Change.objects.create(
                unit=self,
                translation=self.translation,
                action=action,
                user=request.user
            )

        # Force commiting on completing translation
        if (old_translated < self.translation.translated
                and self.translation.translated == self.translation.total):
            self.translation.commit_pending(request)
            Change.objects.create(
                translation=self.translation,
                action=Change.ACTION_COMPLETE,
                user=request.user
            )

        # Propagate to other projects
        if propagate:
            self.propagate(request)

        return True

    def save(self, *args, **kwargs):
        '''
        Wrapper around save to warn when save did not come from
        git backend (eg. commit or by parsing file).
        '''
        # Warn if request is not coming from backend
        if not 'backend' in kwargs:
            weblate.logger.error(
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
        if not same_content:
            self.num_words = len(self.get_source_plurals()[0].split())

        # Actually save the unit
        super(Unit, self).save(*args, **kwargs)

        # Update checks if content or fuzzy flag has changed
        if not same_content or not same_state:
            self.check()

        # Update fulltext index if content has changed or this is a new unit
        if force_insert:
            # New unit, need to update both source and target index
            Unit.objects.add_to_index(self, True)
        else:
            # We only update target index here
            Unit.objects.add_to_index(self, False)

    def get_location_links(self):
        '''
        Generates links to source files where translation was used.
        '''
        ret = []

        # Do we have any locations?
        if len(self.location) == 0:
            return ''

        # Is it just an ID?
        if self.location.isdigit():
            return _('unit ID %s') % self.location

        # Go through all locations separated by comma
        for location in self.location.split(','):
            location = location.strip()
            if location == '':
                continue
            location_parts = location.split(':')
            if len(location_parts) == 2:
                filename, line = location_parts
            else:
                filename = location_parts[0]
                line = 0
            link = self.translation.subproject.get_repoweb_link(filename, line)
            if link is None:
                ret.append('%s' % location)
            else:
                ret.append('<a href="%s">%s</a>' % (link, location))
        return mark_safe('\n'.join(ret))

    def suggestions(self):
        '''
        Returns all suggestions for this unit.
        '''
        from trans.models.unitdata import Suggestion
        return Suggestion.objects.filter(
            checksum=self.checksum,
            project=self.translation.subproject.project,
            language=self.translation.language
        )

    def cleanup_checks(self, source, target):
        '''
        Cleanups listed source and target checks.
        '''
        from trans.models.unitdata import Check
        if len(source) == 0 and len(target) == 0:
            return
        Check.objects.filter(
            checksum=self.checksum,
            project=self.translation.subproject.project
        ).filter(
            (Q(language=self.translation.language) & Q(check__in=target)) |
            (Q(language=None) & Q(check__in=source))
        ).delete()

    def checks(self):
        '''
        Returns all checks for this unit (even ignored).
        '''
        from trans.models.unitdata import Check
        return Check.objects.filter(
            checksum=self.checksum,
            project=self.translation.subproject.project,
            language=self.translation.language
        )

    def source_checks(self):
        '''
        Returns all source checks for this unit (even ignored).
        '''
        from trans.models.unitdata import Check
        return Check.objects.filter(
            checksum=self.checksum,
            project=self.translation.subproject.project,
            language=None
        )

    def active_checks(self):
        '''
        Returns all active (not ignored) checks for this unit.
        '''
        from trans.models.unitdata import Check
        return Check.objects.filter(
            checksum=self.checksum,
            project=self.translation.subproject.project,
            language=self.translation.language,
            ignore=False
        )

    def active_source_checks(self):
        '''
        Returns all active (not ignored) source checks for this unit.
        '''
        from trans.models.unitdata import Check
        return Check.objects.filter(
            checksum=self.checksum,
            project=self.translation.subproject.project,
            language=None,
            ignore=False
        )

    def get_comments(self):
        '''
        Returns list of target comments.
        '''
        from trans.models.unitdata import Comment
        return Comment.objects.filter(
            checksum=self.checksum,
            project=self.translation.subproject.project,
            language=self.translation.language,
        )

    def get_source_comments(self):
        '''
        Returns list of target comments.
        '''
        from trans.models.unitdata import Comment
        return Comment.objects.filter(
            checksum=self.checksum,
            project=self.translation.subproject.project,
            language=None,
        )

    def check(self):
        '''
        Updates checks for this unit.
        '''
        from trans.models.unitdata import Check

        checks_to_run = CHECKS
        cleanup_checks = True

        if self.fuzzy or not self.translated:
            # Check whether there is any message with same source
            project = self.translation.subproject.project
            same_source = Unit.objects.filter(
                translation__language=self.translation.language,
                translation__subproject__project=project,
                checksum=self.checksum,
                fuzzy=False,
            ).exclude(
                id=self.id
            )

            # Delete all checks if only message with this source is fuzzy
            if not same_source.exists():
                self.checks().delete()
                self.translation.invalidate_cache()
                return

            # If there is no consistency checking, we can return
            if not 'inconsistent' in CHECKS:
                return

            # Limit checks to consistency check for fuzzy messages
            checks_to_run = {'inconsistent': CHECKS['inconsistent']}
            cleanup_checks = False

        src = self.get_source_plurals()
        tgt = self.get_target_plurals()
        old_target_checks = set(self.checks().values_list('check', flat=True))
        old_source_checks = set(self.source_checks().values_list(
            'check', flat=True
        ))

        # Run all checks
        for check in checks_to_run:
            check_obj = CHECKS[check]
            # Target check
            if check_obj.target and check_obj.check(src, tgt, self):
                if check in old_target_checks:
                    # We already have this check
                    old_target_checks.remove(check)
                else:
                    # Create new check
                    Check.objects.create(
                        checksum=self.checksum,
                        project=self.translation.subproject.project,
                        language=self.translation.language,
                        ignore=False,
                        check=check
                    )
            # Source check
            if check_obj.source and check_obj.check_source(src, self):
                if check in old_source_checks:
                    # We already have this check
                    old_source_checks.remove(check)
                else:
                    # Create new check
                    Check.objects.create(
                        checksum=self.checksum,
                        project=self.translation.subproject.project,
                        language=None,
                        ignore=False,
                        check=check
                    )

        # Delete no longer failing checks
        if cleanup_checks:
            self.cleanup_checks(old_source_checks, old_target_checks)

        # Update failing checks flag
        self.update_has_failing_check()

    def update_has_failing_check(self):
        '''
        Updates flag counting failing checks.
        '''
        has_failing_check = len(self.active_checks()) > 0
        if has_failing_check != self.has_failing_check:
            self.has_failing_check = has_failing_check
            self.save(backend=True)

            # Invalidate checks cache
            self.translation.invalidate_cache()

            # Update translation stats
            self.translation.update_stats()

    def update_has_suggestion(self):
        '''
        Updates flag counting suggestions.
        '''
        has_suggestion = len(self.suggestions()) > 0
        if has_suggestion != self.has_suggestion:
            self.has_suggestion = has_suggestion
            self.save(backend=True)

            # Update translation stats
            self.translation.update_stats()

    def update_has_comment(self):
        '''
        Updates flag counting comments.
        '''
        has_comment = len(self.get_comments()) > 0
        if has_comment != self.has_comment:
            self.has_comment = has_comment
            self.save(backend=True)

            # Update translation stats
            self.translation.update_stats()

    def nearby(self):
        '''
        Returns list of nearby messages based on location.
        '''
        return Unit.objects.filter(
            translation=self.translation,
            position__gte=self.position - appsettings.NEARBY_MESSAGES,
            position__lte=self.position + appsettings.NEARBY_MESSAGES,
        ).select_related()

    def add_suggestion(self, target, user):
        '''
        Creates new suggestion for this unit.
        '''
        from trans.models.unitdata import Suggestion
        from trans.models.changes import Change
        from accounts.models import notify_new_suggestion

        if not user.is_authenticated():
            user = None

        # Create the suggestion
        suggestion = Suggestion.objects.create(
            target=target,
            checksum=self.checksum,
            language=self.translation.language,
            project=self.translation.subproject.project,
            user=user
        )

        # Record in change
        Change.objects.create(
            unit=self,
            action=Change.ACTION_SUGGESTION,
            translation=self.translation,
            user=user
        )

        # Notify subscribed users
        notify_new_suggestion(self, suggestion, user)

        # Update suggestion stats
        if user is not None:
            profile = user.get_profile()
            profile.suggested += 1
            profile.save()

        # Update unit flags
        for unit in suggestion.get_related_units():
            unit.update_has_suggestion()
