# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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
import traceback
from weblate.trans.checks import CHECKS
from weblate.trans.models.translation import Translation
from weblate.trans.models.source import Source
from weblate.trans.search import update_index_unit, fulltext_search, more_like

from weblate.trans.filelock import FileLockException
from weblate.trans.util import is_plural, split_plural, join_plural
import weblate

FLAG_TEMPLATE = '<span title="%s" class="flag-icon ui-icon ui-icon-%s"></span>'


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
            dbunit = translation.unit_set.get(checksum=checksum)
            created = False
        except Unit.MultipleObjectsReturned:
            # Some inconsistency (possibly race condition), try to recover
            dbunit = translation.unit_set.filter(checksum=checksum).delete()
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

    def filter_checks(self, rqtype, translation, ignored=False):
        '''
        Filtering for checks.
        '''
        from weblate.trans.models.unitdata import Check

        # Filter checks for current project
        checks = Check.objects.filter(
            project=translation.subproject.project,
            ignore=ignored
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

        checks = checks.values_list('contentsum', flat=True)
        ret = self.filter(contentsum__in=checks)
        if filter_translated:
            ret = ret.filter(translated=True)
        return ret

    def filter_type(self, rqtype, translation, ignored=False):
        '''
        Basic filtering based on unit state or failed checks.
        '''
        from weblate.trans.models.unitdata import Comment

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
            coms = coms.values_list('contentsum', flat=True)
            return self.filter(contentsum__in=coms)
        elif rqtype == 'targetcomments':
            return self.filter(has_comment=True)
        elif rqtype in CHECKS or rqtype in ['allchecks', 'sourcechecks']:
            return self.filter_checks(rqtype, translation, ignored)
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
        from weblate.trans.models.changes import Change
        try:
            sample = self.all()[0]
        except IndexError:
            return self.none()
        changes = Change.objects.content().filter(
            translation=sample.translation,
            timestamp__gte=date
        ).exclude(user=user)
        return self.filter(id__in=changes.values_list('unit__id', flat=True))

    def search(self, params):
        '''
        High level wrapper for searching.
        '''

        if params['search'] in ('exact', 'substring'):
            queries = []

            if params['search'] == 'exact':
                modifier = ''
            else:
                modifier = '__icontains'

            if params['src']:
                queries.append('source')
            if params['tgt']:
                queries.append('target')
            if params['ctx']:
                queries.append('context')

            query = reduce(
                lambda q, value:
                q | Q(**{'%s%s' % (value, modifier): params['q']}),
                queries,
                Q()
            )

            return self.filter(query)
        else:
            return self.fulltext(
                params['q'],
                params['src'],
                params['ctx'],
                params['tgt']
            )

    def fulltext(self, query, source=True, context=True, translation=True,
                 checksums=False):
        '''
        Performs full text search on defined set of fields.

        Returns queryset unless checksums is set.
        '''

        lang = self.all()[0].translation.language.code
        ret = fulltext_search(query, lang, source, context, translation)

        if checksums:
            return ret

        return self.filter(checksum__in=ret)

    def same_source(self, unit):
        '''
        Finds units with same source.
        '''
        checksums = fulltext_search(
            unit.get_source_plurals()[0],
            unit.translation.language.code,
            True, False, False
        )

        return self.filter(
            checksum__in=checksums,
            translation__language=unit.translation.language,
            translated=True
        ).exclude(
            pk=unit.id
        )

    def more_like_this(self, unit, top=5):
        '''
        Finds closely similar units.
        '''
        more_results = more_like(unit.checksum, unit.source, top)

        same_results = fulltext_search(
            unit.get_source_plurals()[0],
            unit.translation.language.code,
            True, False, False
        )

        checksums = more_results - same_results

        return self.filter(
            checksum__in=checksums,
            translation__language=unit.translation.language,
            translated=True
        ).exclude(
            pk=unit.id
        )

    def same(self, unit):
        '''
        Units with same source within same project.
        '''
        project = unit.translation.subproject.project
        return self.filter(
            checksum=unit.checksum,
            translation__subproject__project=project,
            translation__language=unit.translation.language
        )


class Unit(models.Model):
    translation = models.ForeignKey(Translation)
    checksum = models.CharField(max_length=40, db_index=True)
    contentsum = models.CharField(max_length=40, db_index=True)
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

    def __init__(self, *args, **kwargs):
        '''
        Constructor to initialize some cache properties.
        '''
        super(Unit, self).__init__(*args, **kwargs)
        self._all_flags = None

    def has_acl(self, user):
        '''
        Checks whether current user is allowed to access this
        subproject.
        '''
        return self.translation.subproject.project.has_acl(user)

    def check_acl(self, request):
        '''
        Raises an error if user is not allowed to access this project.
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
        source = unit.get_source()
        comment = unit.get_comments()
        fuzzy = unit.is_fuzzy()
        translated = unit.is_translated()
        previous_source = unit.get_previous_source()
        contentsum = unit.get_contentsum()

        # Monolingual files handling (without target change)
        if unit.template is not None and target == self.target:
            if source != self.source and translated:
                # Store previous source and fuzzy flag for monolingual files
                if previous_source == '':
                    previous_source = self.source
                fuzzy = True
            else:
                # We should keep calculated flags if translation was
                # not changed outside
                previous_source = self.previous_source
                fuzzy = self.fuzzy

        # Update checks on fuzzy update or on content change
        same_content = (
            target == self.target
            and source == self.source
        )
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
                contentsum == self.contentsum and
                previous_source == self.previous_source):
            return

        # Store updated values
        self.position = pos
        self.location = location
        self.flags = flags
        self.source = source
        self.target = target
        self.fuzzy = fuzzy
        self.translated = translated
        self.comment = comment
        self.contentsum = contentsum
        self.previous_source = previous_source
        self.save(
            force_insert=created,
            backend=True,
            same_content=same_content,
            same_state=same_state
        )

        # Ensure we track source string
        dummy, created = Source.objects.get_or_create(
            checksum=self.checksum,
            subproject=self.translation.subproject
        )

        # Create change object for new source string
        if created:
            from weblate.trans.models.changes import Change

            Change.objects.create(
                translation=self.translation,
                action=Change.ACTION_NEW_SOURCE,
                unit=self,
            )

    def is_plural(self):
        '''
        Checks whether message is plural.
        '''
        return is_plural(self.source)

    def get_source_plurals(self):
        '''
        Returns source plurals in array.
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
            del ret[-1]

        return ret

    def propagate(self, request, change_action=None):
        '''
        Propagates current translation to all others.
        '''
        allunits = Unit.objects.same(self).exclude(id=self.id).filter(
            translation__subproject__allow_translation_propagation=True
        )
        for unit in allunits:
            unit.target = self.target
            unit.fuzzy = self.fuzzy
            unit.save_backend(request, False, change_action=change_action)

    def save_backend(self, request, propagate=True, gen_change=True,
                     change_action=None, user=None):
        '''
        Stores unit to backend.

        Optional user parameters defines authorship of a change.
        '''
        from weblate.accounts.models import (
            notify_new_translation, notify_new_contributor
        )
        from weblate.trans.models.changes import Change

        # Update lock timestamp
        self.translation.update_lock(request)

        # For case when authorship specified, use user from request
        if user is None:
            user = request.user

        # Store to backend
        try:
            (saved, pounit) = self.translation.update_unit(self, request, user)
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
            self.translation.check_sync(True)
            return False

        # Get old unit from database (for notifications)
        oldunit = Unit.objects.get(id=self.id)

        # Return if there was no change
        # We have to explicitly check for fuzzy flag change on monolingual
        # files, where we handle it ourselves without storing to backend
        if not saved and oldunit.fuzzy == self.fuzzy:
            # Propagate if we should
            if propagate:
                self.propagate(request, change_action)
            return False

        # Update translated flag
        self.translated = pounit.is_translated()

        # Update comments as they might have been changed (eg, fuzzy flag
        # removed)
        self.flags = pounit.get_flags()

        # Save updated unit to database
        self.save(backend=True)

        # Update translation stats
        old_translated = self.translation.translated
        self.translation.update_stats()

        # Notify subscribed users about new translation
        notify_new_translation(self, oldunit, request.user)

        # Update user stats
        user.profile.translated += 1
        user.profile.save()

        # Notify about new contributor
        user_changes = Change.objects.filter(
            translation=self.translation,
            user=request.user
        )
        if not user_changes.exists():
            notify_new_contributor(self, request.user)

        # Generate Change object for this change
        if gen_change:
            self.generate_change(request, user, oldunit, change_action)

        # Force commiting on completing translation
        if (old_translated < self.translation.translated
                and self.translation.translated == self.translation.total):
            self.translation.commit_pending(request)
            Change.objects.create(
                translation=self.translation,
                action=Change.ACTION_COMPLETE,
                user=request.user,
                author=user
            )

        # Propagate to other projects
        if propagate:
            self.propagate(request, change_action)

        return True

    def generate_change(self, request, author, oldunit, change_action):
        '''
        Creates Change entry for saving unit.
        '''
        from weblate.trans.models.changes import Change

        # Action type to store
        if change_action is not None:
            action = change_action
        elif oldunit.translated:
            action = Change.ACTION_CHANGE
        else:
            action = Change.ACTION_NEW

        # Should we store history of edits?
        if self.translation.subproject.save_history:
            history_target = self.target
        else:
            history_target = ''

        # Create change object
        Change.objects.create(
            unit=self,
            translation=self.translation,
            action=action,
            user=request.user,
            author=author,
            target=history_target
        )

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
            self.check(same_state, force_insert)

        # Update fulltext index if content has changed or this is a new unit
        if force_insert or not same_content:
            update_index_unit(self, force_insert)

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
        from weblate.trans.models.unitdata import Suggestion
        return Suggestion.objects.filter(
            contentsum=self.contentsum,
            project=self.translation.subproject.project,
            language=self.translation.language
        )

    def cleanup_checks(self, source, target):
        '''
        Cleanups listed source and target checks.
        '''
        from weblate.trans.models.unitdata import Check
        if len(source) == 0 and len(target) == 0:
            return False
        todelete = Check.objects.filter(
            contentsum=self.contentsum,
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
        '''
        Returns all checks for this unit (even ignored).
        '''
        from weblate.trans.models.unitdata import Check
        return Check.objects.filter(
            contentsum=self.contentsum,
            project=self.translation.subproject.project,
            language=self.translation.language
        )

    def source_checks(self):
        '''
        Returns all source checks for this unit (even ignored).
        '''
        from weblate.trans.models.unitdata import Check
        return Check.objects.filter(
            contentsum=self.contentsum,
            project=self.translation.subproject.project,
            language=None
        )

    def active_checks(self):
        '''
        Returns all active (not ignored) checks for this unit.
        '''
        from weblate.trans.models.unitdata import Check
        return Check.objects.filter(
            contentsum=self.contentsum,
            project=self.translation.subproject.project,
            language=self.translation.language,
            ignore=False
        )

    def active_source_checks(self):
        '''
        Returns all active (not ignored) source checks for this unit.
        '''
        from weblate.trans.models.unitdata import Check
        return Check.objects.filter(
            contentsum=self.contentsum,
            project=self.translation.subproject.project,
            language=None,
            ignore=False
        )

    def get_comments(self):
        '''
        Returns list of target comments.
        '''
        from weblate.trans.models.unitdata import Comment
        return Comment.objects.filter(
            contentsum=self.contentsum,
            project=self.translation.subproject.project,
            language=self.translation.language,
        )

    def get_source_comments(self):
        '''
        Returns list of target comments.
        '''
        from weblate.trans.models.unitdata import Comment
        return Comment.objects.filter(
            contentsum=self.contentsum,
            project=self.translation.subproject.project,
            language=None,
        )

    def get_checks_to_run(self, same_state, is_new):
        '''
        Returns list of checks to run on state change.

        Returns tupe of checks to run and whether to do cleanup.
        '''
        checks_to_run = CHECKS
        cleanup_checks = True

        if (same_state or is_new) and not self.translated:
            # Check whether there is any message with same source
            project = self.translation.subproject.project
            same_source = Unit.objects.filter(
                translation__language=self.translation.language,
                translation__subproject__project=project,
                contentsum=self.contentsum,
                translated=True,
            ).exclude(
                id=self.id,
                translation__subproject__allow_translation_propagation=False,
            )

            # Delete all checks if only message with this source is fuzzy
            if not same_source.exists():
                checks = self.checks()
                if checks.exists():
                    checks.delete()
                    self.update_has_failing_check(True)
                return ({}, False)

            # We run only checks which span across more units
            checks_to_run = {}

            # Consistency check checks across more translations
            if 'inconsistent' in CHECKS:
                checks_to_run['inconsistent'] = CHECKS['inconsistent']

            cleanup_checks = False

        return (checks_to_run, cleanup_checks)

    def check(self, same_state=True, is_new=False):
        '''
        Updates checks for this unit.
        '''
        from weblate.trans.models.unitdata import Check

        was_change = False

        checks_to_run, cleanup_checks = self.get_checks_to_run(
            same_state, is_new
        )

        if len(checks_to_run) == 0:
            return

        checks = self.checks()

        src = self.get_source_plurals()
        tgt = self.get_target_plurals()
        old_target_checks = set(checks.values_list('check', flat=True))
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
                        contentsum=self.contentsum,
                        project=self.translation.subproject.project,
                        language=self.translation.language,
                        ignore=False,
                        check=check
                    )
                    was_change = True
            # Source check
            if check_obj.source and check_obj.check_source(src, self):
                if check in old_source_checks:
                    # We already have this check
                    old_source_checks.remove(check)
                else:
                    # Create new check
                    Check.objects.create(
                        contentsum=self.contentsum,
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
        if was_change or is_new:
            self.update_has_failing_check(was_change)

    def update_has_failing_check(self, recurse=False):
        '''
        Updates flag counting failing checks.
        '''
        has_failing_check = not self.fuzzy and self.active_checks().exists()

        # Change attribute if it has changed
        if has_failing_check != self.has_failing_check:
            self.has_failing_check = has_failing_check
            self.save(backend=True, same_content=True, same_state=True)

            # Update translation stats
            self.translation.update_stats()

        # Invalidate checks cache if there was any change
        # (above code cares only about whether there is failing check
        # while here we care about any changed in checks)
        self.translation.invalidate_cache()

        if recurse:
            for unit in Unit.objects.same(self).exclude(id=self.id):
                unit.update_has_failing_check(False)

    def update_has_suggestion(self):
        '''
        Updates flag counting suggestions.
        '''
        has_suggestion = len(self.suggestions()) > 0
        if has_suggestion != self.has_suggestion:
            self.has_suggestion = has_suggestion
            self.save(backend=True, same_content=True, same_state=True)

            # Update translation stats
            self.translation.update_stats()

    def update_has_comment(self):
        '''
        Updates flag counting comments.
        '''
        has_comment = len(self.get_comments()) > 0
        if has_comment != self.has_comment:
            self.has_comment = has_comment
            self.save(backend=True, same_content=True, same_state=True)

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

    def can_vote_suggestions(self):
        '''
        Whether we can vote for suggestions.
        '''
        return self.translation.subproject.suggestion_voting

    def only_vote_suggestions(self):
        '''
        Whether we can vote for suggestions.
        '''
        return (
            self.translation.subproject.suggestion_voting
            and self.translation.subproject.suggestion_autoaccept > 0
        )

    def translate(self, request, new_target, new_fuzzy):
        '''
        Stores new translation of a unit.
        '''
        # Update unit and save it
        self.target = join_plural(new_target)
        self.fuzzy = new_fuzzy
        saved = self.save_backend(request)

        return saved

    @property
    def all_flags(self):
        '''
        Returns union of own and subproject flags.
        '''
        if self._all_flags is None:
            self._all_flags = set(
                self.flags.split(',')
                + self.translation.subproject.all_flags
            )
        return self._all_flags

    def get_state_flags(self):
        '''
        Returns state flags.
        '''
        flags = []

        if self.fuzzy:
            flags.append((
                _('Message is fuzzy'),
                'help'
            ))
        elif not self.translated:
            flags.append((
                _('Message is not translated'),
                'document-b'
            ))
        elif self.has_failing_check:
            flags.append((
                _('Message has failing checks'),
                'notice'
            ))
        elif self.translated:
            flags.append((
                _('Message is translated'),
                'check'
            ))

        if self.has_comment:
            flags.append((
                _('Message has comments'),
                'comment'
            ))

        return mark_safe(
            '\n'.join([FLAG_TEMPLATE % flag for flag in flags])
        )

    def get_source_string_info(self):
        '''
        Returns related source string object.
        '''
        try:
            return Source.objects.get(
                checksum=self.checksum,
                subproject=self.translation.subproject
            )
        except Source.DoesNotExist:
            return None
