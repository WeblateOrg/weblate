# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import os
import codecs
from datetime import timedelta

from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q, Sum, Count
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.utils import timezone
from django.core.urlresolvers import reverse

from weblate import appsettings
from weblate.lang.models import Language
from weblate.trans.formats import AutoFormat, StringIOMode, ParseError
from weblate.trans.checks import CHECKS
from weblate.trans.models.unit import Unit
from weblate.trans.models.unitdata import Suggestion
from weblate.trans.signals import vcs_pre_commit, vcs_post_commit
from weblate.trans.site import get_site_url
from weblate.trans.util import translation_percent, split_plural
from weblate.accounts.avatar import get_user_display
from weblate.trans.mixins import URLMixin, PercentMixin, LoggerMixin
from weblate.trans.boolean_sum import do_boolean_sum
from weblate.accounts.models import notify_new_string, get_author_name
from weblate.trans.models.changes import Change
from weblate.trans.checklists import TranslationChecklist


class TranslationManager(models.Manager):
    # pylint: disable=W0232

    def prefetch(self):
        return self.select_related(
            'subproject', 'subproject__project', 'language'
        )

    def check_sync(self, subproject, lang, code, path, force=False,
                   request=None):
        """Parses translation meta info and updates translation object"""
        translation, dummy = self.get_or_create(
            language=lang,
            subproject=subproject,
            defaults={
                'filename': path,
                'language_code': code,
            },
        )
        if translation.filename != path or translation.language_code != code:
            force = True
            translation.filename = path
            translation.language_code = code
        translation.check_sync(force, request=request)

        return translation

    def enabled(self):
        """Filters enabled translations."""
        return self.prefetch().filter(enabled=True)

    def get_percents(self, project=None, subproject=None, language=None):
        """Returns tuple consting of status percents:

        (translated, fuzzy, failing checks)
        """
        # Filter translations
        translations = self
        if project is not None:
            translations = translations.filter(subproject__project=project)
        if subproject is not None:
            translations = translations.filter(subproject=subproject)
        if language is not None:
            translations = translations.filter(language=language)

        # Aggregate
        translations = translations.aggregate(
            Sum('translated'),
            Sum('fuzzy'),
            Sum('failing_checks'),
            Sum('total'),
        )

        total = translations['total__sum']

        # Catch no translations (division by zero)
        if total == 0 or total is None:
            return (100, 0, 0)

        # Fetch values
        result = [
            translations['translated__sum'],
            translations['fuzzy__sum'],
            translations['failing_checks__sum'],
        ]
        # Calculate percent
        return tuple([translation_percent(value, total) for value in result])


