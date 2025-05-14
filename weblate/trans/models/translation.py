# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import codecs
import os
import tempfile
from datetime import UTC
from itertools import chain
from typing import TYPE_CHECKING, BinaryIO, Literal, NotRequired, TypedDict

import sentry_sdk
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext, ngettext

from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS
from weblate.formats.auto import try_load
from weblate.formats.base import TranslationFormat, TranslationUnit, UnitNotFoundError
from weblate.formats.helpers import CONTROLCHARS, NamedBytesIO
from weblate.lang.models import Language, Plural
from weblate.trans.actions import ActionEvents
from weblate.trans.checklists import TranslationChecklist
from weblate.trans.defines import FILENAME_LENGTH
from weblate.trans.exceptions import (
    FailedCommitError,
    FileParseError,
    PluralFormsMismatchError,
)
from weblate.trans.mixins import CacheKeyMixin, LockMixin, LoggerMixin, URLMixin
from weblate.trans.models.change import Change
from weblate.trans.models.suggestion import Suggestion
from weblate.trans.models.unit import Unit
from weblate.trans.models.variant import Variant
from weblate.trans.signals import component_post_update, store_post_load, vcs_pre_commit
from weblate.trans.util import is_plural, join_plural, split_plural
from weblate.trans.validators import validate_check_flags
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.html import format_html_join_comma
from weblate.utils.render import render_template
from weblate.utils.site import get_site_url
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
    StringState,
)
from weblate.utils.stats import GhostStats, TranslationStats

if TYPE_CHECKING:
    from datetime import datetime

    from weblate.auth.models import AuthenticatedHttpRequest, User

UploadResult = tuple[int, int, int, int]


class NewUnitParams(TypedDict):
    context: NotRequired[str]
    source: str | list[str]
    target: NotRequired[str | list[str] | None]
    auto_context: NotRequired[bool]
    extra_flags: NotRequired[str | None]
    explanation: NotRequired[str]
    state: NotRequired[int | None]
    skip_existing: NotRequired[bool]


class TranslationManager(models.Manager):
    def check_sync(
        self,
        component,
        lang,
        code,
        path,
        force=False,
        request: AuthenticatedHttpRequest | None = None,
        change=None,
    ):
        """Parse translation meta info and updates translation object."""
        translation, _created = component.translation_set.get_or_create(
            language=lang,
            defaults={"filename": path, "language_code": code, "plural": lang.plural},
        )
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
    def prefetch(self, *, defer_huge: bool = True):
        from weblate.trans.models import Component

        component_prefetch: str | models.Prefetch
        if defer_huge:
            component_prefetch = models.Prefetch(
                "component", queryset=Component.objects.defer_huge()
            )
        else:
            component_prefetch = "component"

        return self.prefetch_related(
            component_prefetch,
            "component__project",
            "component__category",
            "component__category__project",
            "component__category__category",
            "component__category__category__project",
            "component__category__category__category",
            "component__category__category__category__project",
        ).prefetch_meta()

    def prefetch_meta(self):
        from weblate.trans.models import Alert, Component

        return self.prefetch_related(
            "language",
            models.Prefetch(
                "component__linked_component", queryset=Component.objects.defer_huge()
            ),
            "component__linked_component__project",
            models.Prefetch(
                "component__alert_set",
                queryset=Alert.objects.filter(dismissed=False),
                to_attr="all_active_alerts",
            ),
        )

    def prefetch_plurals(self):
        return self.prefetch_related("language__plural_set")

    def filter_access(self, user: User):
        result = self
        if user.needs_project_filter:
            result = result.filter(component__project__in=user.allowed_projects)
        if user.needs_component_restrictions_filter:
            result = result.filter(
                Q(component__restricted=False)
                | Q(component_id__in=user.component_permissions)
            )
        return result

    def order(self):
        return self.order_by(
            "component__priority", "component__project__name", "component__name"
        )


