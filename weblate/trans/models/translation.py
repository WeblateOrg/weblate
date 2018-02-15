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

import os
import codecs

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import ugettext as _
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.utils.functional import cached_property
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse

from weblate.lang.models import Language, Plural
from weblate.permissions.helpers import can_translate
from weblate.trans.formats import ParseError, try_load
from weblate.trans.checks import CHECKS
from weblate.trans.models.unit import (
    Unit, STATE_TRANSLATED, STATE_FUZZY, STATE_APPROVED,
)
from weblate.utils.stats import TranslationStats
from weblate.trans.models.suggestion import Suggestion
from weblate.trans.signals import vcs_pre_commit, vcs_post_commit
from weblate.utils.site import get_site_url
from weblate.trans.util import split_plural
from weblate.trans.mixins import URLMixin, LoggerMixin
from weblate.accounts.notifications import notify_new_string
from weblate.accounts.models import get_author_name
from weblate.trans.models.change import Change
from weblate.trans.checklists import TranslationChecklist


class TranslationManager(models.Manager):
    def check_sync(self, subproject, lang, code, path, force=False,
                   request=None):
        """Parse translation meta info and updates translation object"""
        translation, dummy = self.get_or_create(
            language=lang,
            subproject=subproject,
            defaults={
                'filename': path,
                'language_code': code,
                'plural': lang.plural
            },
        )
        if translation.filename != path or translation.language_code != code:
            force = True
            translation.filename = path
            translation.language_code = code
        translation.check_sync(force, request=request)

        return translation


class TranslationQuerySet(models.QuerySet):
    def prefetch(self):
        return self.select_related(
            'subproject', 'subproject__project', 'language'
        )