@python_2_unicode_compatible
class Translation(models.Model, URLMixin, PercentMixin, LoggerMixin):
    subproject = models.ForeignKey('SubProject')
    language = models.ForeignKey(Language)
    revision = models.CharField(max_length=100, default='', blank=True)
    filename = models.CharField(max_length=200)

    translated = models.IntegerField(default=0, db_index=True)
    fuzzy = models.IntegerField(default=0, db_index=True)
    total = models.IntegerField(default=0, db_index=True)
    translated_words = models.IntegerField(default=0)
    fuzzy_words = models.IntegerField(default=0)
    failing_checks_words = models.IntegerField(default=0)
    total_words = models.IntegerField(default=0)
    failing_checks = models.IntegerField(default=0, db_index=True)
    have_suggestion = models.IntegerField(default=0, db_index=True)
    have_comment = models.IntegerField(default=0, db_index=True)

    enabled = models.BooleanField(default=True, db_index=True)

    language_code = models.CharField(max_length=20, default='', blank=True)

    lock_user = models.ForeignKey(User, null=True, blank=True, default=None)
    lock_time = models.DateTimeField(default=timezone.now)

    commit_message = models.TextField(default='', blank=True)

    objects = TranslationManager()

    is_lockable = False

    class Meta(object):
        ordering = ['language__name']
        permissions = (
            ('upload_translation', "Can upload translation"),
            ('overwrite_translation', "Can overwrite with translation upload"),
            ('author_translation', "Can define author of translation upload"),
            ('commit_translation', "Can force commiting of translation"),
            ('update_translation', "Can update translation from VCS"),
            ('push_translation', "Can push translations to remote VCS"),
            (
                'reset_translation',
                "Can reset translations to match remote VCS"
            ),
            ('automatic_translation', "Can do automatic translation"),
            ('lock_translation', "Can lock whole translation project"),
            ('use_mt', "Can use machine translation"),
        )
        app_label = 'trans'
        unique_together = ('subproject', 'language')

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super(Translation, self).__init__(*args, **kwargs)
        self._store = None
        self._last_change_obj = None
        self._last_change_obj_valid = False

    @property
    def log_prefix(self):
        return '/'.join((
            self.subproject.project.slug,
            self.subproject.slug,
            self.language.code,
        ))

    def get_full_slug(self):
        return '__'.join((
            self.subproject.project.slug,
            self.subproject.slug,
            self.language.code,
        ))

    def has_acl(self, user):
        """Checks whether current user is allowed to access this object"""
        return self.subproject.project.has_acl(user)

    def check_acl(self, request):
        """Raises an error if user is not allowed to access this project."""
        self.subproject.project.check_acl(request)

    def is_template(self):
        """Checks whether this is template translation

        This means that translations should be propagated as sources to others.
        """
        return self.filename == self.subproject.template

    def clean(self):
        """
        Validates that filename exists and can be opened using
        translate-toolkit.
        """
        if not os.path.exists(self.get_filename()):
            raise ValidationError(
                _(
                    'Filename %s not found in repository! To add new '
                    'translation, add language file into repository.'
                ) %
                self.filename
            )
        try:
            self.load_store()
        except Exception as error:
            raise ValidationError(
                _('Failed to parse file %(file)s: %(error)s') % {
                    'file': self.filename,
                    'error': str(error)
                }
            )

    def _get_percents(self):
        """Returns percentages of translation status."""
        # No units?
        if self.total == 0:
            return (100, 0, 0)

        return (
            translation_percent(self.translated, self.total),
            translation_percent(self.fuzzy, self.total),
            translation_percent(self.failing_checks, self.total),
        )

    def get_words_percent(self):
        if self.total_words == 0:
            return 0
        return translation_percent(self.translated_words, self.total_words)

    def get_fuzzy_words_percent(self):
        if self.total_words == 0:
            return 0
        return translation_percent(self.fuzzy_words, self.total_words)

    def get_failing_checks_words_percent(self):
        if self.total_words == 0:
            return 0
        return translation_percent(self.failing_checks_words, self.total_words)

    @property
    def untranslated_words(self):
        return self.total_words - self.translated_words

    @property
    def untranslated(self):
        return self.total - self.translated

    def get_lock_user_display(self):
        """Returns formatted lock user."""
        return get_user_display(self.lock_user)

    def get_lock_display(self):
        return mark_safe(
            _('This translation is locked by %(user)s!') % {
                'user': self.get_lock_user_display(),
            }
        )

    def is_locked(self, user=None):
        """Check whether the translation is locked

        Possibly emits messages if request object is provided.
        """
        return (
            self.is_user_locked(user) or
            self.subproject.locked
        )

    def is_user_locked(self, user=None):
        """Checks whether there is valid user lock on this translation."""
        # Any user?
        if self.lock_user is None:
            return False
        # Is lock still valid?
        elif self.lock_time < timezone.now():
            # Clear the lock
            self.create_lock(None)

            return False

        # Is current user the one who has locked?
        elif user is not None and self.lock_user == user:
            return False

        else:
            return True

    def create_lock(self, user, explicit=False):
        """Creates lock on translation."""
        is_new = self.lock_user is None
        self.lock_user = user

        # Clean timestamp on unlock
        if user is None:
            self.lock_time = timezone.now()
            self.save()
            return

        self.update_lock_time(explicit, is_new)

    def update_lock_time(self, explicit=False, is_new=True):
        """Sets lock timestamp."""
        if explicit:
            seconds = appsettings.LOCK_TIME
        else:
            seconds = appsettings.AUTO_LOCK_TIME

        new_lock_time = timezone.now() + timedelta(seconds=seconds)

        if is_new or new_lock_time > self.lock_time:
            self.lock_time = new_lock_time

        self.save()

    def update_lock(self, user, create=True):
        """Updates lock timestamp."""
        # Check if we can lock
        if self.is_user_locked(user):
            return False

        # Update timestamp
        if self.lock_user == user:
            self.update_lock_time()
            return True

        # Auto lock if we should
        if appsettings.AUTO_LOCK and create:
            self.create_lock(user)
            return True

        return False

    def _reverse_url_name(self):
        """Returns base name for URL reversing."""
        return 'translation'

    def _reverse_url_kwargs(self):
        """Returns kwargs for URL reversing."""
        return {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        }

    def get_widgets_url(self):
        """Returns absolute URL for widgets."""
        return get_site_url(
            '%s?lang=%s' % (
                reverse(
                    'widgets', kwargs={
                        'project': self.subproject.project.slug,
                    }
                ),
                self.language.code,
            )
        )

    def get_share_url(self):
        """Returns absolute URL usable for sharing."""
        return get_site_url(
            reverse(
                'engage-lang',
                kwargs={
                    'project': self.subproject.project.slug,
                    'lang': self.language.code
                }
            )
        )

    @models.permalink
    def get_translate_url(self):
        return ('translate', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    def __str__(self):
        return '%s - %s' % (
            force_text(self.subproject),
            force_text(self.language)
        )

    def get_filename(self):
        """Returns absolute filename."""
        return os.path.join(self.subproject.get_path(), self.filename)

    def load_store(self):
        """Loads translate-toolkit storage from disk."""
        return self.subproject.file_format_cls.parse(
            self.get_filename(),
            self.subproject.template_store,
            language_code=self.language_code
        )

    def supports_language_pack(self):
        """Checks whether we support language pack download."""
        return self.subproject.file_format_cls.language_pack is not None

    @property
    def store(self):
        """Returns translate-toolkit storage object for a translation."""
        if self._store is None:
            try:
                self._store = self.load_store()
            except ParseError:
                raise
            except Exception as exc:
                self.subproject.handle_parse_error(exc, self)
        return self._store

    def check_sync(self, force=False, request=None, change=None):
        """Checks whether database is in sync with git and possibly updates"""

        if change is None:
            change = Change.ACTION_UPDATE
        if request is None:
            user = None
        else:
            user = request.user

        # Check if we're not already up to date
        if self.revision != self.get_git_blob_hash():
            reason = 'revision has changed'
        elif force:
            reason = 'check forced'
        else:
            return

        self.log_info(
            'processing %s, %s',
            self.filename,
            reason,
        )

        # List of created units (used for cleanup and duplicates detection)
        created_units = set()

        # Was there change?
        was_new = False
        # Position of current unit
        pos = 1

        for unit in self.store.all_units():
            if not unit.is_translatable():
                continue

            newunit, is_new = Unit.objects.update_from_unit(
                self, unit, pos
            )

            # Check if unit is new and untranslated
            was_new = (
                was_new or
                (is_new and not newunit.translated) or
                (
                    not newunit.translated and
                    newunit.translated != newunit.old_translated
                ) or
                (newunit.fuzzy and newunit.fuzzy != newunit.old_fuzzy)
            )

            # Update position
            pos += 1

            # Check for possible duplicate units
            if newunit.id in created_units:
                self.log_error(
                    'duplicate string to translate: %s (%s)',
                    newunit,
                    repr(newunit.source)
                )
                Change.objects.create(
                    unit=newunit,
                    translation=self,
                    action=Change.ACTION_DUPLICATE_STRING,
                    user=user,
                    author=user
                )

            # Store current unit ID
            created_units.add(newunit.id)

        # Following query can get huge, so we should find better way
        # to delete stale units, probably sort of garbage collection

        # We should also do cleanup on source strings tracking objects

        # Get lists of stale units to delete
        units_to_delete = self.unit_set.exclude(
            id__in=created_units
        )
        # We need to resolve this now as otherwise list will become empty after
        # delete
        deleted_units = units_to_delete.count()

        # Actually delete units
        units_to_delete.delete()

        # Update revision and stats
        self.update_stats()

        # Cleanup checks cache if there were some deleted units
        if deleted_units:
            self.invalidate_cache()

        # Store change entry
        Change.objects.create(
            translation=self,
            action=change,
            user=user,
            author=user
        )

        # Notify subscribed users
        if was_new:
            notify_new_string(self)

    def get_last_remote_commit(self):
        return self.subproject.get_last_remote_commit()

    def do_update(self, request=None, method=None):
        return self.subproject.do_update(request, method=method)

    def do_push(self, request=None):
        return self.subproject.do_push(request)

    def do_reset(self, request=None):
        return self.subproject.do_reset(request)

    def can_push(self):
        return self.subproject.can_push()

    def get_git_blob_hash(self):
        """Returns current VCS blob hash for file."""
        ret = self.subproject.repository.get_object_hash(self.get_filename())

        if not self.subproject.has_template():
            return ret

        return ','.join([
            ret,
            self.subproject.repository.get_object_hash(
                self.subproject.template
            )
        ])

    def update_stats(self):
        """Updates translation statistics."""
        # Grab stats
        stats = self.unit_set.aggregate(
            Sum('num_words'),
            Count('id'),
            fuzzy__sum=do_boolean_sum('fuzzy'),
            translated__sum=do_boolean_sum('translated'),
            has_failing_check__sum=do_boolean_sum('has_failing_check'),
            has_suggestion__sum=do_boolean_sum('has_suggestion'),
            has_comment__sum=do_boolean_sum('has_comment'),
        )

        # Check if we have any units
        if stats['num_words__sum'] is None:
            self.total_words = 0
            self.total = 0
            self.fuzzy = 0
            self.translated = 0
            self.failing_checks = 0
            self.have_suggestion = 0
            self.have_comment = 0
        else:
            self.total_words = stats['num_words__sum']
            self.total = stats['id__count']
            self.fuzzy = int(stats['fuzzy__sum'])
            self.translated = int(stats['translated__sum'])
            self.failing_checks = int(stats['has_failing_check__sum'])
            self.have_suggestion = int(stats['has_suggestion__sum'])
            self.have_comment = int(stats['has_comment__sum'])

        # Count translated words
        self.translated_words = self.unit_set.filter(
            translated=True
        ).aggregate(
            Sum('num_words')
        )['num_words__sum']
        # Nothing matches filter
        if self.translated_words is None:
            self.translated_words = 0

        # Count fuzzy words
        self.fuzzy_words = self.unit_set.filter(
            fuzzy=True
        ).aggregate(
            Sum('num_words')
        )['num_words__sum']
        # Nothing matches filter
        if self.fuzzy_words is None:
            self.fuzzy_words = 0

        # Count words with failing checks
        self.failing_checks_words = self.unit_set.filter(
            has_failing_check=True
        ).aggregate(
            Sum('num_words')
        )['num_words__sum']
        # Nothing matches filter
        if self.failing_checks_words is None:
            self.failing_checks_words = 0

        # Store hash will save object
        self.store_hash()

    def store_hash(self):
        """Stores current hash in database."""
        blob_hash = self.get_git_blob_hash()
        self.revision = blob_hash
        self.save()

    def get_last_author(self, email=False):
        """Returns last autor of change done in Weblate."""
        if self.last_change_obj is None:
            return None
        return get_author_name(
            self.last_change_obj.author,
            email
        )

    @property
    def last_change_obj(self):
        """Cached getter for last content change."""
        if not self._last_change_obj_valid:
            changes = self.change_set.content()

            if changes.exists():
                self._last_change_obj = changes.select_related('author')[0]
            else:
                self._last_change_obj = None

            self._last_change_obj_valid = True

        return self._last_change_obj

    @property
    def last_change(self):
        """Returns date of last change done in Weblate."""
        if self.last_change_obj is None:
            return None
        return self.last_change_obj.timestamp

    def commit_pending(self, request, author=None, skip_push=False):
        """Commits any pending changes."""
        # Get author of last changes
        last = self.get_last_author(True)

        # If it is same as current one, we don't have to commit
        if author == last or last is None:
            return False

        # Commit changes
        self.git_commit(
            request, last, self.last_change, True, True, skip_push
        )
        return True

    def get_commit_message(self):
        """Formats commit message based on project configuration."""
        template = self.subproject.commit_message
        if self.commit_message == '__add__':
            template = self.subproject.add_message
            self.commit_message = ''
            self.save()
        elif self.commit_message == '__delete__':
            template = self.subproject.delete_message
            self.commit_message = ''
            self.save()

        msg = template % {
            'language': self.language_code,
            'language_name': self.language.name,
            'subproject': self.subproject.name,
            'resource': self.subproject.name,
            'component': self.subproject.name,
            'project': self.subproject.project.name,
            'total': self.total,
            'fuzzy': self.fuzzy,
            'fuzzy_percent': self.get_fuzzy_percent(),
            'translated': self.translated,
            'translated_percent': self.get_translated_percent(),
        }
        if self.commit_message:
            msg = '%s\n\n%s' % (msg, self.commit_message)
            self.commit_message = ''
            self.save()

        return msg

    def __git_commit(self, author, timestamp, sync=False):
        """Commits translation to git."""

        # Format commit message
        msg = self.get_commit_message()

        # Pre commit hook
        vcs_pre_commit.send(sender=self.__class__, translation=self)

        # Create list of files to commit
        files = [self.filename]
        if self.subproject.extra_commit_file:
            extra_files = self.subproject.extra_commit_file % {
                'language': self.language_code,
            }
            for extra_file in extra_files.split('\n'):
                full_path_extra = os.path.join(
                    self.subproject.get_path(),
                    extra_file
                )
                if os.path.exists(full_path_extra):
                    files.append(extra_file)

        # Do actual commit
        self.subproject.repository.commit(
            msg, author, timestamp, files
        )

        # Post commit hook
        vcs_post_commit.send(sender=self.__class__, translation=self)

        # Optionally store updated hash
        if sync:
            self.store_hash()

    def repo_needs_commit(self):
        """Checks whether there are some not committed changes."""
        return self.subproject.repository.needs_commit(self.filename)

    def repo_needs_merge(self):
        return self.subproject.repo_needs_merge()

    def repo_needs_push(self):
        return self.subproject.repo_needs_push()

    def git_commit(self, request, author, timestamp, force_commit=False,
                   sync=False, skip_push=False, force_new=False):
        """Wrapper for commiting translation to git.

        force_commit forces commit with lazy commits enabled

        sync updates git hash stored within the translation (otherwise
        translation rescan will be needed)
        """
        # Is there something for commit?
        if not force_new and not self.repo_needs_commit():
            return False

        # Can we delay commit?
        if not force_commit and appsettings.LAZY_COMMITS:
            self.log_info(
                'delaying commiting %s as %s',
                self.filename,
                author
            )
            return False

        # Do actual commit with git lock
        self.log_info(
            'commiting %s as %s',
            self.filename,
            author
        )
        Change.objects.create(
            action=Change.ACTION_COMMIT,
            translation=self,
        )
        with self.subproject.repository_lock():
            self.__git_commit(author, timestamp, sync)

        # Push if we should
        if not skip_push:
            self.subproject.push_if_needed(request)

        self._last_change_obj_valid = False

        return True

    def update_unit(self, unit, request, user=None):
        """Updates backend file and unit."""
        if user is None:
            user = request.user
        # Save with lock acquired
        with self.subproject.repository_lock():

            src = unit.get_source_plurals()[0]
            add = False

            pounit, add = self.store.find_unit(unit.context, src)

            # Bail out if we have not found anything
            if pounit is None or pounit.is_obsolete():
                return False, None

            # Check for changes
            if ((not add or unit.target == '') and
                    unit.target == pounit.get_target() and
                    unit.fuzzy == pounit.is_fuzzy()):
                return False, pounit

            # Store translations
            if unit.is_plural():
                pounit.set_target(unit.get_target_plurals())
            else:
                pounit.set_target(unit.target)

            # Update fuzzy flag
            pounit.mark_fuzzy(unit.fuzzy)

            # Optionally add unit to translation file
            if add:
                self.store.add_unit(pounit)

            # We need to update backend now
            author = get_author_name(user)

            # Update po file header
            now = timezone.now()
            if not timezone.is_aware(now):
                now = timezone.make_aware(now, timezone.utc)

            # Prepare headers to update
            headers = {
                'add': True,
                'last_translator': author,
                'plural_forms': self.language.get_plural_form(),
                'language': self.language_code,
                'PO_Revision_Date': now.strftime('%Y-%m-%d %H:%M%z'),
            }

            # Optionally store language team with link to website
            if self.subproject.project.set_translation_team:
                headers['language_team'] = '%s <%s>' % (
                    self.language.name,
                    get_site_url(self.get_absolute_url()),
                )

            # Optionally store email for reporting bugs in source
            report_source_bugs = self.subproject.report_source_bugs
            if report_source_bugs != '':
                headers['report_msgid_bugs_to'] = report_source_bugs

            # Update genric headers
            self.store.update_header(
                **headers
            )

            # commit possible previous changes (by other author)
            self.commit_pending(request, author)
            # save translation changes
            self.store.save()
            # commit VCS repo if needed
            self.git_commit(request, author, timezone.now(), sync=True)

        return True, pounit

    def get_source_checks(self):
        """Returns list of failing source checks on current subproject."""
        result = TranslationChecklist()
        result.add(
            'all',
            _('All strings'),
            self.total,
            'success',
        )

        # All checks
        result.add_if(
            'sourcechecks',
            _('Strings with any failing checks'),
            self.unit_set.count_type('sourcechecks', self),
            'danger',
        )

        # Process specific checks
        for check in CHECKS:
            check_obj = CHECKS[check]
            if not check_obj.source:
                continue
            result.add_if(
                check,
                check_obj.description,
                self.unit_set.count_type(check, self),
                check_obj.severity,
            )

        # Grab comments
        result.add_if(
            'sourcecomments',
            _('Strings with comments'),
            self.unit_set.count_type('sourcecomments', self),
            'info',
        )

        return result

    def get_translation_checks(self):
        """Returns list of failing checks on current translation."""
        result = TranslationChecklist()

        # All strings
        result.add(
            'all',
            _('All strings'),
            self.total,
            'success',
            self.total_words
        )

        # Count of translated strings
        result.add_if(
            'translated',
            _('Translated strings'),
            self.translated,
            'success',
            self.translated_words,
        )

        # Untranslated strings
        result.add_if(
            'todo',
            _('Strings needing action'),
            self.total - self.translated,
            'danger',
            self.total_words - self.translated_words,
        )

        # Not translated strings
        result.add_if(
            'nottranslated',
            _('Not translated strings'),
            self.total - self.translated - self.fuzzy,
            'danger',
            self.total_words - self.translated_words - self.fuzzy_words,
        )

        # Fuzzy strings
        result.add_if(
            'fuzzy',
            _('Strings marked for review'),
            self.fuzzy,
            'danger',
            self.fuzzy_words,
        )

        # Translations with suggestions
        result.add_if(
            'suggestions',
            _('Strings with suggestions'),
            self.have_suggestion,
            'info',
        )

        # All checks
        result.add_if(
            'allchecks',
            _('Strings with any failing checks'),
            self.failing_checks,
            'danger',
        )

        # Process specific checks
        for check in CHECKS:
            check_obj = CHECKS[check]
            if not check_obj.target:
                continue
            result.add_if(
                check,
                check_obj.description,
                self.unit_set.count_type(check, self),
                check_obj.severity,
            )

        # Grab comments
        result.add_if(
            'comments',
            _('Strings with comments'),
            self.have_comment,
            'info',
        )

        return result

    def merge_translations(self, request, store2, overwrite, add_fuzzy, fuzzy):
        """Merges translation unit wise

        Needed for template based translations to add new strings.
        """
        ret = False

        for set_fuzzy, unit2 in store2.iterate_merge(fuzzy):
            try:
                unit = self.unit_set.get(
                    source=unit2.get_source(),
                    context=unit2.get_context(),
                )
            except Unit.DoesNotExist:
                continue

            if unit.translated and not overwrite:
                continue

            ret = True

            unit.translate(
                request,
                split_plural(unit2.get_target()),
                add_fuzzy or set_fuzzy
            )

        return ret

    def merge_store(self, request, author, store2, overwrite, merge_header,
                    add_fuzzy, fuzzy, merge_comments):
        """Merges translate-toolkit store into current translation."""
        # Merge with lock acquired
        with self.subproject.repository_lock():

            store1 = self.store.store
            store1.require_index()

            if merge_header:
                self.store.merge_header(store2)

            for set_fuzzy, unit2 in store2.iterate_merge(fuzzy):

                # Find unit by ID
                unit1 = store1.findid(unit2.unit.getid())

                # Fallback to finding by source
                if unit1 is None:
                    unit1 = store1.findunit(unit2.unit.source)

                # Unit not found, nothing to do
                if unit1 is None:
                    continue

                # Should we overwrite
                if not overwrite and unit1.istranslated():
                    continue

                # Actually update translation
                unit1.merge(
                    unit2.unit,
                    overwrite=True,
                    comments=merge_comments
                )

                # Handle
                if add_fuzzy or set_fuzzy:
                    unit1.markfuzzy()

            # Write to backend and commit
            self.commit_pending(request, author)
            store1.save()
            ret = self.git_commit(request, author, timezone.now(), True)
            self.check_sync(request=request, change=Change.ACTION_UPLOAD)

        return ret

    def merge_suggestions(self, request, store, fuzzy):
        """Merges content of translate-toolkit store as a suggestions."""
        ret = False
        for dummy, unit in store.iterate_merge(fuzzy):
            # Calculate unit checksum
            checksum = unit.get_checksum()

            # Grab database unit
            try:
                dbunit = self.unit_set.filter(checksum=checksum)[0]
            except IndexError:
                continue

            # Indicate something new
            ret = True

            # Add suggestion
            if dbunit.target != unit.get_target():
                Suggestion.objects.add(dbunit, unit.get_target(), request)

        # Update suggestion count
        if ret:
            self.update_stats()

        return ret

    def merge_upload(self, request, fileobj, overwrite, author=None,
                     merge_header=True, method='', fuzzy='',
                     merge_comments=False):
        """Top level handler for file uploads."""
        filecopy = fileobj.read()
        fileobj.close()

        # Strip possible UTF-8 BOM
        if filecopy[:3] == codecs.BOM_UTF8:
            filecopy = filecopy[3:]

        # Load backend file
        try:
            # First try using own loader
            store = self.store.parse(
                StringIOMode(fileobj.name, filecopy),
                self.subproject.template_store
            )
        except Exception:
            # Fallback to automatic detection
            store = AutoFormat.parse(
                StringIOMode(fileobj.name, filecopy),
            )

        # Optionally set authorship
        if author is None:
            author = get_author_name(request.user)

        # Check valid plural forms
        if hasattr(store.store, 'parseheader'):
            header = store.store.parseheader()
            if 'Plural-Forms' in header and \
                    self.language.get_plural_form() != header['Plural-Forms']:
                raise Exception('Plural forms do not match the language.')

        # List translations we should process
        # Filter out those who don't want automatic update, but keep ourselves
        translations = Translation.objects.filter(
            language=self.language,
            subproject__project=self.subproject.project
        ).filter(
            Q(pk=self.pk) | Q(subproject__allow_translation_propagation=True)
        )

        ret = False

        if method in ('', 'fuzzy'):
            # Do actual merge
            if self.subproject.has_template():
                # Merge on units level
                ret = self.merge_translations(
                    request,
                    store,
                    overwrite,
                    (method == 'fuzzy'),
                    fuzzy
                )
            else:
                # Merge on file level
                for translation in translations:
                    ret |= translation.merge_store(
                        request,
                        author,
                        store,
                        overwrite,
                        merge_header,
                        (method == 'fuzzy'),
                        fuzzy,
                        merge_comments=merge_comments,
                    )
        else:
            # Add as sugestions
            ret = self.merge_suggestions(request, store, fuzzy)

        return ret, store.count_units()

    def invalidate_cache(self, cache_type=None):
        """Invalidates any cached stats."""
        # Get parts of key cache
        slug = self.subproject.get_full_slug()
        code = self.language.code

        # Are we asked for specific cache key?
        if cache_type is None:
            keys = list(CHECKS)
        else:
            keys = [cache_type]

        # Actually delete the cache
        for rqtype in keys:
            cache_key = 'counts-%s-%s-%s' % (slug, code, rqtype)
            cache.delete(cache_key)

    def get_kwargs(self):
        return {
            'lang': self.language.code,
            'subproject': self.subproject.slug,
            'project': self.subproject.project.slug
        }

    def get_export_url(self):
        """Returns URL of exported git repository."""
        return self.subproject.get_export_url()

    def get_stats(self):
        """Returns stats dictionary"""
        return {
            'code': self.language.code,
            'name': self.language.name,
            'total': self.total,
            'total_words': self.total_words,
            'last_change': self.last_change,
            'last_author': self.get_last_author(),
            'translated': self.translated,
            'translated_words': self.translated_words,
            'translated_percent': self.get_translated_percent(),
            'fuzzy': self.fuzzy,
            'fuzzy_percent': self.get_fuzzy_percent(),
            'failing': self.failing_checks,
            'failing_percent': self.get_failing_checks_percent(),
            'url': self.get_share_url(),
            'url_translate': get_site_url(self.get_absolute_url()),
        }
