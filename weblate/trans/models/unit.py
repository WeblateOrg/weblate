# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

import re
from copy import copy

import six
from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property

from weblate.checks import CHECKS
from weblate.checks.flags import Flags
from weblate.checks.models import Check
from weblate.memory.tasks import update_memory
from weblate.trans.mixins import LoggerMixin
from weblate.trans.models.change import Change
from weblate.trans.models.comment import Comment
from weblate.trans.models.source import Source
from weblate.trans.models.suggestion import Suggestion
from weblate.trans.search import Fulltext
from weblate.trans.signals import unit_pre_create
from weblate.trans.util import (
    get_distinct_translations,
    is_plural,
    join_plural,
    split_plural,
)
from weblate.utils.errors import report_error
from weblate.utils.hash import calculate_hash, hash_to_checksum
from weblate.utils.search import parse_query
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_CHOICES,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_TRANSLATED,
)

SIMPLE_FILTERS = {
    'fuzzy': {'state': STATE_FUZZY},
    'approved': {'state': STATE_APPROVED},
    'approved_suggestions': {'state': STATE_APPROVED, 'has_suggestion': True},
    'unapproved': {'state': STATE_TRANSLATED},
    'todo': {'state__lt': STATE_TRANSLATED},
    'nottranslated': {'state': STATE_EMPTY},
    'translated': {'state__gte': STATE_TRANSLATED},
    'suggestions': {'has_suggestion': True},
    'nosuggestions': {'has_suggestion': False, 'state__lt': STATE_TRANSLATED},
    'comments': {'has_comment': True},
}

SEARCH_FILTERS = ('source', 'target', 'context', 'location', 'comment')

NEWLINES = re.compile(r'\r\n|\r|\n')


class UnitQuerySet(models.QuerySet):
    def filter_checks(self, rqtype, project, language, ignored=False, strict=False):
        """Filtering for checks."""

        # Filter checks for current project
        checks = Check.objects.filter(ignore=ignored)

        if project is not None:
            checks = checks.filter(project=project)

        # Filter by language
        if rqtype == 'allchecks':
            return self.filter(has_failing_check=True)
        if rqtype == 'sourcechecks':
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

    def filter_type(self, rqtype, project, language, ignored=False, strict=False):
        """Basic filtering based on unit state or failed checks."""
        if rqtype in SIMPLE_FILTERS:
            return self.filter(**SIMPLE_FILTERS[rqtype])
        if rqtype == 'sourcecomments':
            coms = Comment.objects.filter(language=None)
            if project is not None:
                coms = coms.filter(project=project)
            coms = coms.values_list('content_hash', flat=True)
            return self.filter(content_hash__in=coms)
        elif rqtype.startswith('check:') or rqtype in ['allchecks', 'sourcechecks']:
            return self.filter_checks(rqtype, project, language, ignored, strict=strict)
        elif rqtype == 'all':
            return self.all()
        elif strict:
            raise ValueError('Unknown filter: {}'.format(rqtype))
        # Catch anything not matching
        return self.all()

    def review(
        self,
        date,
        exclude_user,
        only_user,
        project=None,
        component=None,
        language=None,
        translation=None,
    ):
        """Return units touched by other users since given time."""
        # Filter out changes we're interested in
        changes = Change.objects.content()
        if date:
            changes = changes.filter(timestamp__gte=date)
        if exclude_user:
            changes = changes.exclude(Q(author=exclude_user) | Q(user=exclude_user))
        if only_user:
            changes = changes.filter(Q(author=only_user) | Q(user=only_user))
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

    def search(
        self, params, project=None, component=None, language=None, translation=None
    ):
        """High level wrapper for searching."""
        if translation is not None:
            component = translation.component
            language = translation.language
        if component is not None:
            project = component.project

        base = self.prefetch()
        if params['type'] != 'all':
            base = self.filter_type(
                params['type'], project, language, params.get('ignored', False)
            )

        if params.get('date') or params.get('exclude_user') or params.get('only_user'):
            base = base.review(
                params.get('date'),
                params.get('exclude_user'),
                params.get('only_user'),
                project,
                component,
                language,
                translation,
            )

        if 'lang' in params and params['lang']:
            base = base.filter(translation__language__code__in=params['lang'])

        if 'q' not in params or not params['q']:
            return base

        return base.filter(parse_query(params['q']))

    def more_like_this(self, unit, top=5):
        """Find closely similar units."""
        more_results = Fulltext().more_like(unit.pk, unit.source, top)

        return self.filter(
            pk__in=more_results,
            translation__language=unit.translation.language,
            state__gte=STATE_TRANSLATED,
        )

    def same(self, unit, exclude=True):
        """Unit with same source within same project."""
        project = unit.translation.component.project
        result = self.filter(
            content_hash=unit.content_hash,
            translation__component__project=project,
            translation__language=unit.translation.language,
        )
        if exclude:
            result = result.exclude(pk=unit.id)
        return result

    def get_unit(self, ttunit):
        """Find unit matching translate-toolkit unit

        This is used for import, so kind of fuzzy matching is expected.
        """
        source = ttunit.source
        context = ttunit.context

        params = [{'source': source, 'context': context}, {'source': source}]
        # Try empty context first before matching any context
        if context != '':
            params.insert(1, {'source': source, 'context': ''})
        # Special case for XLIFF
        if '///' in context:
            params.insert(1, {'source': source, 'context': context.split('///', 1)[1]})

        for param in params:
            try:
                return self.get(**param)
            except (Unit.DoesNotExist, Unit.MultipleObjectsReturned):
                continue

        raise Unit.DoesNotExist('No matching unit found!')

    def order(self):
        return self.order_by('-priority', 'position')