@python_2_unicode_compatible
class Translation(models.Model, URLMixin, LoggerMixin):
    subproject = models.ForeignKey(
        'SubProject', on_delete=models.deletion.CASCADE
    )
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)
    plural = models.ForeignKey(Plural, on_delete=models.deletion.CASCADE)
    revision = models.CharField(max_length=100, default='', blank=True)
    filename = models.CharField(max_length=200)

    language_code = models.CharField(max_length=20, default='', blank=True)

    commit_message = models.TextField(default='', blank=True)

    objects = TranslationManager.from_queryset(TranslationQuerySet)()

    is_lockable = False
    _reverse_url_name = 'translation'

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
            ('mass_add_translation', 'Can mass add translation'),
            ('automatic_translation', "Can do automatic translation"),
            ('use_mt', "Can use machine translation"),
        )
        app_label = 'trans'
        unique_together = ('subproject', 'language')

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super(Translation, self).__init__(*args, **kwargs)
        self.stats = TranslationStats(self)
        self.addon_commit_files = []

    @cached_property
    def log_prefix(self):
        return '/'.join((
            self.subproject.project.slug,
            self.subproject.slug,
            self.language.code,
        ))

    @cached_property
    def is_template(self):
        """Check whether this is template translation

        This means that translations should be propagated as sources to others.
        """
        return self.filename == self.subproject.template

    def clean(self):
        """Validate that filename exists and can be opened using
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

    def get_reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        return {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        }

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return get_site_url(
            '{0}?lang={1}&component={2}'.format(
                reverse(
                    'widgets', kwargs={
                        'project': self.subproject.project.slug,
                    }
                ),
                self.language.code,
                self.subproject.slug,
            )
        )

    def get_share_url(self):
        """Return absolute URL usable for sharing."""
        return get_site_url(
            reverse(
                'engage',
                kwargs={
                    'project': self.subproject.project.slug,
                    'lang': self.language.code
                }
            )
        )

    def get_translate_url(self):
        return reverse('translate', kwargs={
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    def __str__(self):
        return '{0} - {1}'.format(
            force_text(self.subproject),
            force_text(self.language)
        )

    def get_filename(self):
        """Return absolute filename."""
        return os.path.join(self.subproject.full_path, self.filename)

    def load_store(self):
        """Load translate-toolkit storage from disk."""
        return self.subproject.file_format_cls.parse(
            self.get_filename(),
            self.subproject.template_store,
            language_code=self.language_code
        )

    @cached_property
    def store(self):
        """Return translate-toolkit storage object for a translation."""
        try:
            return self.load_store()
        except ParseError:
            raise
        except Exception as exc:
            self.subproject.handle_parse_error(exc, self)

    def check_sync(self, force=False, request=None, change=None):
        """Check whether database is in sync with git and possibly updates"""

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

        # Store plural
        plural = self.store.get_plural(self.language)
        if plural != self.plural:
            self.plural = plural
            self.save(update_fields=['plural'])

        # Was there change?
        was_new = False
        # Position of current unit
        pos = 1

        # Select all current units for update
        self.unit_set.select_for_update()

        for unit in self.store.all_units():
            if not unit.is_translatable():
                continue

            newunit, is_new = Unit.objects.update_from_unit(
                self, unit, pos
            )

            # Check if unit is worth notification:
            # - new and untranslated
            # - newly not translated
            # - newly fuzzy
            was_new = (
                was_new or
                (is_new and newunit.state <= STATE_TRANSLATED) or
                (
                    newunit.state < STATE_TRANSLATED and
                    newunit.state != newunit.old_unit.state
                )
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

        # Delete stale units
        self.unit_set.exclude(
            id__in=created_units
        ).delete()

        # Update revision and stats
        self.invalidate_cache()
        self.store_hash()

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
        """Return current VCS blob hash for file."""
        ret = self.subproject.repository.get_object_hash(self.get_filename())

        if not self.subproject.has_template():
            return ret

        return ','.join([
            ret,
            self.subproject.repository.get_object_hash(
                self.subproject.template
            )
        ])

    def store_hash(self):
        """Store current hash in database."""
        self.revision = self.get_git_blob_hash()
        self.save(update_fields=['revision'])

    def get_last_author(self, email=False):
        """Return last autor of change done in Weblate."""
        if self.last_change_obj is None:
            return None
        return get_author_name(
            self.last_change_obj.author,
            email
        )

    def invalidate_last_change(self):
        """Invalidate last change cache."""
        if 'last_change_obj' in self.__dict__:
            del self.__dict__['last_change_obj']

    @property
    def last_change_obj(self):
        """Cached getter for last content change."""
        changes = self.change_set.content()
        try:
            return changes.select_related('author')[0]
        except IndexError:
            return None

    @property
    def last_change(self):
        """Return date of last change done in Weblate."""
        if self.last_change_obj is None:
            return None
        return self.last_change_obj.timestamp

    def commit_pending(self, request, author=None, skip_push=False):
        """Commit any pending changes."""
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
        """Format commit message based on project configuration."""
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
            'url': get_site_url(self.get_absolute_url()),
            'total': self.stats.all,
            'fuzzy': self.stats.fuzzy,
            'fuzzy_percent': self.stats.fuzzy_percent,
            'translated': self.stats.translated,
            'translated_percent': self.stats.translated_percent,
        }
        if self.commit_message:
            msg = '{0}\n\n{1}'.format(msg, self.commit_message)
            self.commit_message = ''
            self.save()

        return msg

    def __git_commit(self, author, timestamp, sync=False):
        """Commit translation to git."""

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
                    self.subproject.full_path,
                    extra_file
                )
                if os.path.exists(full_path_extra):
                    files.append(extra_file)

        # Do actual commit
        self.subproject.repository.commit(
            msg, author, timestamp, files + self.addon_commit_files
        )
        self.addon_commit_files = []

        # Post commit hook
        vcs_post_commit.send(sender=self.__class__, translation=self)

        # Optionally store updated hash
        if sync:
            self.store_hash()

    def repo_needs_commit(self):
        """Check whether there are some not committed changes."""
        return (
            self.unit_set.filter(pending=True).exists() or
            self.subproject.repository.needs_commit(self.filename)
        )

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
        with self.subproject.repository.lock:
            # Is there something for commit?
            if not force_new and not self.repo_needs_commit():
                return False

            # Can we delay commit?
            if not force_commit and settings.LAZY_COMMITS:
                self.log_info(
                    'delaying commiting %s as %s',
                    self.filename,
                    author
                )
                return False

            if not force_new:
                # Commit pending units
                self.update_units(author)
                # Bail out if no change was done
                if not self.repo_needs_commit():
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
                user=request.user if request else None,
            )
            self.__git_commit(author, timestamp, sync)

            # Push if we should
            if not skip_push:
                self.subproject.push_if_needed(request)

        return True

    @transaction.atomic
    def update_units(self, author):
        """Update backend file and unit."""
        updated = False
        for unit in self.unit_set.filter(pending=True).select_for_update():

            src = unit.get_source_plurals()[0]
            add = False

            pounit, add = self.store.find_unit(unit.context, src)

            unit.pending = False

            # Bail out if we have not found anything
            if pounit is None or pounit.is_obsolete():
                self.log_error('message %s disappeared!', unit)
                unit.save(backend=True, update_fields=['pending'])
                continue

            # Check for changes
            if ((not add or unit.target == '') and
                    unit.target == pounit.get_target() and
                    unit.approved == pounit.is_approved(unit.approved) and
                    unit.fuzzy == pounit.is_fuzzy()):
                unit.save(backend=True, update_fields=['pending'])
                continue

            updated = True

            # Optionally add unit to translation file.
            # This has be done prior setting tatget as some formats
            # generate content based on target language.
            if add:
                self.store.add_unit(pounit.unit)

            # Store translations
            if unit.is_plural():
                pounit.set_target(unit.get_target_plurals())
            else:
                pounit.set_target(unit.target)

            # Update fuzzy/approved flag
            pounit.mark_fuzzy(unit.state == STATE_FUZZY)
            pounit.mark_approved(unit.state == STATE_APPROVED)

            # Update comments as they might have been changed (eg, fuzzy flag
            # removed)
            state = unit.get_unit_state(pounit, False)
            flags = pounit.get_flags()
            if state != unit.state or flags != unit.flags:
                unit.state = state
                unit.flags = flags
            unit.save(
                backend=True,
                update_fields=['state', 'flags', 'pending']
            )

        # Did we do any updates?
        if not updated:
            return

        # Update po file header
        now = timezone.now()
        if not timezone.is_aware(now):
            now = timezone.make_aware(now, timezone.utc)

        # Prepare headers to update
        headers = {
            'add': True,
            'last_translator': author,
            'plural_forms': self.plural.plural_form,
            'language': self.language_code,
            'PO_Revision_Date': now.strftime('%Y-%m-%d %H:%M%z'),
        }

        # Optionally store language team with link to website
        if self.subproject.project.set_translation_team:
            headers['language_team'] = '{0} <{1}>'.format(
                self.language.name,
                get_site_url(self.get_absolute_url())
            )

        # Optionally store email for reporting bugs in source
        report_source_bugs = self.subproject.report_source_bugs
        if report_source_bugs != '':
            headers['report_msgid_bugs_to'] = report_source_bugs

        # Update genric headers
        self.store.update_header(
            **headers
        )

        # save translation changes
        self.store.save()

        # Update stats (the translated flag might have changed)
        self.invalidate_cache()

    def get_source_checks(self):
        """Return list of failing source checks on current subproject."""
        result = TranslationChecklist()
        result.add(
            self.stats,
            'all',
            _('All strings'),
            'success',
        )

        # All checks
        result.add_if(
            self.stats,
            'sourcechecks',
            _('Strings with any failing checks'),
            'danger',
        )

        # Process specific checks
        for check in CHECKS:
            check_obj = CHECKS[check]
            if not check_obj.source:
                continue
            result.add_if(
                self.stats,
                check_obj.url_id,
                check_obj.description,
                check_obj.severity,
            )

        # Grab comments
        result.add_if(
            self.stats,
            'sourcecomments',
            _('Strings with comments'),
            'info',
        )

        return result

    def get_translation_checks(self):
        """Return list of failing checks on current translation."""
        result = TranslationChecklist()

        # All strings
        result.add(
            self.stats,
            'all',
            _('All strings'),
            'success',
        )

        result.add_if(
            self.stats,
            'approved',
            _('Approved strings'),
            'success',
        )

        # Count of translated strings
        result.add_if(
            self.stats,
            'translated',
            _('Translated strings'),
            'success',
        )

        # To approve
        if self.subproject.project.enable_review:
            result.add_if(
                self.stats,
                'unapproved',
                _('Strings waiting for review'),
                'warning',
            )

        # Approved with suggestions
        result.add_if(
            self.stats,
            'approved_suggestions',
            _('Approved strings with suggestions'),
            'danger',
        )

        # Untranslated strings
        result.add_if(
            self.stats,
            'todo',
            _('Strings needing action'),
            'danger',
        )

        # Not translated strings
        result.add_if(
            self.stats,
            'nottranslated',
            _('Not translated strings'),
            'danger',
        )

        # Fuzzy strings
        result.add_if(
            self.stats,
            'fuzzy',
            _('Strings marked as needing edit'),
            'danger',
        )

        # Translations with suggestions
        result.add_if(
            self.stats,
            'suggestions',
            _('Strings with suggestions'),
            'info',
        )

        # All checks
        result.add_if(
            self.stats,
            'allchecks',
            _('Strings with any failing checks'),
            'danger',
        )

        # Process specific checks
        for check in CHECKS:
            check_obj = CHECKS[check]
            if not check_obj.target:
                continue
            result.add_if(
                self.stats,
                check_obj.url_id,
                check_obj.description,
                check_obj.severity,
            )

        # Grab comments
        result.add_if(
            self.stats,
            'comments',
            _('Strings with comments'),
            'info',
        )

        return result

    def merge_translations(self, request, store2, overwrite, add_fuzzy,
                           fuzzy, merge_header):
        """Merge translation unit wise

        Needed for template based translations to add new strings.
        """
        not_found = 0
        skipped = 0
        accepted = 0

        author = get_author_name(request.user)

        # Commit possible prior changes
        self.commit_pending(request, author)

        for set_fuzzy, unit2 in store2.iterate_merge(fuzzy):
            try:
                unit = self.unit_set.get_unit(unit2)
            except Unit.DoesNotExist:
                not_found += 1
                continue

            if ((unit.translated and not overwrite)
                    or (not can_translate(request.user, unit))):
                skipped += 1
                continue

            accepted += 1

            # We intentionally avoid propagating:
            # - in most cases it's not desired
            # - it slows down import considerably
            # - it brings locking issues as import is
            #   executed with lock held and linked repos
            #   can't obtain the lock
            state = STATE_TRANSLATED
            if add_fuzzy or set_fuzzy:
                state = STATE_FUZZY
            unit.translate(
                request,
                split_plural(unit2.get_target()),
                state,
                change_action=Change.ACTION_UPLOAD,
                propagate=False
            )

        if accepted > 0:
            self.invalidate_cache()

            if merge_header:
                self.store.merge_header(store2)
                self.store.save()
            self.store_hash()

            self.git_commit(
                request, author, timezone.now(),
                force_commit=True, sync=True
            )

        return (not_found, skipped, accepted, store2.count_units())

    def merge_suggestions(self, request, store, fuzzy):
        """Merge content of translate-toolkit store as a suggestions."""
        not_found = 0
        skipped = 0
        accepted = 0

        for dummy, unit in store.iterate_merge(fuzzy):
            # Grab database unit
            try:
                dbunit = self.unit_set.get_unit(unit)
            except Unit.DoesNotExist:
                not_found += 1
                continue

            # Add suggestion
            if dbunit.target != unit.get_target():
                Suggestion.objects.add(dbunit, unit.get_target(), request)
                accepted += 1
            else:
                skipped += 1

        # Update suggestion count
        if accepted > 0:
            self.invalidate_cache()

        return (not_found, skipped, accepted, store.count_units())

    def merge_upload(self, request, fileobj, overwrite, author=None,
                     merge_header=True, method='translate', fuzzy=''):
        """Top level handler for file uploads."""
        filecopy = fileobj.read()
        fileobj.close()

        # Strip possible UTF-8 BOM
        if filecopy[:3] == codecs.BOM_UTF8:
            filecopy = filecopy[3:]

        # Load backend file
        store = try_load(
            fileobj.name,
            filecopy,
            self.subproject.file_format_cls,
            self.subproject.template_store
        )

        # Optionally set authorship
        if author is None:
            author = get_author_name(request.user)

        # Check valid plural forms
        if hasattr(store.store, 'parseheader'):
            header = store.store.parseheader()
            try:
                number, equation = Plural.parse_formula(header['Plural-Forms'])
                if not self.plural.same_plural(number, equation):
                    raise Exception('Plural forms do not match the language.')
            except (ValueError, KeyError):
                # Formula wrong or missing
                pass

        if method in ('translate', 'fuzzy'):
            # Merge on units level
            with self.subproject.repository.lock:
                return self.merge_translations(
                    request,
                    store,
                    overwrite,
                    (method == 'fuzzy'),
                    fuzzy,
                    merge_header,
                )

        # Add as sugestions
        return self.merge_suggestions(request, store, fuzzy)

    def invalidate_cache(self, recurse=True):
        """Invalidate any cached stats."""

        # Invalidate summary stats
        self.stats.invalidate()
        if recurse and self.subproject.allow_translation_propagation:
            related = Translation.objects.filter(
                subproject__project=self.subproject.project,
                subproject__allow_translation_propagation=True,
                language=self.language,
            ).exclude(
                pk=self.pk
            )
            for component in related:
                component.invalidate_cache(False)

    def get_kwargs(self):
        return {
            'lang': self.language.code,
            'subproject': self.subproject.slug,
            'project': self.subproject.project.slug
        }

    def get_export_url(self):
        """Return URL of exported git repository."""
        return self.subproject.get_export_url()

    def get_stats(self):
        """Return stats dictionary"""
        return {
            'code': self.language.code,
            'name': self.language.name,
            'total': self.stats.all,
            'total_words': self.stats.all_words,
            'last_change': self.last_change,
            'last_author': self.get_last_author(),
            'translated': self.stats.translated,
            'translated_words': self.stats.translated_words,
            'translated_percent': self.stats.translated_percent,
            'fuzzy': self.stats.fuzzy,
            'fuzzy_percent': self.stats.fuzzy_percent,
            'failing': self.stats.allchecks,
            'failing_percent': self.stats.allchecks_percent,
            'url': self.get_share_url(),
            'url_translate': get_site_url(self.get_absolute_url()),
        }

    def remove(self, user):
        """Remove translation from the VCS"""
        author = get_author_name(user)
        # Log
        self.log_info(
            'removing %s as %s',
            self.filename,
            author
        )

        # Remove file from VCS
        self.commit_message = '__delete__'
        with self.subproject.repository.lock:
            self.subproject.repository.remove(
                [self.filename],
                self.get_commit_message(),
                author,
            )

        # Delete from the database
        self.delete()

        # Record change
        Change.objects.create(
            subproject=self.subproject,
            action=Change.ACTION_REMOVE,
            target=self.filename,
            user=user,
            author=user
        )

    def new_unit(self, request, key, value):
        self.commit_pending(request)
        Change.objects.create(
            translation=self,
            action=Change.ACTION_NEW_UNIT,
            target=value,
            user=request.user,
            author=request.user
        )
        self.store.new_unit(key, value)
        self.subproject.create_translations(request=request)
