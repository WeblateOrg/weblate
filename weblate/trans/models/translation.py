# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import codecs
import os
import tempfile
from itertools import chain
from typing import TYPE_CHECKING, BinaryIO

import sentry_sdk
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext

from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS
from weblate.formats.auto import try_load
from weblate.formats.base import UnitNotFoundError
from weblate.formats.helpers import CONTROLCHARS, BytesIOMode
from weblate.lang.models import Language, Plural
from weblate.trans.checklists import TranslationChecklist
from weblate.trans.defines import FILENAME_LENGTH
from weblate.trans.exceptions import (
    FailedCommitError,
    FileParseError,
    PluralFormsMismatchError,
)
from weblate.trans.mixins import CacheKeyMixin, LoggerMixin, URLMixin
from weblate.trans.models.change import Change
from weblate.trans.models.suggestion import Suggestion
from weblate.trans.models.unit import Unit
from weblate.trans.models.variant import Variant
from weblate.trans.signals import component_post_update, store_post_load, vcs_pre_commit
from weblate.trans.util import join_plural, split_plural
from weblate.trans.validators import validate_check_flags
from weblate.utils.errors import report_error
from weblate.utils.render import render_template
from weblate.utils.site import get_site_url
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_TRANSLATED,
)
from weblate.utils.stats import GhostStats, TranslationStats

if TYPE_CHECKING:
    from datetime import datetime


class TranslationManager(models.Manager):
    def check_sync(
        self, component, lang, code, path, force=False, request=None, change=None
    ):
        """Parse translation meta info and updates translation object."""
        translation = component.translation_set.get_or_create(
            language=lang,
            defaults={"filename": path, "language_code": code, "plural": lang.plural},
        )[0]
        if translation.filename != path or translation.language_code != code:
            force = True
            translation.filename = path
            translation.language_code = code
            translation.save(update_fields=["filename", "language_code"])
        flags = ""
        if (not component.edit_template and translation.is_template) or (
            not component.has_template() and translation.is_source
        ):
            flags = "read-only"
        if translation.check_flags != flags:
            force = True
            translation.check_flags = flags
            translation.save(update_fields=["check_flags"])
        translation.check_sync(force, request=request, change=change)

        return translation


class TranslationQuerySet(models.QuerySet):
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
                to_attr="all_active_alerts",
            ),
        )

    def filter_access(self, user):
        if user.is_superuser:
            return self
        return self.filter(
            Q(component__project__in=user.allowed_projects)
            & (
                Q(component__restricted=False)
                | Q(component_id__in=user.component_permissions)
            )
        )

    def order(self):
        return self.order_by(
            "component__priority", "component__project__name", "component__name"
        )