@python_2_unicode_compatible
class Unit(models.Model, LoggerMixin):

    translation = models.ForeignKey('Translation', on_delete=models.deletion.CASCADE)
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
        default=STATE_EMPTY, db_index=True, choices=STATE_CHOICES
    )

    position = models.IntegerField()

    has_suggestion = models.BooleanField(default=False, db_index=True)
    has_comment = models.BooleanField(default=False, db_index=True)
    has_failing_check = models.BooleanField(default=False, db_index=True)

    num_words = models.IntegerField(default=0)

    priority = models.IntegerField(default=100)

    pending = models.BooleanField(default=False)

    objects = UnitQuerySet.as_manager()

    class Meta(object):
        app_label = 'trans'
        unique_together = ('translation', 'id_hash')
        index_together = [('translation', 'pending'), ('priority', 'position')]

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super(Unit, self).__init__(*args, **kwargs)
        self.old_unit = copy(self)
        self.is_batch_update = False

    def __str__(self):
        if self.translation.is_template:
            return self.context
        if self.context:
            return '[{}] {}'.format(self.context, self.source)
        return self.source

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
    def full_slug(self):
        return '/'.join(
            (
                self.translation.component.project.slug,
                self.translation.component.slug,
                self.translation.language.code,
                str(self.pk),
            )
        )

    def get_absolute_url(self):
        return '{0}?checksum={1}'.format(
            self.translation.get_translate_url(), self.checksum
        )

    def get_unit_state(self, unit):
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
        if approved and self.translation.component.project.enable_review:
            return STATE_APPROVED
        return STATE_TRANSLATED

    def update_from_unit(self, unit, pos, created):
        """Update Unit from ttkit unit."""
        component = self.translation.component
        self.is_batch_update = True
        # Get unit attributes
        try:
            location = unit.locations
            flags = unit.flags
            target = unit.target
            source = unit.source
            context = unit.context
            comment = unit.comments
            state = self.get_unit_state(unit)
            previous_source = unit.previous_source
            content_hash = unit.content_hash
        except Exception as error:
            self.translation.component.handle_parse_error(error, self.translation)

        # Monolingual files handling (without target change)
        if not created and unit.template is not None and target == self.target:
            if source != self.source and state >= STATE_TRANSLATED:
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
        same_target = target == self.target
        same_source = source == self.source and context == self.context
        same_state = state == self.state and flags == self.flags

        # Check if we actually need to change anything
        # pylint: disable=too-many-boolean-expressions
        if (
            location == self.location
            and flags == self.flags
            and same_source
            and same_target
            and same_state
            and comment == self.comment
            and pos == self.position
            and content_hash == self.content_hash
            and previous_source == self.previous_source
        ):
            return

        # Ensure we track source string
        source_info, source_created = component.get_source(self.id_hash)

        self.__dict__['source_info'] = source_info

        # Store updated values
        self.position = pos
        self.location = location
        self.flags = flags
        self.source = source
        self.target = target
        self.state = state
        self.context = context
        self.comment = comment
        self.content_hash = content_hash
        self.previous_source = previous_source
        self.update_priority(save=False)

        # Sanitize number of plurals
        if self.is_plural():
            self.target = join_plural(self.get_target_plurals())

        if created:
            unit_pre_create.send(sender=self.__class__, unit=self)

        # Save into database
        self.save(
            force_insert=created,
            same_content=same_source and same_target,
            same_state=same_state,
        )

        # Create change object for new source string
        if source_created:
            Change.objects.create(action=Change.ACTION_NEW_SOURCE, unit=self)

        # Track updated sources for source checks
        if source_created or not same_source:
            component.updated_sources[self.id_hash] = self

    def update_priority(self, save=True):
        if self.all_flags.has_value('priority'):
            priority = self.all_flags.get_value('priority')
        else:
            priority = 100
        if self.priority != priority:
            self.priority = priority
            if save:
                self.save(
                    same_content=True, same_state=True, update_fields=['priority']
                )

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

    def propagate(self, user, change_action=None, author=None):
        """Propagate current translation to all others."""
        result = False
        for unit in self.same_source_units:
            if not user.has_perm('unit.edit', unit):
                continue
            if unit.target == self.target and unit.state == self.state:
                continue
            unit.target = self.target
            unit.state = self.state
            unit.save_backend(user, False, change_action=change_action, author=None)
            result = True
        return result

    def save_backend(self, user, propagate=True, change_action=None, author=None):
        """
        Stores unit to backend.

        Optional user parameters defines authorship of a change.

        This should be always called in a trasaction with updated unit
        locked for update.
        """
        # For case when authorship specified, use user
        author = author or user

        # Commit possible previous changes on this unit
        if self.pending:
            change_author = self.get_last_content_change()[0]
            if change_author != author:
                self.translation.commit_pending('pending unit', user, force=True)

        # Propagate to other projects
        # This has to be done before changing source/content_hash for template
        propagated = False
        if propagate:
            propagated = self.propagate(user, change_action, author=author)

        # Return if there was no change
        # We have to explicitly check for fuzzy flag change on monolingual
        # files, where we handle it ourselves without storing to backend
        if self.old_unit.state == self.state and self.old_unit.target == self.target:
            return False

        if self.translation.is_template:
            self.source = self.target
            self.content_hash = calculate_hash(self.source, self.context)

        # Unit is pending for write
        self.pending = True
        # Update translated flag (not fuzzy and at least one translation)
        translation = bool(max(self.get_target_plurals()))
        if self.state >= STATE_TRANSLATED and not translation:
            self.state = STATE_EMPTY
        elif self.state == STATE_EMPTY and translation:
            self.state = STATE_TRANSLATED

        # Save updated unit to database
        self.save()

        # Run source checks
        self.source_info.run_checks(unit=self)

        # Generate Change object for this change
        self.generate_change(user or author, author, change_action)

        if change_action not in (Change.ACTION_UPLOAD, Change.ACTION_AUTO):
            # Update translation stats
            self.translation.invalidate_cache(recurse=propagated)

            # Update user stats
            author.profile.translated += 1
            author.profile.save()

        # Update related source strings if working on a template
        if self.translation.is_template:
            self.update_source_units(self.old_unit.source, user or author, author)

        return True

    def update_source_units(self, previous_source, user, author):
        """Update source for units withing same component.

        This is needed when editing template translation for monolingual
        formats.
        """
        # Find relevant units
        same_source = Unit.objects.filter(
            translation__component=self.translation.component, id_hash=self.id_hash
        ).exclude(id=self.id)
        for unit in same_source.iterator():
            # Update source, number of words and content_hash
            unit.source = self.source
            unit.num_words = self.num_words
            unit.content_hash = self.content_hash
            # Find reverted units
            if unit.state == STATE_FUZZY and unit.previous_source == self.source:
                # Unset fuzzy on reverted
                unit.state = STATE_TRANSLATED
                unit.previous_source = ''
            elif unit.state >= STATE_TRANSLATED:
                # Set fuzzy on changed
                unit.state = STATE_FUZZY
                unit.previous_source = previous_source

            # Update source index and stats
            unit.update_has_comment()
            unit.update_has_suggestion()
            unit.save()
            Fulltext.update_index_unit(unit)
            Change.objects.create(
                unit=unit,
                action=Change.ACTION_SOURCE_CHANGE,
                user=user,
                author=author,
                old=previous_source,
                target=self.source,
            )
            unit.translation.invalidate_cache()

    def generate_change(self, user, author, change_action):
        """Create Change entry for saving unit."""
        # Notify about new contributor
        user_changes = Change.objects.filter(translation=self.translation, user=user)
        if not user_changes.exists():
            Change.objects.create(
                unit=self,
                action=Change.ACTION_NEW_CONTRIBUTOR,
                user=user,
                author=author,
            )

        # Action type to store
        if change_action is not None:
            action = change_action
        elif self.state == STATE_FUZZY:
            action = Change.ACTION_MARKED_EDIT
        elif self.old_unit.state >= STATE_TRANSLATED:
            if self.state == STATE_APPROVED:
                action = Change.ACTION_APPROVE
            else:
                action = Change.ACTION_CHANGE
        else:
            action = Change.ACTION_NEW

        # Create change object
        Change.objects.create(
            unit=self,
            action=action,
            user=user,
            author=author,
            target=self.target,
            old=self.old_unit.target,
        )

    def save(self, same_content=False, same_state=False, force_insert=False, **kwargs):
        """
        Wrapper around save to warn when save did not come from
        git backend (eg. commit or by parsing file).
        """
        # Store number of words
        if not same_content or not self.num_words:
            self.num_words = len(self.get_source_plurals()[0].split())

        # Actually save the unit
        super(Unit, self).save(**kwargs)

        # Update checks if content or fuzzy flag has changed
        if not same_content or not same_state:
            self.run_checks(same_state, same_content)

        # Update fulltext index if content has changed or this is a new unit
        if force_insert or not same_content:
            Fulltext.update_index_unit(self)

    @cached_property
    def suggestions(self):
        """Return all suggestions for this unit."""
        return Suggestion.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=self.translation.language,
        ).order()

    def checks(self, values=False):
        """Return all checks names for this unit (even ignored)."""
        if values and self.translation.component.checks_cache is not None:
            key = (self.content_hash, self.translation.language_id)
            return self.translation.component.checks_cache.get(key, [])
        result = Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=self.translation.language,
        )
        if values:
            return result.values_list('check', flat=True)
        return result

    def source_checks(self):
        """Return all source checks for this unit (even ignored)."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=None,
        )

    def active_checks(self):
        """Return all active (not ignored) checks for this unit."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=self.translation.language,
            ignore=False,
        )

    def active_source_checks(self):
        """Return all active (not ignored) source checks for this unit."""
        return Check.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=None,
            ignore=False,
        )

    def get_comments(self):
        """Return list of target comments."""
        return (
            Comment.objects.filter(
                content_hash=self.content_hash,
                project=self.translation.component.project,
            )
            .filter(Q(language=self.translation.language) | Q(language=None))
            .order()
        )

    def get_source_comments(self):
        """Return list of target comments."""
        return Comment.objects.filter(
            content_hash=self.content_hash,
            project=self.translation.component.project,
            language=None,
        ).order()

    def run_checks(self, same_state=True, same_content=True):
        """Update checks for this unit."""
        was_change = False
        has_checks = None

        if self.translation.is_template:
            checks_to_run = {}
        else:
            checks_to_run = CHECKS.data

        src = self.get_source_plurals()
        tgt = self.get_target_plurals()
        content_hash = self.content_hash
        project = self.translation.component.project
        language = self.translation.language
        old_checks = set(self.checks(True))
        create = []

        # Run all target checks
        for check, check_obj in checks_to_run.items():
            if self.is_batch_update and check_obj.batch_update:
                old_checks.discard(check)
                continue
            if check_obj.check_target(src, tgt, self):
                if check in old_checks:
                    # We already have this check
                    old_checks.remove(check)
                else:
                    # Create new check
                    create.append(
                        Check(
                            content_hash=content_hash,
                            project=project,
                            language=language,
                            ignore=False,
                            check=check,
                        )
                    )
                    was_change = True
                    has_checks = True

        if create:
            Check.objects.bulk_create_ignore(create)

        # Delete no longer failing checks
        if old_checks:
            was_change = True
            Check.objects.filter(
                content_hash=content_hash,
                project=project,
                language=language,
                check__in=old_checks,
            ).delete()

        # Update failing checks flag
        if not self.is_batch_update and (was_change or not same_content):
            self.update_has_failing_check(was_change, has_checks)

    def update_has_failing_check(
        self, recurse=False, has_checks=None, invalidate=False
    ):
        """Update flag counting failing checks."""
        if has_checks is None:
            has_checks = self.active_checks().exists()

        # Change attribute if it has changed
        if has_checks != self.has_failing_check:
            self.has_failing_check = has_checks
            self.save(
                same_content=True, same_state=True, update_fields=['has_failing_check']
            )
            if invalidate:
                self.translation.invalidate_cache()

        if recurse:
            for unit in Unit.objects.prefetch().same(self):
                unit.update_has_failing_check(False, has_checks, invalidate)

    def update_has_suggestion(self):
        """Update flag counting suggestions."""
        has_suggestion = len(self.suggestions) > 0
        if has_suggestion != self.has_suggestion:
            self.has_suggestion = has_suggestion
            self.save(
                same_content=True, same_state=True, update_fields=['has_suggestion']
            )
            return True
        return False

    def update_has_comment(self):
        """Update flag counting comments."""
        has_comment = len(self.get_comments()) > 0
        if has_comment != self.has_comment:
            self.has_comment = has_comment
            self.save(same_content=True, same_state=True, update_fields=['has_comment'])
            return True
        return False

    def nearby(self):
        """Return list of nearby messages based on location."""
        return (
            Unit.objects.prefetch()
            .order_by('position')
            .filter(
                translation=self.translation,
                position__gte=self.position - settings.NEARBY_MESSAGES,
                position__lte=self.position + settings.NEARBY_MESSAGES,
            )
        )

    @transaction.atomic
    def translate(
        self, user, new_target, new_state, change_action=None, propagate=True
    ):
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

        # Newlines fixup
        if 'dos-eol' in self.all_flags:
            self.target = NEWLINES.sub('\r\n', self.target)

        if not_empty:
            self.state = new_state
        else:
            self.state = STATE_EMPTY
        saved = self.save_backend(
            user, change_action=change_action, propagate=propagate
        )
        if (
            propagate
            and user
            and self.target != self.old_unit.target
            and self.state >= STATE_TRANSLATED
        ):
            update_memory(user, self)

        return saved

    @cached_property
    def all_flags(self):
        """Return union of own and component flags."""
        return Flags(
            self.translation.component.all_flags,
            self.source_info.check_flags,
            self.flags,
        )

    @cached_property
    def source_info(self):
        """Return related source string object."""
        return Source.objects.get(
            id_hash=self.id_hash, component=self.translation.component
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

    @cached_property
    def same_source_units(self):
        return (
            Unit.objects.same(self)
            .prefetch()
            .filter(translation__component__allow_translation_propagation=True)
        )

    def get_max_length(self):
        """Returns maximal translation length."""
        if not self.pk:
            return 10000
        if self.all_flags.has_value('max-length'):
            return self.all_flags.get_value('max-length')
        if settings.LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH:
            # Fallback to reasonably big value
            return max(100, len(self.get_source_plurals()[0]) * 10)
        return 10000

    def get_target_hash(self):
        return calculate_hash(None, self.target)

    def get_last_content_change(self, silent=False):
        """Wrapper to get last content change metadata

        Used when commiting pending changes, needs to handle and report
        inconsistencies from past releases.
        """
        from weblate.auth.models import get_anonymous

        try:
            change = self.change_set.content().order_by('-timestamp')[0]
            return change.author or get_anonymous(), change.timestamp
        except IndexError as error:
            if not silent:
                report_error(error, level='error')
            return get_anonymous(), timezone.now()
