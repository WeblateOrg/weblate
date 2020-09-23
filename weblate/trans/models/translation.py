#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import codecs
import os
import tempfile
from datetime import datetime
from typing import BinaryIO, Dict, List, Optional, Union

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext as _

from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS
from weblate.formats.auto import try_load
from weblate.formats.base import UnitNotFound
from weblate.formats.helpers import BytesIOMode
from weblate.lang.models import Language, Plural
from weblate.trans.checklists import TranslationChecklist
from weblate.trans.defines import FILENAME_LENGTH
from weblate.trans.exceptions import FileParseError, PluralFormsMismatch
from weblate.trans.mixins import CacheKeyMixin, LoggerMixin, URLMixin
from weblate.trans.models.change import Change
from weblate.trans.models.suggestion import Suggestion
from weblate.trans.models.unit import (
    STATE_APPROVED,
    STATE_FUZZY,
    STATE_TRANSLATED,
    Unit,
)
from weblate.trans.signals import store_post_load, vcs_pre_commit
from weblate.trans.util import split_plural
from weblate.trans.validators import validate_check_flags
from weblate.utils.db import FastDeleteModelMixin, FastDeleteQuerySetMixin
from weblate.utils.errors import report_error
from weblate.utils.render import render_template
from weblate.utils.site import get_site_url
from weblate.utils.stats import GhostStats, TranslationStats


class TranslationManager(models.Manager):
    def check_sync(self, component, lang, code, path, force=False, request=None):
        """Parse translation meta info and updates translation object."""
        translation = self.get_or_create(
            language=lang,
            component=component,
            defaults={"filename": path, "language_code": code, "plural": lang.plural},
        )[0]
        # Share component instance to improve performance
        # and to properly process updated data.
        translation.component = component
        if translation.filename != path or translation.language_code != code:
            force = True
            translation.filename = path
            translation.language_code = code
            translation.save(update_fields=["filename", "language_code"])
        flags = ""
        if (not component.edit_template and translation.is_template) or (
            not translation.is_template and translation.is_source
        ):
            flags = "read-only"
        if translation.check_flags != flags:
            force = True
            translation.check_flags = flags
            translation.save(update_fields=["check_flags"])
        translation.check_sync(force, request=request)

        return translation


class TranslationQuerySet(FastDeleteQuerySetMixin, models.QuerySet):
    def prefetch(self):
        from weblate.trans.models import Alert

        return self.prefetch_related(
            "component",
            "component__project",
            "language",
            "component__linked_component",
            "component__linked_component__project",
            models.Prefetch(
                "component__alert_set",
                queryset=Alert.objects.filter(dismissed=False),
                to_attr="all_alerts",
            ),
        )

    def filter_access(self, user):
        if user.is_superuser:
            return self
        return self.filter(
            Q(component__project_id__in=user.allowed_project_ids)
            & (
                Q(component__restricted=False)
                | Q(component_id__in=user.component_permissions)
            )
        )