class Translation(models.Model, URLMixin, LoggerMixin, CacheKeyMixin):
    component = models.ForeignKey("Component", on_delete=models.deletion.CASCADE)
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)
    plural = models.ForeignKey(Plural, on_delete=models.deletion.CASCADE)
    revision = models.CharField(max_length=200, default="", blank=True)
    filename = models.CharField(max_length=FILENAME_LENGTH)

    language_code = models.CharField(max_length=50, default="", blank=True)

    check_flags = models.TextField(
        verbose_name="Translation flags",
        default="",
        validators=[validate_check_flags],
        blank=True,
    )

    objects = TranslationManager.from_queryset(TranslationQuerySet)()

    is_lockable = False
    remove_permission = "translation.delete"
    settings_permission = "component.edit"

    class Meta:
        app_label = "trans"
        unique_together = [("component", "language")]
        verbose_name = "translation"
        verbose_name_plural = "translations"

    def __str__(self):
        return f"{self.component} — {self.language}"

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super().__init__(*args, **kwargs)
        self.stats = TranslationStats(self)
        self.addon_commit_files = []
        self.was_new = 0
        self.reason = ""
        self._invalidate_scheduled = False
        self.update_changes = []

    @cached_property
    def full_slug(self):
        return (
            f"{self.component.project.slug}/{self.component.slug}/{self.language.code}"
        )

    @property
    def code(self):
        return self.language.code

    def log_hook(self, level, msg, *args):
        self.component.store_log(self.full_slug, msg, *args)

    @cached_property
    def is_template(self):
        """
        Check whether this is template translation.

        This means that translations should be propagated as sources to others.
        """
        return self.filename == self.component.template

    @cached_property
    def is_source(self):
        """
        Check whether this is source strings.

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
                gettext(
                    "Filename %s not found in repository! To add new "
                    "translation, add language file into repository."
                )
                % self.filename
            )
        try:
            self.load_store()
        except Exception as error:
            raise ValidationError(
                gettext("Could not parse file %(file)s: %(error)s")
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

    def get_url_path(self):
        return (*self.component.get_url_path(), self.language.code)

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return "{}?lang={}&component={}".format(
            self.component.project.get_widgets_url(),
            self.language.code,
            self.component.slug,
        )

    def get_share_url(self):
        """Return absolute URL usable for sharing."""
        return get_site_url(
            reverse(
                "engage",
                kwargs={"path": [self.component.project.slug, "-", self.language.code]},
            )
        )

    def get_translate_url(self):
        return reverse("translate", kwargs={"path": self.get_url_path()})

    def get_filename(self):
        """Return absolute filename."""
        if not self.filename:
            return None
        return os.path.join(self.component.full_path, self.filename)

    def load_store(self, fileobj=None, force_intermediate=False):
        """Load translate-toolkit storage from disk."""
        # Use intermediate store as template for source translation
        with sentry_sdk.start_span(op="load_store", description=self.get_filename()):
            if force_intermediate or (self.is_template and self.component.intermediate):
                template = self.component.intermediate_store
            else:
                template = self.component.template_store
            if fileobj is None:
                fileobj = self.get_filename()
            elif self.is_template:
                template = self.component.load_template_store(
                    BytesIOMode(fileobj.name, fileobj.read())
                )
                fileobj.seek(0)
            store = self.component.file_format_cls.parse(
                fileobj,
                template,
                language_code=self.language_code,
                source_language=self.component.source_language.code,
                is_template=self.is_template,
                existing_units=self.unit_set.all(),
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
            report_error(
                cause="Translation parse error", project=self.component.project
            )
            self.component.handle_parse_error(exc, self)

    def sync_unit(
        self,
        dbunits: dict[int, Unit],
        updated: dict[int, Unit],
        id_hash: int,
        unit,
        pos: int,
    ):
        try:
            newunit = dbunits[id_hash]
            is_new = False
        except KeyError:
            newunit = Unit(translation=self, id_hash=id_hash, state=-1)
            # Avoid fetching empty list of checks from the database
            newunit.all_checks = []
            # Avoid fetching empty list of variants
            newunit._prefetched_objects_cache = {
                "defined_variants": Variant.objects.none()
            }
            is_new = True

        with sentry_sdk.start_span(
            op="update_from_unit", description=f"{self.full_slug}:{pos}"
        ):
            newunit.update_from_unit(unit, pos, is_new)

        # Check if unit is worth notification:
        # - new and untranslated
        # - newly untranslated
        # - newly fuzzy
        # - source string changed
        if newunit.state < STATE_TRANSLATED and (
            newunit.state != newunit.old_unit["state"]
            or is_new
            or newunit.source != newunit.old_unit["source"]
        ):
            self.was_new += 1

        # Store current unit ID
        updated[id_hash] = newunit

    def check_sync(self, force=False, request=None, change=None):  # noqa: C901
        """Check whether database is in sync with git and possibly updates."""
        with sentry_sdk.start_span(op="check_sync", description=self.full_slug):
            if change is None:
                change = Change.ACTION_UPDATE
            user = None if request is None else request.user

            details = {
                "filename": self.filename,
            }
            self.update_changes = []

            # Check if we're not already up to date
            try:
                new_revision = self.get_git_blob_hash()
            except Exception as exc:
                report_error(
                    cause="Translation parse error", project=self.component.project
                )
                self.component.handle_parse_error(exc, self)
            if not self.revision:
                self.reason = "new file"
            elif self.revision != new_revision:
                self.reason = "content changed"

                # Include changed filename in the details
                old_parts = self.revision.split(",")
                new_parts = new_revision.split(",")
                if len(old_parts) == len(new_parts):
                    filenames = self.get_hash_filenames()
                    for i, old_part in enumerate(old_parts):
                        if old_part != new_parts[i]:
                            details["filename"] = filenames[i][
                                len(self.component.full_path) :
                            ].lstrip("/")
                            break

            elif force:
                self.reason = "check forced"
            else:
                self.reason = ""
                return
            details["reason"] = self.reason

            self.component.check_template_valid()

            # List of updated units (used for cleanup and duplicates detection)
            updated = {}

            try:
                store = self.store
                translation_store = None

                try:
                    store_units = store.content_units
                except ValueError as error:
                    raise FileParseError(str(error))

                self.log_info(
                    "processing %s, %s, %d strings",
                    self.filename,
                    self.reason,
                    len(store_units),
                )

                # Store plural
                plural = store.get_plural(self.language, store)
                if plural != self.plural:
                    self.plural = plural
                    self.save(update_fields=["plural"])

                # Was there change?
                self.was_new = 0

                # Select all current units for update
                dbunits = {
                    unit.id_hash: unit
                    for unit in self.unit_set.prefetch_bulk().select_for_update()
                }

                # Process based on intermediate store if available
                if self.component.intermediate:
                    translation_store = store
                    store = self.load_store(force_intermediate=True)
                    try:
                        store_units = store.content_units
                    except ValueError as error:
                        raise FileParseError(str(error))

                for pos, unit in enumerate(store_units):
                    # Use translation store if exists and if it contains the string
                    if translation_store is not None:
                        try:
                            translated_unit, created = translation_store.find_unit(
                                unit.context, unit.source
                            )
                            if translated_unit and not created:
                                unit = translated_unit
                            else:
                                # Patch unit to have matching source
                                unit.source = translated_unit.source
                        except UnitNotFoundError:
                            pass

                    try:
                        id_hash = unit.id_hash
                    except Exception as error:
                        self.component.handle_parse_error(error, self)

                    # Check for possible duplicate units
                    if id_hash in updated:
                        newunit = updated[id_hash]
                        self.log_warning(
                            "duplicate string to translate: %s (%s)",
                            newunit,
                            repr(newunit.source),
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
                report_error(
                    cause="Could not parse file on update",
                    project=self.component.project,
                )
                self.log_warning("skipping update due to parse error: %s", error)
                self.store_update_changes()
                return

            # Delete stale units
            stale = set(dbunits) - set(updated)
            if stale:
                self.log_info("deleting %d stale strings", len(stale))
                self.unit_set.filter(id_hash__in=stale).delete()
                self.component.needs_cleanup = True

            # We should also do cleanup on source strings tracking objects

            # Update revision and stats
            self.store_hash()

            # Store change entry
            self.update_changes.append(
                Change(
                    translation=self,
                    action=change,
                    user=user,
                    author=user,
                    details=details,
                )
            )

            self.store_update_changes()

            # Invalidate keys cache
            transaction.on_commit(self.invalidate_keys)
            self.log_info("updating completed")

        # Use up to date list as prefetch for source
        if self.is_source:
            self.component.preload_sources(updated)

    def store_update_changes(self):
        # Save change
        Change.objects.bulk_create(self.update_changes, batch_size=500)
        self.update_changes = []

    def do_update(self, request=None, method=None):
        return self.component.do_update(request, method=method)

    def do_push(self, request=None):
        return self.component.do_push(request)

    def do_reset(self, request=None):
        return self.component.do_reset(request)

    def do_cleanup(self, request=None):
        return self.component.do_cleanup(request)

    def do_file_sync(self, request=None):
        return self.component.do_file_sync(request)

    def do_file_scan(self, request=None):
        return self.component.do_file_scan(request)

    def can_push(self):
        return self.component.can_push()

    def has_push_configuration(self):
        return self.component.has_push_configuration()

    def get_hash_filenames(self):
        """Return filenames to include in the hash."""
        component = self.component
        filenames = [self.get_filename()]

        if component.has_template():
            # Include template
            filenames.append(component.get_template_filename())

            filename = component.get_intermediate_filename()
            if component.intermediate and os.path.exists(filename):
                # Include intermediate language as it might add new strings
                filenames.append(filename)

        return filenames

    def get_git_blob_hash(self):
        """Return current VCS blob hash for file."""
        get_object_hash = self.component.repository.get_object_hash

        return ",".join(
            get_object_hash(filename) for filename in self.get_hash_filenames()
        )

    def store_hash(self):
        """Store current hash in database."""
        self.revision = self.get_git_blob_hash()
        self.save(update_fields=["revision"])

    def get_last_author(self):
        """Return last author of change done in Weblate."""
        if not self.stats.last_author:
            return None
        from weblate.auth.models import User

        return User.objects.get(pk=self.stats.last_author).get_visible_name()

    @transaction.atomic
    def commit_pending(self, reason: str, user, skip_push: bool = False):
        """Commit any pending changes."""
        if not self.needs_commit():
            return False
        return self.component.commit_pending(reason, user, skip_push=skip_push)

    @transaction.atomic
    def _commit_pending(self, reason: str, user):
        """
        Translation commit implementation.

        Assumptions:

        - repository lock is held
        - the source translation needs to be committed first
        - signals and alerts are updated by the caller
        - repository push is handled by the caller
        """
        self.log_info("committing pending changes (%s)", reason)

        try:
            store = self.store
        except FileParseError as error:
            report_error(
                cause="Could not parse file on commit", project=self.component.project
            )
            self.log_error("skipping commit due to error: %s", error)
            return False

        try:
            store.ensure_index()
        except ValueError as error:
            report_error(
                cause="Could not parse file on commit", project=self.component.project
            )
            self.log_error("skipping commit due to error: %s", error)
            return False

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
            self.git_commit(user, author_name, timestamp, skip_push=True, signals=False)

        # Update stats (the translated flag might have changed)
        self.invalidate_cache()

        # Make sure template cache is purged upon commit
        self.drop_store_cache()

        return True

    def get_commit_message(self, author: str, template: str, **kwargs):
        """Format commit message based on project configuration."""
        return render_template(template, translation=self, author=author, **kwargs)

    @property
    def count_pending_units(self):
        return self.unit_set.filter(pending=True).count()

    def needs_commit(self):
        """Check whether there are some not committed changes."""
        return self.count_pending_units > 0

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

    def git_commit(
        self,
        user,
        author: str,
        timestamp: datetime | None = None,
        skip_push=False,
        signals=True,
        template: str | None = None,
        store_hash: bool = True,
    ):
        """Wrapper for committing translation to git."""
        repository = self.component.repository
        if template is None:
            template = self.component.commit_message
        with repository.lock:
            # Pre commit hook
            vcs_pre_commit.send(sender=self.__class__, translation=self, author=author)

            # Do actual commit with git lock
            if self.component.commit_files(
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
            if store_hash:
                self.store_hash()
            self.addon_commit_files = []

        return True

    def update_units(self, units, store, author_name, author_id):
        """Update backend file and unit."""
        updated = False
        clear_pending = []
        for unit in units:
            # We reuse the queryset, so pending units might reappear here
            if not unit.pending:
                continue
            # Skip changes by other authors
            change_author = unit.get_last_content_change()[0]
            if change_author.id != author_id:
                continue

            details = unit.details

            # Remove pending flag
            unit.pending = False

            if details.get("add_unit"):
                pounit = store.new_unit(
                    unit.context, unit.get_source_plurals(), unit.get_target_plurals()
                )
                pounit.set_explanation(unit.explanation)
                pounit.set_source_explanation(unit.source_unit.explanation)
                updated = True
                del details["add_unit"]
            else:
                try:
                    pounit, add = store.find_unit(unit.context, unit.source)
                except UnitNotFoundError:
                    # Bail out if we have not found anything
                    report_error(
                        cause="String disappeared", project=self.component.project
                    )
                    self.log_error(
                        "string %s disappeared from the file, removing", unit
                    )
                    unit.delete()
                    continue

                # Optionally add unit to translation file.
                # This has be done prior setting target as some formats
                # generate content based on target language.
                if add:
                    store.add_unit(pounit.unit)

                # Store translations
                try:
                    if unit.is_plural:
                        pounit.set_target(unit.get_target_plurals())
                    else:
                        pounit.set_target(unit.target)
                    pounit.set_explanation(unit.explanation)
                    pounit.set_source_explanation(unit.source_unit.explanation)
                except Exception as error:
                    self.component.handle_parse_error(error, self, reraise=False)
                    report_error(
                        cause="Could not update unit", project=self.component.project
                    )
                    continue

                updated = True

            # Update fuzzy/approved flag
            pounit.set_state(unit.state)

            # Do not go via save() to avoid triggering signals
            if unit.details:
                Unit.objects.filter(pk=unit.pk).update(
                    pending=unit.pending, details=unit.details
                )
            else:
                clear_pending.append(unit.pk)

        if clear_pending:
            Unit.objects.filter(pk__in=clear_pending).update(pending=False, details={})

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
            headers["language_team"] = "{} <{}>".format(
                self.language.name, get_site_url(self.get_absolute_url())
            )

        # Optionally store email for reporting bugs in source
        report_source_bugs = self.component.report_source_bugs
        if report_source_bugs:
            headers["report_msgid_bugs_to"] = report_source_bugs

        # Update generic headers
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

        result.add_if(
            self.stats, "readonly", "info" if self.enable_review else "success"
        )

        if not self.is_readonly:
            if self.enable_review:
                result.add_if(self.stats, "approved", "info")

            # Count of translated strings
            result.add_if(self.stats, "translated", "success")

            # To approve
            if self.enable_review:
                result.add_if(self.stats, "unapproved", "success")

                # Approved with suggestions
                result.add_if(self.stats, "approved_suggestions", "info")

            # Unfinished strings
            result.add_if(self.stats, "todo", "danger")

            # Untranslated strings
            result.add_if(self.stats, "nottranslated", "danger")

            # Fuzzy strings
            result.add_if(self.stats, "fuzzy", "danger")

            # Translations with suggestions
            result.add_if(self.stats, "suggestions", "danger")
            result.add_if(self.stats, "nosuggestions", "danger")

        # All checks
        result.add_if(self.stats, "allchecks", "danger")

        # Translated strings with checks
        if not self.is_source:
            result.add_if(self.stats, "translated_checks", "danger")

        # Dismissed checks
        result.add_if(self.stats, "dismissed_checks", "danger")

        # Process specific checks
        for check in CHECKS:
            check_obj = CHECKS[check]
            result.add_if(self.stats, check_obj.url_id, "danger")

        # Grab comments
        result.add_if(self.stats, "comments", "")

        # Include labels
        labels = self.component.project.label_set.order_by("name")
        if labels:
            for label in labels:
                result.add_if(
                    self.stats,
                    f"label:{label.name}",
                    f"label label-{label.color}",
                )
            result.add_if(self.stats, "unlabeled", "")

        return result

    def merge_translations(
        self, request, store2, conflicts: str, method: str, fuzzy: str
    ):
        """
        Merge translation unit wise.

        Needed for template based translations to add new strings.
        """
        not_found = 0
        skipped = 0
        accepted = 0
        add_fuzzy = method == "fuzzy"
        add_approve = method == "approve"

        # Are there any translations to propagate?
        # This is just an optimalization to avoid doing that for every unit.
        propagate = (
            Translation.objects.filter(
                language=self.language,
                component__source_language_id=self.component.source_language_id,
                component__project=self.component.project,
            )
            .filter(component__allow_translation_propagation=True)
            .exclude(pk=self.pk)
            .exists()
        )

        unit_set = self.unit_set.all()

        for set_fuzzy, unit2 in store2.iterate_merge(fuzzy):
            try:
                unit = unit_set.get_unit(unit2)
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
                propagate=propagate,
            )

        if accepted > 0:
            self.invalidate_cache()
            request.user.profile.increase_count("translated", accepted)

        return (not_found, skipped, accepted, len(store2.content_units))

    def merge_suggestions(self, request, store, fuzzy):
        """Merge content of translate-toolkit store as a suggestions."""
        not_found = 0
        skipped = 0
        accepted = 0

        unit_set = self.unit_set.all()

        for _unused, unit in store.iterate_merge(fuzzy):
            # Grab database unit
            try:
                dbunit = unit_set.get_unit(unit)
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

        return (not_found, skipped, accepted, len(store.content_units))

    def drop_store_cache(self):
        if "store" in self.__dict__:
            del self.__dict__["store"]
        if self.is_source:
            self.component.drop_template_store_cache()

    def handle_source(self, request, fileobj):
        """Replace source translations with uploaded one."""
        component = self.component
        filenames = []
        with component.repository.lock:
            # Commit pending changes
            try:
                component.commit_pending("source update", request.user)
            except Exception as error:
                raise FailedCommitError(
                    gettext("Could not commit pending changes: %s")
                    % str(error).replace(self.component.full_path, "")
                )

            # Create actual file with the uploaded content
            temp = tempfile.NamedTemporaryFile(
                prefix="weblate-upload", dir=self.component.full_path, delete=False
            )
            temp.write(fileobj.read())
            temp.close()

            try:
                # Prepare msgmerge args, this is merely a copy from
                # weblate.addons.gettext.MsgmergeAddon and should be turned into
                # file format parameters
                args = ["--previous"]
                try:
                    addon = component.addon_set.get(name="weblate.gettext.customize")
                    addon_config = addon.configuration
                    if addon_config["width"] != 77:
                        args.append("--no-wrap")
                except ObjectDoesNotExist:
                    pass
                try:
                    addon = component.addon_set.get(name="weblate.gettext.msgmerge")
                    addon_config = addon.configuration
                    if not addon_config.get("fuzzy", True):
                        args.append("--no-fuzzy-matching")
                    if addon_config.get("previous", True):
                        args.append("--previous")
                    if addon_config.get("no_location", False):
                        args.append("--no-location")
                except ObjectDoesNotExist:
                    pass

                # Update translation files
                for translation in component.translation_set.exclude(
                    language=component.source_language
                ):
                    filename = translation.get_filename()
                    component.file_format_cls.update_bilingual(
                        filename, temp.name, args=args
                    )
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
            previous_revision = self.component.repository.last_revision
            if component.commit_files(
                template=component.addon_message,
                files=filenames,
                author=request.user.get_author_name(),
                extra_context={"addon_name": "Source update"},
            ):
                self.handle_store_change(
                    request,
                    request.user,
                    previous_revision,
                    change=Change.ACTION_REPLACE_UPLOAD,
                )
        return (0, 0, self.unit_set.count(), self.unit_set.count())

    def handle_replace(self, request, fileobj):
        """Replace file content with uploaded one."""
        filecopy = fileobj.read()
        fileobj.close()
        fileobj = BytesIOMode(fileobj.name, filecopy)
        with self.component.repository.lock:
            try:
                if self.is_source:
                    self.component.commit_pending("replace file", request.user)
                else:
                    self.commit_pending("replace file", request.user)
            except Exception as error:
                raise FailedCommitError(
                    gettext("Could not commit pending changes: %s")
                    % str(error).replace(self.component.full_path, "")
                )
            # This will throw an exception in case of error
            store2 = self.load_store(fileobj)
            store2.check_valid()

            # Actually replace file content
            self.store.save_atomic(
                self.store.storefile, lambda handle: handle.write(filecopy)
            )

            # Commit to VCS
            previous_revision = self.component.repository.last_revision
            if self.git_commit(
                request.user, request.user.get_author_name(), store_hash=False
            ):
                # Drop store cache
                self.handle_store_change(
                    request,
                    request.user,
                    previous_revision,
                    change=Change.ACTION_REPLACE_UPLOAD,
                )

        return (0, 0, self.unit_set.count(), len(store2.content_units))

    def handle_add_upload(self, request, store, fuzzy: str = ""):
        component = self.component
        has_template = component.has_template()
        skipped = 0
        accepted = 0
        component.start_batched_checks()
        if has_template:
            existing = set(self.unit_set.values_list("context", flat=True))
        else:
            existing = set(self.unit_set.values_list("context", "source"))
        for _set_fuzzy, unit in store.iterate_merge(fuzzy, only_translated=False):
            idkey = unit.context if has_template else (unit.context, unit.source)
            if idkey in existing:
                skipped += 1
                continue
            self.add_unit(
                request,
                unit.context,
                split_plural(unit.source),
                split_plural(unit.target) if not self.is_source else [],
                is_batch_update=True,
            )
            existing.add(idkey)
            accepted += 1
        self.was_new = accepted
        self.notify_new(request)
        component.invalidate_cache()
        if component.needs_variants_update:
            component.update_variants()
        component.schedule_sync_terminology()
        component.update_source_checks()
        component.run_batched_checks()
        component_post_update.send(sender=self.__class__, component=component)
        return (0, skipped, accepted, len(store.content_units))

    @transaction.atomic
    def handle_upload(  # noqa: C901
        self,
        request,
        fileobj: BinaryIO,
        conflicts: str,
        author_name: str | None = None,
        author_email: str | None = None,
        method: str = "translate",
        fuzzy: str = "",
    ):
        """Top level handler for file uploads."""
        from weblate.accounts.models import AuditLog

        component = self.component

        # Optionally set authorship
        orig_user = None
        if author_email:
            from weblate.auth.models import User

            orig_user = request.user
            request.user, created = User.objects.get_or_create(
                email=author_email,
                defaults={
                    "username": author_email,
                    "full_name": author_name or author_email,
                },
            )
            if created:
                AuditLog.objects.create(
                    request.user,
                    request,
                    "autocreated",
                )

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

            # Commit pending changes in template
            if component.has_template() and component.source_translation.needs_commit():
                try:
                    component.commit_pending("upload", request.user)
                except Exception as error:
                    raise FailedCommitError(
                        gettext("Could not commit pending changes: %s")
                        % str(error).replace(self.component.full_path, "")
                    )

            # Load backend file
            if method == "add" and self.is_template:
                template_store = try_load(
                    fileobj.name,
                    filecopy,
                    component.file_format_cls,
                    None,
                    as_template=True,
                )
            else:
                template_store = component.template_store
            store = try_load(
                fileobj.name,
                filecopy,
                component.file_format_cls,
                template_store,
            )

            # Check valid plural forms
            if hasattr(store.store, "parseheader"):
                header = store.store.parseheader()
                try:
                    number, formula = Plural.parse_plural_forms(header["Plural-Forms"])
                except (ValueError, KeyError):
                    # Formula wrong or missing
                    pass
                else:
                    if not self.plural.same_plural(number, formula):
                        raise PluralFormsMismatchError

            if method in ("translate", "fuzzy", "approve"):
                # Merge on units level
                return self.merge_translations(request, store, conflicts, method, fuzzy)
            if method == "add":
                with component.lock:
                    return self.handle_add_upload(request, store, fuzzy=fuzzy)

            # Add as suggestions
            return self.merge_suggestions(request, store, fuzzy)  # noqa: TRY300
        finally:
            if orig_user:
                request.user = orig_user

    def _invalidate_triger(self):
        self._invalidate_scheduled = False
        self.stats.invalidate()
        self.component.invalidate_glossary_cache()

    def invalidate_cache(self):
        """Invalidate any cached stats."""
        # Invalidate summary stats
        if self._invalidate_scheduled:
            return
        self._invalidate_scheduled = True
        transaction.on_commit(self._invalidate_triger)

    @property
    def keys_cache_key(self):
        return f"translation-keys-{self.pk}"

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
        if any(os.path.exists(name) for name in self.filenames):
            with self.component.repository.lock:
                self.component.repository.remove(
                    self.filenames,
                    self.get_commit_message(
                        author, template=self.component.delete_message
                    ),
                    author,
                )
                self.component.push_if_needed()

        # Delete from the database
        self.stats.invalidate()
        self.delete()
        transaction.on_commit(self.component.schedule_update_checks)

        # Record change
        Change.objects.create(
            component=self.component,
            action=Change.ACTION_REMOVE_TRANSLATION,
            target=self.filename,
            user=user,
            author=user,
        )

    def handle_store_change(self, request, user, previous_revision: str, change=None):
        self.drop_store_cache()
        # Explicit stats invalidation is needed here as the unit removal in
        # delete_unit might do changes in the database only and not touch the files
        # for pending new units
        if self.is_source:
            self.component.create_translations(request=request, change=change)
            self.component.invalidate_cache()
        else:
            self.check_sync(request=request, change=change)
            self.notify_new(request)
            self.invalidate_cache()
        # Trigger post-update signal
        self.component.trigger_post_update(previous_revision, False)

    def get_store_change_translations(self):
        component = self.component
        result = []
        if self.is_source:
            result.extend(component.translation_set.exclude(id=self.id))
        # Source is always at the end
        result.append(self)
        return result

    @transaction.atomic
    def add_unit(  # noqa: C901
        self,
        request,
        context: str,
        source: str | list[str],
        target: str | list[str] | None = None,
        extra_flags: str = "",
        explanation: str = "",
        auto_context: bool = False,
        is_batch_update: bool = False,
        skip_existing: bool = False,
        state: int | None = None,
    ):
        if isinstance(source, list):
            source = join_plural(source)
        user = request.user if request else None
        component = self.component
        if self.is_source:
            translations = (
                self,
                *component.translation_set.exclude(id=self.id).select_related(
                    "language"
                ),
            )
        elif component.is_glossary and "terminology" in Flags(extra_flags):
            translations = (
                component.source_translation,
                *component.translation_set.exclude(
                    id=component.source_translation.id
                ).select_related("language"),
            )
        else:
            translations = (component.source_translation, self)
        has_template = component.has_template()
        source_unit = None
        result = None

        # Automatic context
        if auto_context:
            suffix = 0
            base = context
            filter_args = {"source": source} if not has_template else {}
            while self.unit_set.filter(context=context, **filter_args).exists():
                suffix += 1
                context = f"{base}{suffix}"

        unit_ids = []
        changes = []
        for translation in translations:
            is_source = translation.is_source
            kwargs = {}
            if has_template:
                kwargs["pending"] = is_source
            else:
                kwargs["pending"] = not is_source
            if kwargs["pending"]:
                kwargs["details"] = {"add_unit": True}
            if (self.is_source and is_source) or (not self.is_source and not is_source):
                kwargs["explanation"] = explanation
            if is_source:
                current_target = source
                kwargs["extra_flags"] = extra_flags
            else:
                current_target = target
            if current_target is None:
                current_target = ""
            if isinstance(current_target, list):
                has_translation = any(current_target)
                current_target = join_plural(current_target)
            else:
                has_translation = bool(current_target)
            id_hash = component.file_format_cls.unit_class.calculate_id_hash(
                has_template, source, context
            )
            # When adding to a target the source string can already exist
            unit = None
            if (skip_existing or not self.is_source) and is_source:
                try:
                    unit = component.get_source(id_hash)
                    flags = Flags(unit.extra_flags)
                    flags.merge(extra_flags)
                    new_flags = flags.format()
                    if not skip_existing and (
                        unit.extra_flags != new_flags or unit.explanation != explanation
                    ):
                        unit.extra_flags = new_flags
                        unit.explanation = explanation
                        unit.save(
                            update_fields=["extra_flags", "explanation"],
                            same_content=True,
                            sync_terminology=False,
                        )
                except Unit.DoesNotExist:
                    pass
            if unit is None:
                if has_translation and (state is None or state == STATE_EMPTY):
                    unit_state = STATE_TRANSLATED
                elif not has_translation and (state is None or state != STATE_EMPTY):
                    unit_state = STATE_EMPTY
                else:
                    unit_state = state
                unit = Unit(
                    translation=translation,
                    context=context,
                    source=source,
                    target=current_target,
                    state=unit_state,
                    source_unit=source_unit,
                    id_hash=id_hash,
                    position=translation.stats.all + 1,
                    **kwargs,
                )
                unit.is_batch_update = is_batch_update
                unit.trigger_update_variants = False
                try:
                    with transaction.atomic():
                        unit.save(
                            force_insert=True,
                            sync_terminology=False,
                        )
                        changes.append(
                            unit.generate_change(
                                user=user,
                                author=user,
                                change_action=Change.ACTION_NEW_UNIT,
                                check_new=False,
                                save=False,
                            )
                        )
                except IntegrityError:
                    if not skip_existing:
                        raise
                    unit = translation.unit_set.get(id_hash=id_hash)
            # The source language is always first in the translations array
            if source_unit is None:
                source_unit = unit
                component._sources[id_hash] = unit
            if translation == self:
                result = unit
            unit_ids.append(unit.pk)

        if changes:
            Change.objects.bulk_create(changes)

        if not is_batch_update:
            if self.component.needs_variants_update:
                component.update_variants(
                    updated_units=Unit.objects.filter(pk__in=unit_ids)
                )
            component.invalidate_cache()
            component_post_update.send(sender=self.__class__, component=component)
            self.was_new = 1
            self.notify_new(request)
        return result

    def notify_deletion(self, unit, user):
        self.change_set.create(
            action=Change.ACTION_STRING_REMOVE,
            user=user,
            target=unit.target,
            details={
                "source": unit.source,
                "target": unit.target,
            },
        )

    @transaction.atomic
    def delete_unit(self, request, unit):
        from weblate.auth.models import get_anonymous

        component = self.component
        user = request.user if request else get_anonymous()
        with component.repository.lock:
            component.commit_pending("delete unit", user)
            previous_revision = self.component.repository.last_revision
            cleanup_variants = False
            for translation in self.get_store_change_translations():
                # Does unit exist here?
                try:
                    translation_unit = translation.unit_set.get(id_hash=unit.id_hash)
                except ObjectDoesNotExist:
                    continue
                # Delete the removed unit from the database
                cleanup_variants |= translation_unit.variant_id is not None
                translation_unit.delete()
                self.notify_deletion(translation_unit, user)
                # Skip file processing on source language without a storage
                if not self.filename:
                    continue
                # Does unit exist in the file?
                try:
                    pounit, add = translation.store.find_unit(unit.context, unit.source)
                except UnitNotFoundError:
                    continue
                if add:
                    continue
                # Commit changed file
                extra_files = translation.store.remove_unit(pounit.unit)
                translation.addon_commit_files.extend(extra_files)
                translation.drop_store_cache()
                translation.git_commit(user, user.get_author_name(), store_hash=False)
                # Adjust position as it will happen in most formats
                if translation_unit.position:
                    translation.unit_set.filter(
                        position__gt=translation_unit.position
                    ).update(position=F("position") - 1)
                # Delete stale source units
                if not self.is_source and translation == self:
                    source_unit = translation_unit.source_unit
                    if source_unit.source_unit.unit_set.count() == 1:
                        source_unit.delete()
                        source_unit.translation.notify_deletion(source_unit, user)

            if self.is_source and unit.position and not component.has_template():
                # Adjust position is source language
                self.unit_set.filter(position__gt=unit.position).update(
                    position=F("position") - 1
                )

            if cleanup_variants:
                self.component.update_variants()

            self.handle_store_change(request, user, previous_revision)

    @transaction.atomic
    def sync_terminology(self):
        if not self.is_source or not self.component.manage_units:
            return
        expected_count = self.component.translation_set.count()
        self.was_new = 0
        for source in self.component.get_all_sources():
            # Is the string a terminology
            if "terminology" not in source.all_flags:
                continue
            if source.unit_set.count() == expected_count:
                continue
            # Add unit
            self.add_unit(
                None,
                source.context,
                source.get_source_plurals(),
                "",
                is_batch_update=True,
                skip_existing=True,
            )
            self.was_new += 1
        self.notify_new(None)

    def validate_new_unit_data(
        self,
        context: str,
        source: str | list[str],
        target: str | list[str] | None = None,
        auto_context: bool = False,
        extra_flags: str | None = None,
        explanation: str = "",
        state: int | None = None,
    ):
        extra = {}
        if isinstance(source, str):
            source = [source]
        for text in chain(source, [context]):
            if any(char in text for char in CONTROLCHARS):
                raise ValidationError(
                    gettext("String contains control character: %s") % repr(text)
                )
        if state is not None:
            if state == STATE_EMPTY and any(source):
                raise ValidationError(
                    gettext("Empty state is supported for blank strings only.")
                )
            if not any(source) and state != STATE_EMPTY:
                raise ValidationError(gettext("Blank strings require an empty state."))
            if state == STATE_APPROVED and not self.enable_review:
                raise ValidationError(
                    gettext(
                        "Approved state is not available as reviews are not enabled."
                    )
                )
        if context:
            self.component.file_format_cls.validate_context(context)
        if not self.component.has_template():
            extra["source"] = join_plural(source)
        if not auto_context and self.unit_set.filter(context=context, **extra).exists():
            raise ValidationError(gettext("This string seems to already exist."))
        # Avoid using source translations without a filename
        if not self.filename:
            try:
                translation = self.component.translation_set.exclude(pk=self.pk)[0]
            except IndexError:
                raise ValidationError(
                    gettext("Failed adding string, no translation found.")
                )
            translation.validate_new_unit_data(
                context,
                source,
                target,
                auto_context=auto_context,
                extra_flags=extra_flags,
                explanation=explanation,
            )
            return

    @property
    def all_repo_components(self):
        return self.component.all_repo_components


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
        return f"{self.component} — {self.language}"

    def get_absolute_url(self):
        return None