class Translation(models.Model, URLMixin, LoggerMixin, CacheKeyMixin, LockMixin):
    component = models.ForeignKey(
        "trans.Component", on_delete=models.deletion.CASCADE, db_index=False
    )
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

    remove_permission = "translation.delete"
    settings_permission = "component.edit"

    class Meta:
        app_label = "trans"
        unique_together = [("component", "language")]
        verbose_name = "translation"
        verbose_name_plural = "translations"

    def __str__(self) -> str:
        return f"{self.component} — {self.language}"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.stats = TranslationStats(self)
        self.addon_commit_files: list[str] = []
        self.reason = ""
        self._invalidate_scheduled = False
        self.update_changes: list[Change] = []
        # Project backup integration
        self.original_id = -1

        self.create_unit_change_action = ActionEvents.NEW_UNIT_REPO
        self.update_unit_change_action = ActionEvents.STRING_REPO_UPDATE

    @property
    def code(self):
        return self.language.code

    def log_hook(self, level, msg, *args) -> None:
        self.component.store_log(self.full_slug, msg, *args)

    @cached_property
    def is_template(self):
        """
        Check whether this is template translation.

        This means that translations should be propagated as sources to others.
        """
        return self.component.template and self.filename == self.component.template

    @cached_property
    def is_source(self) -> bool:
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

    def clean(self) -> None:
        """Validate that filename exists and can be opened using translate-toolkit."""
        filename = self.get_filename()
        if filename is None:
            # Should not actually happen
            msg = "Translation without a filename!"
            raise ValidationError(msg)
        if not os.path.exists(filename):
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
            ) from error

    def get_url_path(self):
        return (*self.component.get_url_path(), self.language.code)

    def get_widgets_url(self) -> str:
        """Return absolute URL for widgets."""
        return f"{self.component.project.get_widgets_url()}?lang={self.language.code}&component={self.component.pk}"

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

    def get_filename(self) -> str | None:
        """Return absolute filename."""
        if not self.filename:
            return None
        return os.path.join(self.component.full_path, self.filename)

    def load_store(self, fileobj=None, force_intermediate=False):
        """Load translate-toolkit storage from disk."""
        # Use intermediate store as template for source translation
        with sentry_sdk.start_span(
            op="translation.load_store", name=self.get_filename()
        ):
            if force_intermediate or (self.is_template and self.component.intermediate):
                template = self.component.intermediate_store
            else:
                template = self.component.template_store
            if fileobj is None:
                fileobj = self.get_filename()
                if fileobj is None:
                    msg = "Attempt to parse store without a filename."
                    raise ValueError(msg)
            elif self.is_template:
                template = self.component.load_template_store(
                    NamedBytesIO(fileobj.name, fileobj.read())
                )
                fileobj.seek(0)
            store = self.component.file_format_cls(
                fileobj,
                template,
                language_code=self.language_code,
                source_language=self.language_code
                if self.component.has_template()
                else self.component.source_language.code,
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
                "Translation parse error", project=self.component.project, print_tb=True
            )
            self.component.handle_parse_error(exc, self)

    def sync_unit(
        self,
        dbunits: dict[int, Unit],
        updated: dict[int, Unit],
        id_hash: int,
        unit,
        pos: int,
    ) -> None:
        try:
            newunit = dbunits[id_hash]
            is_new = False
        except KeyError:
            newunit = Unit(translation=self, id_hash=id_hash, state=-1)
            # Avoid fetching empty list of checks from the database
            newunit.all_checks = []
            # Avoid fetching empty list of variants
            newunit._prefetched_objects_cache = {  # noqa: SLF001
                "defined_variants": Variant.objects.none()
            }
            is_new = True

        with sentry_sdk.start_span(
            op="unit.update_from_unit", name=f"{self.full_slug}:{pos}"
        ):
            newunit.update_from_unit(unit, pos, is_new)

        # Store current unit ID
        updated[id_hash] = newunit

    def check_sync(  # noqa: C901
        self,
        force: bool = False,
        request: AuthenticatedHttpRequest | None = None,
        change: int | None = None,
    ) -> None:
        """Check whether database is in sync with git and possibly updates."""
        with sentry_sdk.start_span(op="translation.check_sync", name=self.full_slug):
            if change is None:
                change = ActionEvents.UPDATE
            user = None if request is None else request.user

            details = {
                "filename": self.filename,
            }
            self.update_changes = []

            # Check if we're not already up to date
            try:
                new_revision = self.get_git_blob_hash()
            except FileNotFoundError:
                self.reason = ""
                return
            except Exception as exc:
                report_error("Translation parse error", project=self.component.project)
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
            updated: dict[int, Unit] = {}

            try:
                store = self.store
                translation_store = None

                try:
                    store_units = store.content_units
                except ValueError as error:
                    raise FileParseError(str(error)) from error

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
                        raise FileParseError(str(error)) from error

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
                    if (
                        self.component.file_format_cls.monolingual
                        and self.component.key_filter_re
                        and self.component.key_filter_re.match(unit.context) is None
                    ):
                        # This is where the key filtering take place
                        self.log_info(
                            "Doesn't match with key_filter, skipping: %s (%s)",
                            unit.context,
                            repr(unit.source),
                        )
                        continue

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
                    "Could not parse file on update", project=self.component.project
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

    def store_update_changes(self) -> None:
        # Save change
        Change.objects.bulk_create(self.update_changes, batch_size=500)
        self.update_changes.clear()

    def do_update(self, request: AuthenticatedHttpRequest | None = None, method=None):
        return self.component.do_update(request, method=method)

    def do_push(self, request: AuthenticatedHttpRequest | None = None):
        return self.component.do_push(request)

    def do_reset(self, request: AuthenticatedHttpRequest | None = None):
        return self.component.do_reset(request)

    def do_cleanup(self, request: AuthenticatedHttpRequest | None = None):
        return self.component.do_cleanup(request)

    def do_file_sync(self, request: AuthenticatedHttpRequest | None = None):
        return self.component.do_file_sync(request)

    def do_file_scan(self, request: AuthenticatedHttpRequest | None = None):
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

    def store_hash(self) -> None:
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
    def commit_pending(self, reason: str, user: User | None, skip_push: bool = False):
        """Commit any pending changes."""
        if not self.needs_commit():
            return False
        return self.component.commit_pending(reason, user, skip_push=skip_push)

    @transaction.atomic
    def _commit_pending(self, reason: str, user: User | None) -> bool:
        """
        Commit pending translation.

        Assumptions:

        - repository lock is held
        - the source translation needs to be committed first
        - signals and alerts are updated by the caller
        - repository push is handled by the caller
        """
        try:
            store = self.store
        except FileParseError as error:
            report_error(
                "Could not parse file on commit", project=self.component.project
            )
            self.log_error("skipping commit due to error: %s", error)
            return False

        try:
            store.ensure_index()
        except ValueError as error:
            report_error(
                "Could not parse file on commit", project=self.component.project
            )
            self.log_error("skipping commit due to error: %s", error)
            return False

        units = list(
            self.unit_set.filter(pending=True)
            .prefetch_recent_content_changes()
            .select_for_update()
        )

        self.log_info("committing %d pending changes (%s)", len(units), reason)

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
        user: User | None,
        author: str,
        timestamp: datetime | None = None,
        skip_push=False,
        signals=True,
        template: str | None = None,
        store_hash: bool = True,
    ) -> bool:
        """Commit translation to git."""
        repository = self.component.repository
        if template is None:
            template = self.component.commit_message
        with repository.lock:
            # Pre commit hook
            vcs_pre_commit.send(
                sender=self.__class__,
                translation=self,
                author=author,
                store_hash=store_hash,
            )

            # Do actual commit with git lock
            if self.component.commit_files(
                template=template,
                author=author,
                timestamp=timestamp,
                skip_push=skip_push,
                signals=signals,
                files=self.filenames + self.addon_commit_files,
                extra_context={"translation": self},
                store_hash=store_hash,
            ):
                self.log_info("committed %s as %s", self.filenames, author)
                self.change_set.create(action=ActionEvents.COMMIT, user=user)

            # Store updated hash
            if store_hash:
                self.store_hash()
            self.addon_commit_files = []

        return True

    def update_units(  # noqa: C901
        self,
        units: list[Unit],
        store: TranslationFormat,
        author_name: str,
        author_id: int,
    ) -> None:
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
                # Check if context has changed while adding to storage
                if pounit.context != unit.context:
                    if self.is_source:
                        # Update all matching translations
                        Unit.objects.filter(
                            context=unit.context, translation__component=self.component
                        ).update(context=pounit.context)
                    else:
                        # Update this unit only
                        Unit.objects.filter(pk=unit.pk).update(context=pounit.context)
                    unit.context = pounit.context
                updated = True
                del details["add_unit"]
            else:
                try:
                    pounit, add = store.find_unit(unit.context, unit.source)
                except UnitNotFoundError:
                    # Bail out if we have not found anything
                    report_error("String disappeared", project=self.component.project)
                    # TODO: once we have a deeper stack of pending changes,
                    # this should be kept as pending, so that the changes are not lost
                    unit.state = STATE_FUZZY
                    # Use update instead of hitting expensive save()
                    Unit.objects.filter(pk=unit.pk).update(state=STATE_FUZZY)
                    unit.change_set.create(
                        action=ActionEvents.SAVE_FAILED,
                        target="Could not find string in the translation file",
                    )
                    clear_pending.append(unit.pk)
                    continue

                # Optionally add unit to translation file.
                # This has be done prior setting target as some formats
                # generate content based on target language.
                if add:
                    store.add_unit(pounit)

                # Store translations
                try:
                    if unit.is_plural:
                        pounit.set_target(unit.get_target_plurals())
                    else:
                        pounit.set_target(unit.target)
                    pounit.set_explanation(unit.explanation)
                    pounit.set_source_explanation(unit.source_unit.explanation)
                except Exception as error:
                    report_error(
                        "Could not update unit", project=self.component.project
                    )
                    # TODO: once we have a deeper stack of pending changes,
                    # this should be kept as pending, so that the changes are not lost
                    unit.state = STATE_FUZZY
                    # Use update instead of hitting expensive save()
                    Unit.objects.filter(pk=unit.pk).update(state=STATE_FUZZY)
                    unit.change_set.create(
                        action=ActionEvents.SAVE_FAILED,
                        target=self.component.get_parse_error_message(error),
                    )
                    clear_pending.append(unit.pk)
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
            now = timezone.make_aware(now, UTC)

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
            headers["language_team"] = (
                f"{self.language.name} <{get_site_url(self.get_absolute_url())}>"
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
    def workflow_settings(self):
        return self.component.project.project_languages[self.language].workflow_settings

    @cached_property
    def enable_review(self):
        project = self.component.project
        project_review = (
            project.source_review if self.is_source else project.translation_review
        )
        if not project_review:
            return False
        if self.workflow_settings is not None:
            return self.workflow_settings.translation_review
        return project_review

    @property
    def enable_suggestions(self):
        if self.workflow_settings is not None:
            return self.workflow_settings.enable_suggestions
        return self.component.enable_suggestions

    @property
    def suggestion_voting(self):
        if self.workflow_settings is not None:
            return self.workflow_settings.suggestion_voting
        return self.component.suggestion_voting

    @property
    def suggestion_autoaccept(self):
        if self.workflow_settings is not None:
            return self.workflow_settings.suggestion_autoaccept
        return self.component.suggestion_autoaccept

    @cached_property
    def list_translation_checks(self):
        """Return list of failing checks on current translation."""
        result = TranslationChecklist()

        # All strings
        result.add(self.stats, "all", "")

        result.add_if(
            self.stats, "readonly", "primary" if self.enable_review else "success"
        )

        if not self.is_readonly:
            if self.enable_review:
                result.add_if(self.stats, "approved", "primary")

            # Count of translated strings
            result.add_if(self.stats, "translated", "success")

            # To approve
            if self.enable_review:
                result.add_if(self.stats, "unapproved", "success")

                # Approved with suggestions
                result.add_if(self.stats, "approved_suggestions", "primary")

            # Unfinished strings
            result.add_if(self.stats, "todo", "")

            # Untranslated strings
            result.add_if(self.stats, "nottranslated", "")

            # Fuzzy strings
            result.add_if(self.stats, "fuzzy", "")

            # Translations with suggestions
            if result.add_if(self.stats, "suggestions", ""):
                result.add_if(self.stats, "nosuggestions", "")

        # All checks
        result.add_if(self.stats, "allchecks", "")

        # Translated strings with checks
        if not self.is_source:
            result.add_if(self.stats, "translated_checks", "")

        # Dismissed checks
        result.add_if(self.stats, "dismissed_checks", "")

        # Process specific checks
        for check in CHECKS:
            check_obj = CHECKS[check]
            result.add_if(self.stats, check_obj.url_id, "")

        # Grab comments
        result.add_if(self.stats, "comments", "")

        # Include labels
        labels = self.component.project.label_set.order_by("name")
        if labels:
            has_label = False
            for label in labels:
                has_label |= result.add_if(
                    self.stats,
                    f"label:{label.name}",
                    f"label label-{label.color}",
                )
            if has_label:
                result.add_if(self.stats, "unlabeled", "")

        return result

    def log_upload_not_found(
        self, not_found_log: list[str], unit: TranslationUnit
    ) -> None:
        not_found_log.append(unit.source)

    def show_upload_not_found(
        self,
        request: AuthenticatedHttpRequest,
        not_found_log: list[str],
        string_limit: int = 8,
    ) -> None:
        count = len(not_found_log)

        strings = format_html_join_comma(
            gettext("“{}”"), ((string,) for string in not_found_log[:string_limit])
        )
        if count > string_limit:
            strings = format_html_join_comma("{}", [(strings,), (gettext("…"),)])

        messages.warning(
            request,
            format_html(
                "{} {}",
                ngettext(
                    "Could not find %d string:", "Could not find %d strings:", count
                )
                % count,
                strings,
            ),
            fail_silently=True,
        )

    def merge_translations(
        self,
        request: AuthenticatedHttpRequest,
        author: User,
        store2: TranslationFormat,
        conflicts: Literal["", "replace-approved", "replace-translated"],
        method: Literal["fuzzy", "approve", "translate"],
        fuzzy: Literal["", "process", "approve"],
    ):
        """
        Merge translation unit wise.

        Needed for template based translations to add new strings.
        """
        skipped = 0
        accepted = 0
        add_fuzzy = method == "fuzzy"
        add_approve = method == "approve"
        not_found_log: list[str] = []

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

        unit_set = self.unit_set.select_for_update()

        for set_fuzzy, unit2 in store2.iterate_merge(fuzzy):
            try:
                unit = unit_set.get_unit(unit2)
            except Unit.DoesNotExist:
                self.log_upload_not_found(not_found_log, unit2)
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

            unit.translate(
                request.user,
                split_plural(unit2.target),
                state,
                change_action=ActionEvents.UPLOAD,
                propagate=propagate,
                author=author,
                request=request,
            )

        if accepted > 0:
            self.invalidate_cache()
            request.user.profile.increase_count("translated", accepted)

        if not_found_log:
            self.show_upload_not_found(request, not_found_log)

        return (len(not_found_log), skipped, accepted, len(store2.content_units))

    def merge_suggestions(
        self, request: AuthenticatedHttpRequest, author: User, store, fuzzy
    ):
        """Merge content of translate-toolkit store as a suggestions."""
        skipped = 0
        accepted = 0
        not_found_log: list[str] = []

        unit_set = self.unit_set.all()

        for _unused, unit in store.iterate_merge(fuzzy):
            # Grab database unit
            try:
                dbunit = unit_set.get_unit(unit)
            except Unit.DoesNotExist:
                self.log_upload_not_found(not_found_log, unit)
                continue

            # Add suggestion
            current_target = dbunit.get_target_plurals()
            new_target = unit.target
            if isinstance(new_target, str):
                new_target = [new_target]
            if current_target != new_target and not dbunit.readonly:
                if Suggestion.objects.add(
                    dbunit,
                    new_target,
                    request,
                    raise_exception=False,
                    user=author,
                ):
                    accepted += 1
                else:
                    skipped += 1
            else:
                skipped += 1

        # Update suggestion count
        if accepted > 0:
            self.invalidate_cache()

        if not_found_log:
            self.show_upload_not_found(request, not_found_log)

        return (len(not_found_log), skipped, accepted, len(store.content_units))

    def drop_store_cache(self) -> None:
        if "store" in self.__dict__:
            del self.__dict__["store"]
        if self.is_source:
            self.component.drop_template_store_cache()

    def handle_upload_store_change(
        self,
        request: AuthenticatedHttpRequest,
        author: User,
        change_action: ActionEvents,
    ) -> None:
        component = self.component
        if not component.repository.needs_commit(self.filenames):
            return

        self.create_unit_change_action = ActionEvents.NEW_UNIT_UPLOAD
        self.update_unit_change_action = ActionEvents.STRING_UPLOAD_UPDATE

        previous_revision = component.repository.last_revision
        self.drop_store_cache()

        self.git_commit(
            author,
            author=author.get_author_name(),
            store_hash=False,
            signals=False,
        )

        self.handle_store_change(
            request, author, previous_revision, change=change_action
        )
        # Emit signals later to avoid cleanup add-on to store translation
        # revision before parsing
        component.send_post_commit_signal()

        self.create_unit_change_action = ActionEvents.NEW_UNIT_REPO
        self.update_unit_change_action = ActionEvents.STRING_REPO_UPDATE

    def handle_source(
        self, request: AuthenticatedHttpRequest, author: User, fileobj: BinaryIO
    ) -> UploadResult:
        """Replace source translations with uploaded one."""
        from weblate.addons.gettext import GettextCustomizeAddon, MsgmergeAddon

        component = self.component
        filenames = []
        with component.repository.lock:
            # Commit pending changes
            try:
                component.commit_pending("source update", author)
            except Exception as error:
                raise FailedCommitError(
                    gettext("Could not commit pending changes: %s")
                    % str(error).replace(self.component.full_path, "")
                ) from error

            # Create actual file with the uploaded content
            with tempfile.NamedTemporaryFile(
                prefix="weblate-upload", dir=self.component.full_path, delete=False
            ) as temp:
                temp.write(fileobj.read())

            try:
                # Prepare msgmerge args based on add-ons (if configured)
                if addon := component.get_addon(MsgmergeAddon.name):
                    args = addon.addon.get_msgmerge_args(component)
                else:
                    args = ["--previous"]
                    if addon := component.get_addon(GettextCustomizeAddon.name):
                        args.extend(addon.addon.get_msgmerge_args(component))

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
            self.handle_upload_store_change(
                request, author, change_action=ActionEvents.SOURCE_UPLOAD
            )
        return (0, 0, self.unit_set.count(), self.unit_set.count())

    def handle_replace(
        self, request: AuthenticatedHttpRequest, author: User, fileobj: BinaryIO
    ) -> UploadResult:
        """Replace file content with uploaded one."""
        filecopy = fileobj.read()
        fileobj.close()
        fileobj = NamedBytesIO(fileobj.name, filecopy)
        self.unit_set.select_for_update()
        with self.component.repository.lock:
            try:
                if self.is_source:
                    self.component.commit_pending("replace file", author)
                else:
                    self.commit_pending("replace file", author)
            except Exception as error:
                raise FailedCommitError(
                    gettext("Could not commit pending changes: %s")
                    % str(error).replace(self.component.full_path, "")
                ) from error
            # This will throw an exception in case of error
            store2 = self.load_store(fileobj)
            store2.check_valid()

            # Actually replace file content
            self.component.file_format_cls.save_atomic(
                self.get_filename(), lambda handle: handle.write(filecopy)
            )

            # Commit to VCS
            self.handle_upload_store_change(
                request, author, change_action=ActionEvents.REPLACE_UPLOAD
            )

        return (0, 0, self.unit_set.count(), len(store2.content_units))

    def handle_add_upload(
        self,
        request: AuthenticatedHttpRequest,
        author: User,
        store: TranslationFormat,
        fuzzy: Literal["", "process", "approve"] = "",
    ) -> UploadResult:
        component = self.component
        has_template = component.has_template()
        skipped = 0
        accepted = 0
        component.start_batched_checks()
        existing: set[str] | set[tuple[str, str]]
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
                state=STATE_READONLY if unit.is_readonly() else None,
            )
            existing.add(idkey)
            accepted += 1
        self.store_update_changes()
        component.invalidate_cache()
        if component.needs_variants_update:
            component.update_variants()
        component.schedule_sync_terminology()
        component.update_source_checks()
        component.run_batched_checks()
        component_post_update.send(sender=self.__class__, component=component)
        return (0, skipped, accepted, len(store.content_units))

    def load_uploaded_file(
        self,
        request: AuthenticatedHttpRequest,
        fileobj: BinaryIO,
        method: Literal["fuzzy", "approve", "translate"],
    ) -> TranslationFormat:
        component = self.component

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
                ) from error

        # Load backend file
        if method == "add" and self.is_template:
            template_store = try_load(
                fileobj.name,
                filecopy,
                component.file_format_cls,
                None,
                is_template=True,
            )
            if isinstance(template_store, component.file_format_cls):
                store_post_load.send(
                    sender=self.__class__, translation=self, store=template_store
                )
        else:
            template_store = component.template_store
        store = try_load(
            fileobj.name,
            filecopy,
            component.file_format_cls,
            template_store,
        )
        if isinstance(store, component.file_format_cls):
            store_post_load.send(sender=self.__class__, translation=self, store=store)

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
        return store

    @transaction.atomic
    def handle_upload(
        self,
        request: AuthenticatedHttpRequest,
        fileobj: BinaryIO,
        conflicts: Literal["", "replace-approved", "replace-translated"],
        author_name: str | None = None,
        author_email: str | None = None,
        method: Literal["fuzzy", "approve", "translate"] = "translate",
        fuzzy: Literal["", "process", "approve"] = "",
    ) -> UploadResult:
        """Top level handler for file uploads."""
        from weblate.auth.models import User

        component = self.component

        # Get User object for author
        author = User.objects.get_author_by_email(
            author_name, author_email, request.user, request
        )
        result: UploadResult

        if method == "replace":
            result = self.handle_replace(request, author, fileobj)

        elif method == "source":
            result = self.handle_source(request, author, fileobj)
        else:
            store = self.load_uploaded_file(request, fileobj, method)

            if method in {"translate", "fuzzy", "approve"}:
                # Merge on units level
                result = self.merge_translations(
                    request, author, store, conflicts, method, fuzzy
                )
            elif method == "add":
                with component.lock:
                    result = self.handle_add_upload(request, author, store, fuzzy=fuzzy)
            else:
                # Add as suggestions
                result = self.merge_suggestions(request, author, store, fuzzy)

        self.change_set.create(
            action=ActionEvents.FILE_UPLOAD,
            user=request.user,
            author=author,
            details={
                "method": method,
                "not_found": result[0],
                "skipped": result[1],
                "accepted": result[2],
                "total": result[3],
            },
        )

        return result

    def _invalidate_triger(self) -> None:
        self._invalidate_scheduled = False
        self.stats.update_stats()
        self.component.invalidate_glossary_cache()

    def invalidate_cache(self) -> None:
        """Invalidate any cached stats."""
        # Invalidate summary stats
        if self._invalidate_scheduled:
            return
        self._invalidate_scheduled = True
        transaction.on_commit(self._invalidate_triger)

    def detect_completed_translation(self, change: Change, old_translated: int) -> None:
        translated = self.stats.translated
        if old_translated < translated and translated == self.stats.all:
            self.change_set.create(
                action=ActionEvents.COMPLETE,
                user=change.user,
                author=change.author,
            )

            # check if component is fully translated
            component = self.component
            if component.stats.translated == component.stats.all:
                self.component.change_set.create(
                    action=ActionEvents.COMPLETED_COMPONENT,
                    user=change.user,
                    author=change.author,
                )

    @property
    def keys_cache_key(self) -> str:
        return f"translation-keys-{self.pk}"

    def invalidate_keys(self) -> None:
        cache.delete(self.keys_cache_key)

    def get_export_url(self):
        """Return URL of exported git repository."""
        return self.component.get_export_url()

    def remove(self, user: User) -> None:
        """Remove translation from the Database and VCS."""
        from weblate.glossary.tasks import cleanup_stale_glossaries

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
        self.delete()
        transaction.on_commit(self.stats.update_parents)
        transaction.on_commit(self.component.schedule_update_checks)

        # Record change
        self.component.change_set.create(
            action=ActionEvents.REMOVE_TRANSLATION,
            target=self.filename,
            user=user,
            author=user,
        )
        if not self.component.is_glossary:
            cleanup_stale_glossaries.delay_on_commit(self.component.project.id)

    def handle_store_change(
        self,
        request: AuthenticatedHttpRequest | None,
        user: User,
        previous_revision: str,
        change=None,
    ) -> None:
        self.drop_store_cache()
        # Explicit stats invalidation is needed here as the unit removal in
        # delete_unit might do changes in the database only and not touch the files
        # for pending new units
        if self.is_source:
            self.component.create_translations(
                request=request, change=change, run_async=True
            )
            self.component.invalidate_cache()
        else:
            self.check_sync(request=request, change=change)
            self.invalidate_cache()
        # Trigger post-update signal
        self.component.trigger_post_update(previous_revision, False)

    def get_store_change_translations(self) -> list[Translation]:
        component = self.component
        result: list[Translation] = []
        if self.is_source:
            result.extend(component.translation_set.exclude(id=self.id))
        # Source is always at the end
        result.append(self)
        return result

    @transaction.atomic
    def add_unit(  # noqa: C901,PLR0914,PLR0915,PLR0912
        self,
        request: AuthenticatedHttpRequest | None,
        context: str,
        source: str | list[str],
        target: str | list[str] | None = None,
        *,
        extra_flags: str = "",
        explanation: str = "",
        auto_context: bool = False,
        is_batch_update: bool = False,
        skip_existing: bool = False,
        state: StringState | None = None,
        author: User | None = None,
    ):
        if isinstance(source, list):
            source = join_plural(source)

        parsed_flags = Flags(extra_flags)

        user = request.user if request else author
        component = self.component
        add_terminology = False
        if is_plural(source) and not component.file_format_cls.supports_plural:
            msg = "Plurals not supported by format!"
            raise ValueError(msg)

        if self.is_source:
            translations = (
                self,
                *component.translation_set.exclude(id=self.id).select_related(
                    "language"
                ),
            )
        elif component.is_glossary and "terminology" in parsed_flags:
            add_terminology = True
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
            elif add_terminology and translation != self:
                current_target = ""
            else:
                current_target = target
            if current_target is None:
                current_target = ""
            # Wipe target for untranslatable strings
            if component.is_glossary and "read-only" in parsed_flags:
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
                if "read-only" in translation.all_flags or (
                    component.is_glossary and "read-only" in parsed_flags
                ):
                    unit_state = STATE_READONLY
                elif state is None:
                    unit_state = STATE_TRANSLATED if has_translation else STATE_EMPTY
                elif has_translation and state == STATE_EMPTY:
                    unit_state = STATE_TRANSLATED
                elif not has_translation and state != STATE_EMPTY:
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
                                author=author or user,
                                change_action=ActionEvents.NEW_UNIT,
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
                component._sources[id_hash] = unit  # noqa: SLF001
            if translation == self:
                result = unit
            unit_ids.append(unit.pk)

        if changes:
            if is_batch_update:
                self.update_changes.extend(changes)
            else:
                Change.objects.bulk_create(changes)

        if not is_batch_update:
            if self.component.needs_variants_update:
                component.update_variants(
                    updated_units=Unit.objects.filter(pk__in=unit_ids)
                )
            component.invalidate_cache()
            component_post_update.send(sender=self.__class__, component=component)
        return result

    def notify_deletion(self, unit, user: User) -> None:
        self.change_set.create(
            action=ActionEvents.STRING_REMOVE,
            user=user,
            target=unit.target,
            details={
                "source": unit.source,
                "target": unit.target,
            },
        )

    @transaction.atomic
    def delete_unit(self, request: AuthenticatedHttpRequest | None, unit: Unit) -> None:
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
                    translation_unit = translation.unit_set.select_for_update().get(
                        id_hash=unit.id_hash
                    )
                except ObjectDoesNotExist:
                    continue
                # Delete the removed unit from the database
                cleanup_variants |= translation_unit.variant_id is not None
                translation_unit.delete()
                translation.notify_deletion(translation_unit, user)
                # Skip file processing on source language without a storage
                if not translation.filename:
                    continue
                # Does unit exist in the file?
                try:
                    pounit, needs_add = translation.store.find_unit(
                        unit.context, unit.source
                    )
                except UnitNotFoundError:
                    needs_add = True
                if not needs_add:
                    # Commit changed file
                    extra_files = translation.store.remove_unit(pounit.unit)
                    translation.addon_commit_files.extend(extra_files)
                    translation.drop_store_cache()
                    translation.git_commit(
                        user, user.get_author_name(), store_hash=False
                    )
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

            try:
                alert = self.component.alert_set.get(name="DuplicateString")
            except ObjectDoesNotExist:
                pass
            else:
                occurrences = [
                    item
                    for item in alert.details["occurrences"]
                    if unit.pk != item["unit_pk"]
                ]
                if not occurrences:
                    alert.delete()
                elif occurrences != alert.details["occurrences"]:
                    alert.details["occurrences"] = occurrences
                    alert.save(update_fields=["details"])

            self.handle_store_change(request, user, previous_revision)

    @transaction.atomic
    def sync_terminology(self) -> None:
        from weblate.auth.models import User

        if not self.is_source or not self.component.manage_units:
            return
        expected_count = self.component.translation_set.count()
        author: User | None = None
        for source in self.component.get_all_sources():
            # Is the string a terminology
            if "terminology" not in source.all_flags:
                continue
            if source.unit_set.count() == expected_count:
                continue
            if author is None:
                author = User.objects.get_or_create_bot(
                    scope="glossary", username="sync", verbose="Glossary sync"
                )
            # Add unit
            self.add_unit(
                None,
                source.context,
                source.get_source_plurals(),
                "",
                is_batch_update=True,
                skip_existing=True,
                author=author,
            )
        self.store_update_changes()

    def validate_new_unit_data(
        self,
        context: str,
        source: str | list[str],
        target: str | list[str] | None = None,
        auto_context: bool = False,
        extra_flags: str | None = None,
        explanation: str = "",
        state: int | None = None,
        skip_existing: bool = False,
    ) -> None:
        component = self.component
        extra = {}
        if isinstance(source, str):
            source = [source]
        if len(source) > 1 and not component.file_format_cls.supports_plural:
            raise ValidationError(
                gettext("Plurals are not supported by the file format!")
            )
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
            component.file_format_cls.validate_context(context)
        if not component.has_template():
            extra["source"] = join_plural(source)
        if not auto_context and self.unit_set.filter(context=context, **extra).exists():
            raise ValidationError(gettext("This string seems to already exist."))
        # Avoid using source translations without a filename
        if not self.filename:
            try:
                translation = component.translation_set.exclude(pk=self.pk)[0]
            except IndexError as error:
                raise ValidationError(
                    gettext("Failed adding string, no translation found.")
                ) from error
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

    def get_source_plurals(self):
        """Return blank source fields for pluralized new string."""
        return [""] * self.plural.number

    def can_be_deleted(self) -> bool:
        """
        Check if a glossary can be deleted.

        It is possible to delete a glossary if:
        - it has no translations
        - it is managed by Weblate (i.e. repo == 'local:')
        """
        return self.stats.translated == 0 and self.component.repo == "local:"

    def get_glossaries(self) -> TranslationQuerySet:
        return (
            Translation.objects.filter(
                component__in=self.component.project.glossaries, language=self.language
            )
            .prefetch()
            .order()
        )


class GhostTranslation:
    """Ghost translation object used to show missing translations."""

    is_ghost = True

    def __init__(self, component, language) -> None:
        self.component = component
        self.language = language
        self.stats = GhostStats(component.source_translation.stats)
        self.pk = self.stats.pk
        self.is_source = False

    def __str__(self) -> str:
        return f"{self.component} — {self.language}"

    def get_absolute_url(self) -> str:
        return ""