class Translation(
    FastDeleteModelMixin, models.Model, URLMixin, LoggerMixin, CacheKeyMixin
):
    component = models.ForeignKey("Component", on_delete=models.deletion.CASCADE)
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)
    plural = models.ForeignKey(Plural, on_delete=models.deletion.CASCADE)
    revision = models.CharField(max_length=200, default="", blank=True)
    filename = models.CharField(max_length=FILENAME_LENGTH)

    language_code = models.CharField(max_length=20, default="", blank=True)

    check_flags = models.TextField(
        verbose_name="Translation flags",
        default="",
        validators=[validate_check_flags],
        blank=True,
    )

    objects = TranslationManager.from_queryset(TranslationQuerySet)()

    is_lockable = False
    _reverse_url_name = "translation"

    class Meta:
        app_label = "trans"
        unique_together = ("component", "language")
        verbose_name = "translation"
        verbose_name_plural = "translations"

    def __str__(self):
        return "{0} — {1}".format(self.component, self.language)

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super().__init__(*args, **kwargs)
        self.stats = TranslationStats(self)
        self.addon_commit_files = []
        self.was_new = 0
        self.reason = ""

    def get_badges(self):
        if self.is_source:
            yield (_("source"), _("This translation is used for source strings."))

    @cached_property
    def full_slug(self):
        return "/".join(
            (self.component.project.slug, self.component.slug, self.language.code)
        )

    def log_hook(self, level, msg, *args):
        self.component.store_log(self.full_slug, msg, *args)

    @cached_property
    def is_template(self):
        """Check whether this is template translation.

        This means that translations should be propagated as sources to others.
        """
        return self.filename == self.component.template

    @cached_property
    def is_source(self):
        """Check whether this is source strings.

        This means that translations should be propagated as sources to others.
        """
        return self.language_id == self.component.source_language_id

    @cached_property
    def all_flags(self):
        """Return parsed list of flags."""
        return Flags(self.component.all_flags, self.check_flags)

    @cached_property
    def is_readonly(self):
        return "read-only" in self.all_flags

    def clean(self):
        """Validate that filename exists and can be opened using translate-toolkit."""
        if not os.path.exists(self.get_filename()):
            raise ValidationError(
                _(
                    "Filename %s not found in repository! To add new "
                    "translation, add language file into repository."
                )
                % self.filename
            )
        try:
            self.load_store()
        except Exception as error:
            raise ValidationError(
                _("Failed to parse file %(file)s: %(error)s")
                % {"file": self.filename, "error": str(error)}
            )

    def notify_new(self, request):
        if self.was_new:
            # Create change after flags has been updated and cache
            # invalidated, otherwise we might be sending notification
            # with outdated values
            Change.objects.create(
                translation=self,
                action=Change.ACTION_NEW_STRING,
                user=request.user if request else None,
                author=request.user if request else None,
                details={"count": self.was_new},
            )
            self.was_new = 0

    def get_reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        return {
            "project": self.component.project.slug,
            "component": self.component.slug,
            "lang": self.language.code,
        }

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return get_site_url(
            "{0}?lang={1}&component={2}".format(
                reverse("widgets", kwargs={"project": self.component.project.slug}),
                self.language.code,
                self.component.slug,
            )
        )

    def get_share_url(self):
        """Return absolute URL usable for sharing."""
        return get_site_url(
            reverse(
                "engage",
                kwargs={
                    "project": self.component.project.slug,
                    "lang": self.language.code,
                },
            )
        )

    def get_translate_url(self):
        return reverse("translate", kwargs=self.get_reverse_url_kwargs())

    def get_filename(self):
        """Return absolute filename."""
        if not self.filename:
            return None
        return os.path.join(self.component.full_path, self.filename)

    def load_store(self, fileobj=None, force_intermediate=False):
        """Load translate-toolkit storage from disk."""
        if fileobj is None:
            fileobj = self.get_filename()
        # Use intermediate store as template for source translation
        if force_intermediate or (self.is_template and self.component.intermediate):
            template = self.component.intermediate_store
        else:
            template = self.component.template_store
        store = self.component.file_format_cls.parse(
            fileobj,
            template,
            language_code=self.language_code,
            is_template=self.is_template,
        )
        store_post_load.send(sender=self.__class__, translation=self, store=store)
        return store

    @cached_property
    def store(self):
        """Return translate-toolkit storage object for a translation."""
        try:
            return self.load_store()
        except FileParseError:
            raise
        except Exception as exc:
            report_error(cause="Translation parse error")
            self.component.handle_parse_error(exc, self)

    def sync_unit(self, dbunits, updated, id_hash, unit, pos):
        try:
            newunit = dbunits[id_hash]
            is_new = False
        except KeyError:
            newunit = Unit(translation=self, id_hash=id_hash, state=-1)
            is_new = True

        newunit.update_from_unit(unit, pos, is_new)

        # Check if unit is worth notification:
        # - new and untranslated
        # - newly not translated
        # - newly fuzzy
        # - source string changed
        if newunit.state < STATE_TRANSLATED and (
            newunit.state != newunit.old_unit.state
            or is_new
            or newunit.source != newunit.old_unit.source
        ):
            self.was_new += 1

        # Store current unit ID
        updated[id_hash] = newunit

    def check_sync(self, force=False, request=None, change=None):  # noqa: C901
        """Check whether database is in sync with git and possibly updates."""
        if change is None:
            change = Change.ACTION_UPDATE
        if request is None:
            user = None
        else:
            user = request.user

        # Check if we're not already up to date
        if not self.revision:
            self.reason = "new file"
        elif self.revision != self.get_git_blob_hash():
            self.reason = "content changed"
        elif force:
            self.reason = "check forced"
        else:
            self.reason = ""
            return

        self.log_info("processing %s, %s", self.filename, self.reason)

        # List of updated units (used for cleanup and duplicates detection)
        updated = {}

        try:
            store = self.store
            translation_store = None

            # Store plural
            plural = store.get_plural(self.language)
            if plural != self.plural:
                self.plural = plural
                self.save(update_fields=["plural"])

            # Was there change?
            self.was_new = 0

            # Select all current units for update
            dbunits = {unit.id_hash: unit for unit in self.unit_set.select_for_update()}

            # Process based on intermediate store if available
            if self.component.intermediate:
                translation_store = store
                store = self.load_store(force_intermediate=True)

            for pos, unit in enumerate(store.content_units):
                # Use translation store if exists and if it contains the string
                if translation_store is not None:
                    try:
                        translated_unit, created = translation_store.find_unit(
                            unit.context
                        )
                        if translated_unit and not created:
                            unit = translated_unit
                        else:
                            # Patch unit to have matching source
                            unit.source = translated_unit.source
                    except UnitNotFound:
                        pass

                id_hash = unit.id_hash

                # Check for possible duplicate units
                if id_hash in updated:
                    newunit = updated[id_hash]
                    self.log_warning(
                        "duplicate string to translate: %s (%s)",
                        newunit,
                        repr(newunit.source),
                    )
                    Change.objects.create(
                        unit=newunit,
                        action=Change.ACTION_DUPLICATE_STRING,
                        user=user,
                        author=user,
                    )
                    self.component.trigger_alert(
                        "DuplicateString",
                        language_code=self.language.code,
                        source=newunit.source,
                        unit_pk=newunit.pk,
                    )
                    continue

                self.sync_unit(dbunits, updated, id_hash, unit, pos + 1)

        except FileParseError as error:
            self.log_warning("skipping update due to parse error: %s", error)
            return

        # Delete stale units
        stale = set(dbunits) - set(updated)
        if stale:
            self.unit_set.filter(id_hash__in=stale).delete()
            self.component.needs_cleanup = True

        # We should also do cleanup on source strings tracking objects

        # Update revision and stats
        self.store_hash()

        # Store change entry
        Change.objects.create(translation=self, action=change, user=user, author=user)

        # Invalidate keys cache
        transaction.on_commit(self.invalidate_keys)

        # Use up to date list as prefetch for source
        if self.is_source:
            self.component.preload_sources(updated)

    def do_update(self, request=None, method=None):
        return self.component.do_update(request, method=method)

    def do_push(self, request=None):
        return self.component.do_push(request)

    def do_reset(self, request=None):
        return self.component.do_reset(request)

    def do_cleanup(self, request=None):
        return self.component.do_cleanup(request)

    def can_push(self):
        return self.component.can_push()

    def get_git_blob_hash(self):
        """Return current VCS blob hash for file."""
        get_object_hash = self.component.repository.get_object_hash

        # Include language file
        hashes = [get_object_hash(self.get_filename())]

        if self.component.has_template():
            # Include template
            hashes.append(get_object_hash(self.component.template))

            if self.component.intermediate:
                # Include intermediate language as it might add new strings
                hashes.append(get_object_hash(self.component.intermediate))

        return ",".join(hashes)

    def store_hash(self):
        """Store current hash in database."""
        self.revision = self.get_git_blob_hash()
        self.save(update_fields=["revision"])

    def get_last_author(self, email=False):
        """Return last autor of change done in Weblate."""
        if not self.stats.last_author:
            return None
        from weblate.auth.models import User

        return User.objects.get(pk=self.stats.last_author).get_author_name(email)

    @transaction.atomic
    def commit_pending(self, reason, user, skip_push=False, force=False, signals=True):
        """Commit any pending changes."""
        if not force and not self.needs_commit():
            return False

        self.log_info("committing pending changes (%s)", reason)

        try:
            store = self.store
        except FileParseError as error:
            report_error(cause="Failed to parse file on commit")
            self.log_error("skipping commit due to error: %s", error)
            return False

        with self.component.repository.lock:
            units = (
                self.unit_set.filter(pending=True)
                .prefetch_recent_content_changes()
                .select_for_update()
            )

            for unit in units:
                # We reuse the queryset, so pending units might reappear here
                if not unit.pending:
                    continue

                # Get last change metadata
                author, timestamp = unit.get_last_content_change()

                author_name = author.get_author_name()

                # Flush pending units for this author
                self.update_units(units, store, author_name, author.id)

                # Commit changes
                self.git_commit(
                    user, author_name, timestamp, skip_push=skip_push, signals=signals
                )

            # Remove the pending flag
            units.update(pending=False)

        # Update stats (the translated flag might have changed)
        self.invalidate_cache()

        return True

    def get_commit_message(self, author: str, template: str, **kwargs):
        """Format commit message based on project configuration."""
        return render_template(template, translation=self, author=author, **kwargs)

    def needs_commit(self):
        """Check whether there are some not committed changes."""
        return self.unit_set.filter(pending=True).exists()

    def repo_needs_merge(self):
        return self.component.repo_needs_merge()

    def repo_needs_push(self):
        return self.component.repo_needs_push()

    @cached_property
    def filenames(self):
        if not self.filename:
            return []
        if self.component.file_format_cls.simple_filename:
            return [self.get_filename()]
        return self.store.get_filenames()

    def repo_needs_commit(self):
        return self.component.repository.needs_commit(self.filenames)

    def git_commit(
        self,
        user,
        author: str,
        timestamp: Optional[datetime] = None,
        skip_push=False,
        signals=True,
        template: Optional[str] = None,
    ):
        """Wrapper for committing translation to git."""
        repository = self.component.repository
        if template is None:
            template = self.component.commit_message
        with repository.lock:
            # Pre commit hook
            vcs_pre_commit.send(sender=self.__class__, translation=self, author=author)

            # Do actual commit with git lock
            if not self.component.commit_files(
                template=template,
                author=author,
                timestamp=timestamp,
                skip_push=skip_push,
                signals=signals,
                files=self.filenames + self.addon_commit_files,
                extra_context={"translation": self},
            ):
                self.log_info("committed %s as %s", self.filenames, author)
                Change.objects.create(
                    action=Change.ACTION_COMMIT, translation=self, user=user
                )

            # Store updated hash
            self.store_hash()
            self.addon_commit_files = []

        return True

    def update_units(self, units, store, author_name, author_id):
        """Update backend file and unit."""
        updated = False
        for unit in units:
            # We reuse the queryset, so pending units might reappear here
            if not unit.pending:
                continue
            # Skip changes by other authors
            change_author = unit.get_last_content_change()[0]
            if change_author.id != author_id:
                continue

            # Remove pending flag
            unit.pending = False

            try:
                pounit, add = store.find_unit(unit.context, unit.source)
            except UnitNotFound:
                # Bail out if we have not found anything
                report_error(cause="String disappeared")
                self.log_error("disappeared string: %s", unit)
                continue

            # Check for changes
            if (
                (not add or unit.target == "")
                and unit.target == pounit.target
                and unit.approved == pounit.is_approved(unit.approved)
                and unit.fuzzy == pounit.is_fuzzy()
            ):
                continue

            updated = True

            # Optionally add unit to translation file.
            # This has be done prior setting tatget as some formats
            # generate content based on target language.
            if add:
                store.add_unit(pounit.unit)

            # Store translations
            if unit.is_plural:
                pounit.set_target(unit.get_target_plurals())
            else:
                pounit.set_target(unit.target)

            # Update fuzzy/approved flag
            pounit.mark_fuzzy(unit.state == STATE_FUZZY)
            pounit.mark_approved(unit.state == STATE_APPROVED)

            # Update comments as they might have been changed by state changes
            state = unit.get_unit_state(pounit, "")
            flags = pounit.flags
            same_state = True
            if state != unit.state or flags != unit.flags:
                unit.state = state
                unit.flags = flags
                same_state = False
                unit.save(
                    update_fields=["state", "flags", "pending"],
                    same_content=True,
                    same_state=same_state,
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
            "add": True,
            "last_translator": author_name,
            "plural_forms": self.plural.plural_form,
            "language": self.language_code,
            "PO_Revision_Date": now.strftime("%Y-%m-%d %H:%M%z"),
        }

        # Optionally store language team with link to website
        if self.component.project.set_language_team:
            headers["language_team"] = "{0} <{1}>".format(
                self.language.name, get_site_url(self.get_absolute_url())
            )

        # Optionally store email for reporting bugs in source
        report_source_bugs = self.component.report_source_bugs
        if report_source_bugs:
            headers["report_msgid_bugs_to"] = report_source_bugs

        # Update genric headers
        store.update_header(**headers)

        # save translation changes
        store.save()

    @cached_property
    def enable_review(self):
        project = self.component.project
        return project.source_review if self.is_source else project.translation_review

    @cached_property
    def list_translation_checks(self):
        """Return list of failing checks on current translation."""
        result = TranslationChecklist()

        # All strings
        result.add(self.stats, "all", "")

        result.add_if(self.stats, "readonly", "default")

        if not self.is_readonly:
            if self.enable_review:
                result.add_if(self.stats, "approved", "info")

            # Count of translated strings
            result.add_if(self.stats, "translated", "success")

            # To approve
            if self.enable_review:
                result.add_if(self.stats, "unapproved", "dark")

                # Approved with suggestions
                result.add_if(self.stats, "approved_suggestions", "info")

            # Untranslated strings
            result.add_if(self.stats, "todo", "danger")

            # Not translated strings
            result.add_if(self.stats, "nottranslated", "danger")

            # Fuzzy strings
            result.add_if(self.stats, "fuzzy", "danger")

            # Translations with suggestions
            result.add_if(self.stats, "suggestions", "dark")
            result.add_if(self.stats, "nosuggestions", "dark")

        # All checks
        result.add_if(self.stats, "allchecks", "warning")

        # Translated strings with checks
        if not self.is_source:
            result.add_if(self.stats, "translated_checks", "warning")

        # Process specific checks
        for check in CHECKS:
            check_obj = CHECKS[check]
            result.add_if(self.stats, check_obj.url_id, "warning")

        # Grab comments
        result.add_if(self.stats, "comments", "dark")

        # Include labels
        labels = self.component.project.label_set.order_by("name")
        if labels:
            for label in labels:
                result.add_if(
                    self.stats,
                    "label:{}".format(label.name),
                    f"label label-{label.color}",
                )
            result.add_if(self.stats, "unlabeled", "")

        return result

    def merge_translations(
        self, request, store2, conflicts: str, method: str, fuzzy: str
    ):
        """Merge translation unit wise.

        Needed for template based translations to add new strings.
        """
        not_found = 0
        skipped = 0
        accepted = 0
        add_fuzzy = method == "fuzzy"
        add_approve = method == "approve"

        for set_fuzzy, unit2 in store2.iterate_merge(fuzzy):
            try:
                unit = self.unit_set.get_unit(unit2)
            except Unit.DoesNotExist:
                not_found += 1
                continue

            state = STATE_TRANSLATED
            if add_fuzzy or set_fuzzy:
                state = STATE_FUZZY
            elif add_approve:
                state = STATE_APPROVED

            if (
                (unit.translated and not conflicts)
                or (unit.approved and conflicts != "replace-approved")
                or unit.readonly
                or (not request.user.has_perm("unit.edit", unit))
                or (unit.target == unit2.target and unit.state == state)
            ):
                skipped += 1
                continue

            accepted += 1

            # We intentionally avoid propagating:
            # - in most cases it's not desired
            # - it slows down import considerably
            # - it brings locking issues as import is
            #   executed with lock held and linked repos
            #   can't obtain the lock
            unit.translate(
                request.user,
                split_plural(unit2.target),
                state,
                change_action=Change.ACTION_UPLOAD,
                propagate=False,
            )

        if accepted > 0:
            self.invalidate_cache()
            request.user.profile.increase_count("translated", accepted)

        return (not_found, skipped, accepted, len(list(store2.content_units)))

    def merge_suggestions(self, request, store, fuzzy):
        """Merge content of translate-toolkit store as a suggestions."""
        not_found = 0
        skipped = 0
        accepted = 0

        for _unused, unit in store.iterate_merge(fuzzy):
            # Grab database unit
            try:
                dbunit = self.unit_set.get_unit(unit)
            except Unit.DoesNotExist:
                not_found += 1
                continue

            # Add suggestion
            if dbunit.target != unit.target and not dbunit.readonly:
                if Suggestion.objects.add(dbunit, unit.target, request):
                    accepted += 1
                else:
                    skipped += 1
            else:
                skipped += 1

        # Update suggestion count
        if accepted > 0:
            self.invalidate_cache()

        return (not_found, skipped, accepted, len(list(store.content_units)))

    def drop_store_cache(self):
        if "store" in self.__dict__:
            del self.__dict__["store"]

    def handle_source(self, request, fileobj):
        """Replace source translations with uploaded one."""
        component = self.component
        filenames = []
        with component.repository.lock:
            # Commit pending changes
            component.commit_pending("source update", request.user)

            # Create acutal file with the file
            temp = tempfile.NamedTemporaryFile(
                prefix="weblate-upload", dir=self.component.full_path, delete=False
            )
            temp.write(fileobj.read())
            temp.close()

            try:
                # Update translation files
                for translation in component.translation_set.exclude(
                    language=component.source_language
                ):
                    filename = translation.get_filename()
                    component.file_format_cls.update_bilingual(filename, temp.name)
                    filenames.append(filename)
            finally:
                if os.path.exists(temp.name):
                    if component.new_base:
                        filename = component.get_new_base_filename()
                        os.replace(temp.name, filename)
                        filenames.append(filename)
                    else:
                        os.unlink(temp.name)

            # Commit changes
            if component.commit_files(
                template=component.addon_message,
                files=filenames,
                author=request.user.get_author_name(),
                extra_context={"addon_name": "Source update"},
            ):
                component.create_translations(request=request, force=True)
        return (0, 0, self.unit_set.count(), self.unit_set.count())

    def handle_replace(self, request, fileobj):
        """Replace file content with uploaded one."""
        filecopy = fileobj.read()
        fileobj.close()
        fileobj = BytesIOMode(fileobj.name, filecopy)
        with self.component.repository.lock:
            self.commit_pending("replace file", request.user)
            # This will throw an exception in case of error
            store2 = self.load_store(fileobj)
            store2.check_valid()

            # Actually replace file content
            self.store.save_atomic(
                self.store.storefile, lambda handle: handle.write(filecopy)
            )

            # Commit to VCS
            if self.git_commit(request.user, request.user.get_author_name()):

                # Drop store cache
                self.drop_store_cache()

                # Parse the file again
                if self.is_template:
                    self.component.create_translations(request=request, force=True)
                else:
                    self.check_sync(
                        force=True,
                        request=request,
                        change=Change.ACTION_REPLACE_UPLOAD,
                    )
                    self.invalidate_cache()

        return (0, 0, self.unit_set.count(), len(list(store2.content_units)))

    @transaction.atomic
    def merge_upload(
        self,
        request,
        fileobj: BinaryIO,
        conflicts: str,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
        method: str = "translate",
        fuzzy: str = "",
    ):
        """Top level handler for file uploads."""
        # Optionally set authorship
        orig_user = None
        if author_email:
            from weblate.auth.models import User

            orig_user = request.user
            request.user = User.objects.get_or_create(
                email=author_email,
                defaults={
                    "username": author_email,
                    "is_active": False,
                    "full_name": author_name or author_email,
                },
            )[0]

        try:
            if method == "replace":
                return self.handle_replace(request, fileobj)

            if method == "source":
                return self.handle_source(request, fileobj)

            filecopy = fileobj.read()
            fileobj.close()

            # Strip possible UTF-8 BOM
            if filecopy[:3] == codecs.BOM_UTF8:
                filecopy = filecopy[3:]

            # Load backend file
            store = try_load(
                fileobj.name,
                filecopy,
                self.component.file_format_cls,
                self.component.template_store,
            )

            # Check valid plural forms
            if hasattr(store.store, "parseheader"):
                header = store.store.parseheader()
                try:
                    number, formula = Plural.parse_plural_forms(header["Plural-Forms"])
                    if not self.plural.same_plural(number, formula):
                        raise PluralFormsMismatch()
                except (ValueError, KeyError):
                    # Formula wrong or missing
                    pass

            if method in ("translate", "fuzzy", "approve"):
                # Merge on units level
                with self.component.repository.lock:
                    return self.merge_translations(
                        request, store, conflicts, method, fuzzy
                    )

            # Add as sugestions
            return self.merge_suggestions(request, store, fuzzy)
        finally:
            if orig_user:
                request.user = orig_user

    def invalidate_cache(self, recurse: bool = True):
        """Invalidate any cached stats."""
        # Invalidate summary stats
        transaction.on_commit(lambda: self.stats.invalidate(recurse=recurse))

    @property
    def keys_cache_key(self):
        return "translation-keys-{}".format(self.pk)

    def invalidate_keys(self):
        cache.delete(self.keys_cache_key)

    def get_export_url(self):
        """Return URL of exported git repository."""
        return self.component.get_export_url()

    def remove(self, user):
        """Remove translation from the VCS."""
        author = user.get_author_name()
        # Log
        self.log_info("removing %s as %s", self.filenames, author)

        # Remove file from VCS
        if any((os.path.exists(name) for name in self.filenames)):
            with self.component.repository.lock:
                self.component.repository.remove(
                    self.filenames,
                    self.get_commit_message(
                        author, template=self.component.delete_message
                    ),
                    author,
                )

        # Delete from the database
        self.stats.invalidate()
        self.delete()

        # Record change
        Change.objects.create(
            component=self.component,
            action=Change.ACTION_REMOVE_TRANSLATION,
            target=self.filename,
            user=user,
            author=user,
        )

    def new_unit(
        self,
        request,
        key: Optional[str],
        value: Optional[Union[str, List[str]]],
        batch: Optional[Dict[str, Union[str, List[str]]]] = None,
    ):
        from weblate.auth.models import get_anonymous

        user = request.user if request else get_anonymous()
        with self.component.repository.lock:
            self.component.commit_pending("new unit", user)
            if batch:
                for batch_key, batch_value in batch.items():
                    self.store.new_unit(batch_key, batch_value)
                    Change.objects.create(
                        translation=self,
                        action=Change.ACTION_NEW_UNIT,
                        target=batch_value,
                        user=user,
                        author=user,
                    )
            else:
                self.store.new_unit(key, value)
                Change.objects.create(
                    translation=self,
                    action=Change.ACTION_NEW_UNIT,
                    target=value,
                    user=user,
                    author=user,
                )
            self.component.create_translations(request=request)
            self.git_commit(user, user.get_author_name())

    def delete_unit(self, request, unit):
        from weblate.auth.models import get_anonymous

        component = self.component
        user = request.user if request else get_anonymous()
        with component.repository.lock:
            component.commit_pending("delete unit", user)
            try:
                pounit, add = self.store.find_unit(unit.context, unit.source)
            except UnitNotFound:
                return
            if add:
                return
            extra_files = self.store.remove_unit(pounit.unit)
            self.addon_commit_files.extend(extra_files)
            self.git_commit(user, user.get_author_name())
        component.create_translations(request=request, force=True)


class GhostTranslation:
    """Ghost translation object used to show missing translations."""

    is_ghost = True

    def __init__(self, component, language):
        self.component = component
        self.language = language
        self.stats = GhostStats(component.source_translation.stats)
        self.pk = self.stats.pk
        self.is_source = False

    def __str__(self):
        return "{0} — {1}".format(self.component, self.language)

    def get_absolute_url(self):
        return None
