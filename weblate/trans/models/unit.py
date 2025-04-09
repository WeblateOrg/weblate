# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import operator
import re
from functools import partial, reduce
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import sentry_sdk
from django.conf import settings
from django.core.cache import cache
from django.db import Error as DjangoDatabaseError
from django.db import models, transaction
from django.db.models import Count, Max, Q, Sum, Value
from django.db.models.functions import MD5, Length, Lower
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy, ngettext
from pyparsing import ParseException

from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS, Check
from weblate.formats.helpers import CONTROLCHARS
from weblate.memory.tasks import handle_unit_translation_change
from weblate.memory.utils import is_valid_memory_entry
from weblate.trans.actions import ActionEvents
from weblate.trans.autofixes import fix_target
from weblate.trans.mixins import LoggerMixin
from weblate.trans.models.change import Change
from weblate.trans.models.comment import Comment
from weblate.trans.models.suggestion import Suggestion
from weblate.trans.models.variant import Variant
from weblate.trans.signals import unit_pre_create
from weblate.trans.util import (
    count_words,
    get_distinct_translations,
    is_plural,
    is_unused_string,
    join_plural,
    split_plural,
)
from weblate.trans.validators import validate_check_flags
from weblate.utils import messages
from weblate.utils.db import using_postgresql, verify_in_transaction
from weblate.utils.errors import report_error
from weblate.utils.hash import calculate_hash, hash_to_checksum
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
    StringState,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable
    from datetime import datetime

    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.formats.base import TranslationUnit
    from weblate.machinery.base import UnitMemoryResultDict

SIMPLE_FILTERS: dict[str, dict[str, Any]] = {
    "fuzzy": {"state": STATE_FUZZY},
    "approved": {"state": STATE_APPROVED},
    "approved_suggestions": {"state": STATE_APPROVED, "suggestion__isnull": False},
    "unapproved": {"state": STATE_TRANSLATED},
    "todo": {"state__lt": STATE_TRANSLATED},
    "nottranslated": {"state": STATE_EMPTY},
    "translated": {"state__gte": STATE_TRANSLATED},
    "suggestions": {"suggestion__isnull": False},
    "nosuggestions": {"suggestion__isnull": True, "state__lt": STATE_TRANSLATED},
    "comments": {"comment__resolved": False},
    "allchecks": {"check__ignore": False},
}

NEWLINES = re.compile(r"\r\n|\r|\n")


class UnitQuerySet(models.QuerySet):
    def filter_type(self, rqtype):
        """Filter based on unit state or failed checks."""
        if rqtype in SIMPLE_FILTERS:
            return self.filter(**SIMPLE_FILTERS[rqtype])
        if rqtype.startswith("check:"):
            check_id = rqtype[6:]
            if check_id not in CHECKS:
                msg = f"Unknown check: {check_id}"
                raise ValueError(msg)
            return self.filter(check__name=check_id, check__dismissed=False)
        if rqtype.startswith("label:"):
            return self.filter(labels__name=rqtype[6:])
        if rqtype == "all":
            return self.all()
        msg = f"Unknown filter: {rqtype}"
        raise ValueError(msg)

    def prefetch(self):
        from weblate.trans.models import Component

        return self.prefetch_related(
            "translation",
            "translation__language",
            "translation__plural",
            models.Prefetch(
                "translation__component", queryset=Component.objects.defer_huge()
            ),
            "translation__component__category",
            "translation__component__category__project",
            "translation__component__category__category",
            "translation__component__category__category__project",
            "translation__component__category__category__category",
            "translation__component__category__category__category__project",
            "translation__component__project",
            "translation__component__source_language",
        )

    def prefetch_source(self):
        from weblate.trans.models import Component

        return self.prefetch_related(
            "source_unit",
            "source_unit__translation",
            "source_unit__translation__language",
            "source_unit__translation__plural",
            models.Prefetch(
                "source_unit__translation__component",
                queryset=Component.objects.defer_huge(),
            ),
            "source_unit__translation__component__source_language",
            "source_unit__translation__component__project",
        )

    def fill_in_source_translation(self):
        """
        Inject source translation intro component from the source unit.

        This materializes the query.

        This assumes prefetch_source() was called before on the query.
        """
        for unit in self:
            unit.translation.component.source_translation = unit.source_unit.translation
        return self

    def prefetch_all_checks(self):
        return self.prefetch_related(
            models.Prefetch(
                "check_set",
                to_attr="all_checks",
            ),
        )

    def count_screenshots(self):
        return self.annotate(Count("screenshots"))

    def prefetch_full(self):
        return (
            self.prefetch_all_checks()
            .prefetch_source()
            .prefetch_related(
                "labels",
                models.Prefetch(
                    "suggestion_set",
                    queryset=Suggestion.objects.order(),
                    to_attr="suggestions",
                ),
                models.Prefetch(
                    "comment_set",
                    queryset=Comment.objects.filter(resolved=False),
                    to_attr="unresolved_comments",
                ),
            )
        )

    def prefetch_bulk(self):
        """Prefetch useful for bulk editing."""
        return self.prefetch_full().prefetch_related("defined_variants")

    def prefetch_recent_content_changes(self):
        """
        Prefetch recent content changes.

        This is used in commit pending, where we need this
        for all pending units.
        """
        return self.prefetch_related(
            models.Prefetch(
                "change_set",
                queryset=Change.objects.content().order().prefetch_related("author"),
                to_attr="recent_content_changes",
            )
        )

    def search(self, query, **context) -> UnitQuerySet:
        """High level wrapper for searching."""
        from weblate.utils.search import parse_query

        result = self.filter(parse_query(query, **context))
        return result.distinct()

    def same(self, unit: Unit, exclude: bool = True) -> UnitQuerySet:
        """Get units with same source within same project."""
        translation = unit.translation
        component = translation.component
        result = self.filter(
            source__lower__md5=MD5(Lower(Value(unit.source))),
            context__lower__md5=MD5(Lower(Value(unit.context))),
            source=unit.source,
            context=unit.context,
            translation__component__project_id=component.project_id,
            translation__language_id=translation.language_id,
            translation__component__source_language_id=component.source_language_id,
        )
        if exclude:
            result = result.exclude(pk=unit.id)
        return result

    def same_target(self, unit: Unit, target: str | None = None) -> UnitQuerySet:
        if target is None:
            target = unit.target
        if not target or not any(split_plural(target)):
            return self.none()
        translation = unit.translation
        component = translation.component
        result = self.filter(
            target__lower__md5=MD5(Lower(Value(target))),
            target=target,
            translation__component__project_id=component.project_id,
            translation__language_id=translation.language_id,
            translation__component__source_language_id=component.source_language_id,
            translation__component__allow_translation_propagation=True,
            translation__plural_id=translation.plural_id,
            translation__plural__number__gt=1,
        ).exclude(source=unit.source)
        if not unit.translation.language.is_case_sensitive():
            result = result.exclude(source__lower__md5=MD5(Lower(Value(unit.source))))
        return result

    def order_by_request(self, form_data, obj) -> UnitQuerySet:
        sort_list_request = form_data.get("sort_by", "").split(",")
        available_sort_choices = [
            "priority",
            "position",
            "context",
            "num_words",
            "labels",
            "timestamp",
            "last_updated",
            "source",
            "target",
            "location",
        ]
        countable_sort_choices: dict[str, dict[str, Any]] = {
            "num_comments": {"order_by": "comment__count", "filter": None},
            "num_failing_checks": {
                "order_by": "check__count",
                "filter": Q(check__dismissed=False),
            },
        }
        sort_list = []
        for choice in sort_list_request:
            unsigned_choice = choice.replace("-", "")
            if unsigned_choice in countable_sort_choices:
                return self.order_by_count(
                    choice.replace(
                        unsigned_choice,
                        countable_sort_choices[unsigned_choice]["order_by"],
                    ),
                    countable_sort_choices[unsigned_choice]["filter"],
                )
            if unsigned_choice in available_sort_choices:
                if unsigned_choice == "labels":
                    choice = choice.replace("labels", "max_labels_name")
                sort_list.append(choice)
        if not sort_list:
            if hasattr(obj, "component") and obj.component.is_glossary:
                sort_list = ["source"]
            else:
                sort_list = ["-priority", "position"]
        if "max_labels_name" in sort_list or "-max_labels_name" in sort_list:
            return self.annotate(max_labels_name=Max("labels__name")).order_by(
                *sort_list
            )
        return self.order_by(*sort_list)

    def order_by_count(self, choice: str, count_filter) -> UnitQuerySet:
        model = choice.split("__")[0].replace("-", "")
        annotation_name = choice.replace("-", "")
        return self.annotate(
            **{annotation_name: Count(model, filter=count_filter)}
        ).order_by(choice)

    @cached_property
    def source_context_lookup(self):
        return {(unit.context, unit.source): unit for unit in self}

    @cached_property
    def source_lookup(self) -> dict[str, Unit]:
        return {unit.source: unit for unit in self}

    def get_unit(self, ttunit: TranslationUnit) -> Unit:
        """
        Find unit matching translate-toolkit unit.

        This is used for import, so kind of fuzzy matching is expected.
        """
        source = ttunit.source
        context = ttunit.context

        contexts = [context]
        # Special case for XLIFF, strip file
        if "///" in context:
            contexts.append(context.split("///", 1)[1])

        # Try with empty context if exact context is not found, useful for importing
        # monolingual to bilingual
        if context:
            contexts.append("")

        # Lookups based on context
        for match in contexts:
            try:
                return self.source_context_lookup[match, source]
            except KeyError:
                continue

        # Fallback to source string only lookup
        try:
            return self.source_lookup[source]
        except KeyError:
            msg = "No matching unit found!"
            raise Unit.DoesNotExist(msg) from None

    def order(self):
        return self.order_by("-priority", "position")

    def filter_access(self, user: User):
        result = self
        if user.needs_project_filter:
            result = result.filter(
                translation__component__project__in=user.allowed_projects
            )
        if user.needs_component_restrictions_filter:
            result = result.filter(
                Q(translation__component__restricted=False)
                | Q(translation__component_id__in=user.component_permissions)
            )
        return result

    def get_ordered(self, ids):
        """Return list of units ordered by ID."""
        return sorted(self.filter(id__in=ids), key=lambda unit: ids.index(unit.id))

    def select_for_update(self) -> UnitQuerySet:  # type: ignore[override]
        if using_postgresql():
            # Use weaker locking and limit locking to Unit table only
            return super().select_for_update(no_key=True, of=("self",))
        # Discard any select_related to avoid locking additional tables
        return super().select_for_update().select_related(None)

    def annotate_stats(self):
        return self.annotate(
            strings=Count("pk"), words=Sum("num_words"), chars=Sum(Length("source"))
        )


class LabelsField(models.ManyToManyField):
    def save_form_data(self, instance, data) -> None:
        from weblate.trans.models.label import TRANSLATION_LABELS

        super().save_form_data(instance, data)

        # Delete translation labels when not checked
        new_labels = {label.name for label in data}
        through = getattr(instance, self.attname).through.objects
        for label in TRANSLATION_LABELS:
            if label not in new_labels:
                through.filter(unit__source_unit=instance, label__name=label).delete()


class OldUnit(TypedDict):
    state: StringState
    source: str
    target: str
    context: str
    extra_flags: str
    explanation: str


class Unit(models.Model, LoggerMixin):
    translation = models.ForeignKey(
        "trans.Translation", on_delete=models.deletion.CASCADE, db_index=False
    )
    id_hash = models.BigIntegerField()
    location = models.TextField(default="", blank=True)
    context = models.TextField(default="", blank=True)
    note = models.TextField(default="", blank=True)
    flags = models.TextField(default="", blank=True)
    source = models.TextField()
    previous_source = models.TextField(default="", blank=True)
    target = models.TextField(default="", blank=True)
    state = models.IntegerField(default=STATE_EMPTY, choices=StringState.choices)
    original_state = models.IntegerField(
        default=STATE_EMPTY, choices=StringState.choices
    )
    details = models.JSONField(default=dict)

    position = models.IntegerField()

    num_words = models.IntegerField(default=0)

    priority = models.IntegerField(default=100)

    pending = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    extra_flags = models.TextField(
        verbose_name=gettext_lazy("Translation flags"),
        default="",
        help_text=gettext_lazy(
            "Additional comma-separated flags to influence Weblate behavior."
        ),
        validators=[validate_check_flags],
        blank=True,
    )
    explanation = models.TextField(
        verbose_name=gettext_lazy("Explanation"),
        default="",
        blank=True,
        help_text=gettext_lazy(
            "Additional explanation to clarify meaning or usage of the string."
        ),
    )
    variant = models.ForeignKey(
        "trans.Variant",
        on_delete=models.deletion.SET_NULL,
        blank=True,
        null=True,
        default=None,
    )
    labels = LabelsField("Label", verbose_name=gettext_lazy("Labels"), blank=True)

    # The type annotation hides that field can be None because
    # save() updates it to non-None immediately.
    source_unit: Unit = models.ForeignKey(
        "trans.Unit", on_delete=models.deletion.CASCADE, blank=True, null=True
    )  # type: ignore[assignment]

    objects = UnitQuerySet.as_manager()

    class Meta:
        app_label = "trans"
        unique_together = [("translation", "id_hash")]
        verbose_name = "string"
        verbose_name_plural = "strings"
        indexes = [
            models.Index(
                MD5(Lower("source")), "translation", name="trans_unit_source_md5"
            ),
            models.Index(
                MD5(Lower("target")), "translation", name="trans_unit_target_md5"
            ),
            models.Index(
                MD5(Lower("context")), "translation", name="trans_unit_context_md5"
            ),
            # Partial index for pending field to optimize lookup in translation
            # commit pending method. Full table index performs poorly here because
            # it becomes huge.
            # MySQL/MariaDB does not supports condition and uses full index instead.
            models.Index(
                "translation",
                "pending",
                condition=Q(pending=True),
                name="trans_unit_pending",
            ),
        ]

    def __str__(self) -> str:
        source = self.get_source_plurals()[0]
        if self.translation.is_template:
            name = self.context
        elif self.context:
            name = f"[{self.context}] {source}"
        else:
            name = source
        return f"{self.pk}: {name}"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.is_batch_update = False
        self.source_updated = False
        self.check_cache: dict[str, Any] = {}
        self.trigger_update_variants = True
        self.fixups: list[str] = []
        # Data for machinery integration
        self.machinery: UnitMemoryResultDict = {}
        # PluralMapper integration
        self.plural_map: list[str] = []
        # Data for glossary integration
        self.glossary_terms: list[Unit] | None = None
        self.glossary_positions: tuple[tuple[int, int], ...] = ()
        # Project backup integration
        self.import_data: dict[str, Any] = {}
        # Store original attributes for change tracking
        self.old_unit: OldUnit
        # Avoid loading self-referencing source unit from the database
        # Skip this when deferred fields are present to avoid database access
        if (
            self.id
            and not self.get_deferred_fields()
            and self.source_unit_id == self.id
        ):
            self.source_unit = self
        if "state" in self.__dict__ and "source" in self.__dict__:
            # Avoid storing if .only() was used to fetch the query (eg. in stats)
            self.store_old_unit(self)

    def save(  # type: ignore[override]
        self,
        *,
        same_content: bool = False,
        run_checks: bool = True,
        force_propagate_checks: bool = False,
        force_insert: bool = False,
        force_update: bool = False,
        only_save: bool = False,
        sync_terminology: bool = True,
        using=None,
        update_fields: list[str] | None = None,
    ) -> None:
        """
        Save the unit.

        Wrapper around save to run checks or update fulltext.
        """
        # Store number of words
        if not same_content or not self.num_words:
            self.num_words = count_words(
                self.source, self.translation.component.source_language
            )
            if update_fields and "num_words" not in update_fields:
                update_fields.append("num_words")

        # Update last_updated timestamp
        if update_fields and "last_updated" not in update_fields:
            update_fields.append("last_updated")

        # Actually save the unit
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )
        if only_save:
            return

        # Set source_unit for source units, this needs to be done after
        # having a primary key
        if self.is_source and not self.source_unit:
            self.source_unit = self
            # Avoid using save() for recursion
            Unit.objects.filter(pk=self.pk).update(source_unit=self)

        # Update checks if content or fuzzy flag has changed
        if run_checks:
            self.run_checks(force_propagate=force_propagate_checks)
        if self.is_source:
            self.source_unit_save()

        # Update manual variants
        if (
            self.old_unit["extra_flags"] != self.extra_flags
            or self.context != self.old_unit["context"]
            or force_insert
        ):
            self.update_variants()

        # Update terminology
        if sync_terminology:
            self.sync_terminology()

    def get_absolute_url(self) -> str:
        return f"{self.translation.get_translate_url()}?checksum={self.checksum}"

    def get_url_path(self):
        return (*self.translation.get_url_path(), str(self.pk))

    def invalidate_checks_cache(self) -> None:
        self.check_cache = {}
        for key in ["propagated_units"]:
            if key in self.__dict__:
                del self.__dict__[key]

    def store_old_unit(self, unit) -> None:
        self.old_unit = {
            "state": unit.state,
            "source": unit.source,
            "target": unit.target,
            "context": unit.context,
            "extra_flags": unit.extra_flags,
            "explanation": unit.explanation,
        }

    @property
    def approved(self) -> bool:
        return self.state == STATE_APPROVED

    @property
    def translated(self) -> bool:
        return self.state >= STATE_TRANSLATED

    @property
    def readonly(self) -> bool:
        return self.state == STATE_READONLY

    @property
    def fuzzy(self) -> bool:
        return self.state == STATE_FUZZY

    @property
    def has_failing_check(self) -> bool:
        return bool(self.active_checks)

    @property
    def has_comment(self) -> bool:
        # Use bool here as unresolved_comments might be list
        # or a queryset (from prefetch)
        return bool(self.unresolved_comments)

    @property
    def has_suggestion(self) -> bool:
        return bool(self.suggestions)

    def source_unit_save(self) -> None:
        # Run checks, update state and priority if flags changed
        # or running bulk edit
        if (
            self.old_unit["extra_flags"] != self.extra_flags
            or self.state != self.old_unit["state"]
        ):
            # We can not exclude current unit here as we need to trigger
            # the updates below
            for unit in self.unit_set.select_for_update().prefetch().prefetch_bulk():
                # Share component instance for locking and possible bulk updates
                unit.translation.component = self.translation.component
                unit.update_state()
                unit.update_priority()
                unit.run_checks()
            if not self.is_batch_update:
                self.translation.component.invalidate_cache()

    def sync_terminology(self) -> None:
        try:
            unit_flags = Flags(self.flags)
        except ParseException:
            unit_flags = None
        new_flags = Flags(self.extra_flags, unit_flags)

        if "terminology" in new_flags:
            self.translation.component.schedule_sync_terminology()

    def update_variants(self) -> None:
        variants = self.defined_variants.all()
        component = self.translation.component
        flags = self.all_flags
        new_variant = None
        remove = False

        if not flags.has_value("variant"):
            remove = bool(variants)
        else:
            new_variant = flags.get_value("variant")
            if any(variant.key != new_variant for variant in variants):
                remove = True

        # Delete stale variant
        if remove:
            for variant in variants:
                variant.defining_units.remove(self)
                if variant.defining_units.count() == 0:
                    variant.delete()
                else:
                    variant.unit_set.filter(id_hash=self.id_hash).update(variant=None)

        # Add new variant
        if new_variant:
            variant = Variant.objects.get_or_create(
                key=new_variant, component=component
            )[0]
            variant.defining_units.add(self)

        # Update variant links
        if (
            remove
            or new_variant
            or (
                component.variant_regex
                and re.findall(component.variant_regex, self.context)
            )
        ):
            if self.trigger_update_variants:
                component.update_variants()
            else:
                component.needs_variants_update = True

    def get_unit_state(self, unit, flags: str | None, string_changed: bool = False):
        """Calculate translated and fuzzy status."""
        # Read-only from the file format
        if unit.is_readonly():
            return STATE_READONLY

        if flags is not None:
            # Read-only from the source
            if (
                not self.is_source
                and self.source_unit.state < STATE_TRANSLATED
                and self.translation.component.intermediate
            ):
                return STATE_READONLY

            # Read-only from flags
            if "read-only" in self.get_all_flags(flags):
                return STATE_READONLY

        # We need to keep approved/fuzzy state for formats which do not
        # support saving it
        if unit.is_fuzzy(self.fuzzy and not string_changed):
            return STATE_FUZZY

        if not unit.is_translated():
            return STATE_EMPTY

        if (
            unit.is_approved(self.approved and not string_changed)
            and self.translation.enable_review
        ):
            return STATE_APPROVED

        return STATE_TRANSLATED

    @staticmethod
    def check_valid(texts) -> None:
        for text in texts:
            if any(char in text for char in CONTROLCHARS):
                raise ValueError(
                    gettext("String contains control character: %s") % repr(text)
                )

    def update_source_unit(
        self, component, source, context, pos, note, location, flags, explanation
    ) -> None:
        source_unit = component.get_source(
            self.id_hash,
            create={
                "source": source,
                "target": source,
                "context": context,
                "position": pos,
                "note": note,
                "location": location,
                "explanation": explanation,
                "flags": flags,
            },
        )
        same_flags = flags == source_unit.flags
        if (
            not source_unit.source_updated
            and not source_unit.translation.filename
            and (
                pos != source_unit.position
                or location != source_unit.location
                or not same_flags
                or note != source_unit.note
            )
        ):
            source_unit.position = pos
            source_unit.source_updated = True
            source_unit.location = location
            source_unit.explanation = explanation
            source_unit.flags = flags
            source_unit.note = note
            source_unit.save(
                update_fields=["position", "location", "explanation", "flags", "note"],
                same_content=True,
                run_checks=False,
                only_save=same_flags,
            )
        self.source_unit = source_unit

    def update_from_unit(self, unit, pos, created) -> None:  # noqa: C901
        """Update Unit from ttkit unit."""
        translation = self.translation
        component = translation.component
        self.is_batch_update = True
        self.trigger_update_variants = False
        self.source_updated = True
        # Get unit attributes
        try:
            location = unit.locations
            if self.translation.component.file_format_cls.supports_explanation:
                explanation = unit.explanation
                source_explanation = unit.source_explanation
            else:
                explanation = self.explanation
                source_explanation = "" if created else self.source_unit.explanation
            flags = unit.flags
            source = unit.source
            self.check_valid(split_plural(source))
            if not translation.is_template and translation.is_source:
                # Load target from source string for bilingual source translations
                target = source
            else:
                target = unit.target
                self.check_valid(split_plural(target))
            context = unit.context
            self.check_valid([context])
            note = unit.notes
            source_change = previous_source = unit.previous_source
        except DjangoDatabaseError:
            raise
        except Exception as error:
            report_error("Unit update error", project=component.project)
            translation.component.handle_parse_error(error, translation)

        pending = False

        # Ensure we track source string for bilingual, this can not use
        # Unit.is_source as that depends on source_unit attribute, which
        # we set here
        old_source_unit = self.source_unit
        if not translation.is_source:
            self.update_source_unit(
                component,
                source,
                context,
                pos,
                note,
                location,
                flags,
                source_explanation,
            )

        # Has source/target changed
        same_source = source == self.source and context == self.context
        same_target = target == self.target

        # Calculate state
        state = self.get_unit_state(
            unit, flags, string_changed=not same_source or not same_target
        )
        original_state = self.get_unit_state(unit, None)

        # Monolingual files handling (without target change)
        if (
            not created
            and state != STATE_READONLY
            and unit.template is not None
            and same_target
        ):
            if not same_source and state in {STATE_TRANSLATED, STATE_APPROVED}:
                if self.previous_source == source and self.fuzzy:
                    # Source change was reverted
                    source_change = self.source
                    previous_source = ""
                    state = STATE_TRANSLATED
                else:
                    # Store previous source and fuzzy flag for monolingual
                    if not previous_source:
                        source_change = previous_source = self.source
                    state = STATE_FUZZY
                pending = True
            elif (
                self.state == STATE_FUZZY
                and state == STATE_FUZZY
                and not previous_source
            ):
                # Avoid losing previous source of fuzzy strings
                previous_source = self.previous_source

        # Update checks on fuzzy update or on content change
        same_state = state == self.state and flags == self.flags
        same_metadata = (
            location == self.location
            and explanation == self.explanation
            and note == self.note
            and pos == self.position
            and not pending
        )
        same_data = (
            not created
            and same_source
            and same_target
            and same_state
            and original_state == self.original_state
            and flags == self.flags
            and previous_source == self.previous_source
            and self.source_unit == old_source_unit
            and old_source_unit is not None
        )

        # Check if we actually need to change anything
        if same_data and same_metadata:
            return

        # Store updated values
        self.original_state = original_state
        self.position = pos
        self.location = location
        self.explanation = explanation
        self.flags = flags
        self.source = source
        self.target = target
        self.state = state
        self.context = context
        self.note = note
        self.previous_source = previous_source
        self.pending = pending
        self.update_priority(save=False)

        # Metadata update only, these do not trigger any actions in Weblate and
        # are display only
        if same_data and not same_metadata:
            self.save(
                same_content=True,
                only_save=True,
                update_fields=["location", "explanation", "note", "position"],
            )
            return

        # Sanitize number of plurals
        if self.is_plural and not component.file_format_cls.has_multiple_strings:
            self.target = join_plural(self.get_target_plurals())

        if created:
            unit_pre_create.send(sender=self.__class__, unit=self)

        # Save into database
        self.save(
            force_insert=created,
            same_content=same_source and same_target,
            run_checks=not same_source or not same_target or not same_state,
        )
        # Track updated sources for source checks
        if translation.is_template:
            component.updated_sources[self.id] = self
        # Indicate source string change
        if not same_source and source_change:
            translation.update_changes.append(
                self.generate_change(
                    None,
                    None,
                    ActionEvents.SOURCE_CHANGE,
                    check_new=False,
                    old=source_change,
                    target=self.source,
                    save=False,
                )
            )
        # Track VCS change
        if not same_data:
            translation.update_changes.append(
                self.generate_change(
                    user=None,
                    author=None,
                    change_action=translation.create_unit_change_action
                    if created
                    else translation.update_unit_change_action,
                    check_new=False,
                    save=False,
                )
            )

        # Update translation memory if needed
        if created or not same_source or not same_target:
            self.update_translation_memory(needs_user_check=False)

    def update_state(self) -> None:
        """
        Update state based on flags.

        Mark read-only strings:

        * Flagged with 'read-only'
        * Where source string is untranslated
        """
        if "read-only" in self.all_flags or (
            not self.is_source
            and self.source_unit.state < STATE_TRANSLATED
            and self.translation.component.intermediate
        ):
            if not self.readonly:
                self.original_state = self.state
                self.state = STATE_READONLY
                self.save(
                    same_content=True,
                    run_checks=False,
                    update_fields=["state", "original_state"],
                )
        elif self.readonly and self.state != self.original_state:
            self.state = self.original_state
            self.save(same_content=True, run_checks=False, update_fields=["state"])

    def update_priority(self, save: bool = True) -> None:
        if self.all_flags.has_value("priority"):
            priority = self.all_flags.get_value("priority")
        else:
            priority = 100
        if self.priority != priority:
            self.priority = priority
            if save:
                self.save(
                    same_content=True, run_checks=False, update_fields=["priority"]
                )

    @cached_property
    def is_plural(self) -> bool:
        """Check whether message is plural."""
        return is_plural(self.source) or is_plural(self.target)

    @cached_property
    def is_source(self) -> bool:
        return self.source_unit_id is None or self.source_unit_id == self.id

    def get_source_plurals(self) -> list[str]:
        """Return source plurals in array."""
        return split_plural(self.source)

    @cached_property
    def source_string(self) -> str:
        """
        Return a single source string.

        In most cases it's singular with exception of unused singulars
        generated by some frameworks.
        """
        plurals = self.get_source_plurals()
        singular = plurals[0]
        if len(plurals) == 1 or not is_unused_string(singular):
            return singular
        return plurals[1]

    def adjust_plurals(
        self, values: list[str], plurals: int | None = None
    ) -> list[str]:
        if not self.is_plural:
            plurals = 1
        elif plurals is None:
            plurals = self.translation.plural.number

        # Check if we have expected number of them
        if len(values) == plurals:
            return values

        # Pad with empty translations
        while len(values) < plurals:
            values.append("")

        # Delete extra plurals
        while len(values) > plurals:
            del values[-1]

        return values

    def get_target_plurals(self, plurals: int | None = None) -> list[str]:
        """Return target plurals in array."""
        # Split plurals
        ret = split_plural(self.target)

        if not self.translation.component.is_multivalue:
            ret = self.adjust_plurals(ret, plurals=plurals)

        return ret

    def propagate(
        self, user: User | None, change_action=None, author=None, request=None
    ) -> bool:
        """Propagate current translation to all others."""
        from weblate.auth.permissions import PermissionResult

        warnings: list[str] = []

        with sentry_sdk.start_span(op="unit.propagate", name=f"{self.pk}"):
            to_update: list[Unit] = []
            units = self.propagated_units.exclude(
                target=self.target, state=self.state
            ).select_for_update()
            for unit in units:
                if user is not None and not (
                    denied := user.has_perm("unit.edit", unit)
                ):
                    component = unit.translation.component
                    if request and isinstance(denied, PermissionResult):
                        warnings.append(
                            gettext(
                                "String could not be propagated to %(component)s: %(reason)s"
                            )
                            % {"component": component, "reason": denied.reason},
                        )
                    continue

                # Commit any previous pending changes
                unit.commit_if_pending(user)

                # Update unit attributes for the current instance, the database is bulk updated later
                unit.target = self.target
                unit.state = self.state
                unit.pending = True

                to_update.append(unit)

                unit.update_translation_memory(user)

            if warnings:
                if len(warnings) > 10:
                    messages.warning(
                        request,
                        ngettext(
                            "String could not be propagated to %d component.",
                            "String could not be propagated to %d components.",
                            len(warnings),
                        )
                        % len(warnings),
                    )
                else:
                    for warning in warnings:
                        messages.warning(request, warning)
            if not to_update:
                return False

            # Bulk update units
            Unit.objects.filter(pk__in=(unit.pk for unit in to_update)).update(
                target=self.target,
                state=self.state,
                original_state=self.state,
                pending=True,
                last_updated=self.last_updated,
            )

            # Postprocess changes and generate change objects
            changes = [
                unit.post_save(
                    user,
                    user,
                    change_action=ActionEvents.PROPAGATED_EDIT,
                    check_new=False,
                    save=False,
                )
                for unit in to_update
            ]

            # Bulk create changes
            Change.objects.bulk_create(changes)

            # Update user stats
            if user is not None:
                user.profile.increase_count("translated", len(to_update))

            return True

    def commit_if_pending(self, author: User | None) -> None:
        """Commit possible previous changes on this unit."""
        if self.pending:
            change_author = self.get_last_content_change()[0]
            if change_author != author:
                # This intentionally discards user - the translating user
                # has no control on what this does (it can even trigger update
                # of the repo)
                self.translation.commit_pending("pending unit", None)

    def save_backend(
        self,
        user: User | None,
        propagate: bool = True,
        change_action=None,
        author: User | None = None,
        run_checks: bool = True,
        request=None,
    ) -> bool:
        """
        Store unit to backend.

        Optional user parameters defines authorship of a change.

        This should be always called in a transaction with updated unit
        locked for update.
        """
        verify_in_transaction()
        # For case when authorship specified, use user
        author = author or user

        # Commit possible previous changes on this unit
        self.commit_if_pending(author)

        # Propagate to other projects
        # This has to be done before changing source for template
        was_propagated = False
        if propagate:
            was_propagated = self.propagate(
                user, change_action, author=author, request=request
            )

        # Return if there was no change
        # We have to explicitly check for fuzzy flag change on monolingual
        # files, where we handle it ourselves without storing to backend
        if (
            self.old_unit["state"] == self.state
            and self.old_unit["target"] == self.target
            and self.old_unit["explanation"] == self.explanation
            and not was_propagated
        ):
            return False

        update_fields = ["target", "state", "original_state", "pending", "explanation"]
        if self.is_source and not self.translation.component.intermediate:
            self.source = self.target
            update_fields.extend(["source"])

        # Unit is pending for write
        self.pending = True
        # Update translated flag (not fuzzy and at least one translation)
        translation = any(self.get_target_plurals())
        if self.state >= STATE_TRANSLATED and not translation:
            self.state = STATE_EMPTY
        elif self.state == STATE_EMPTY and translation:
            self.state = STATE_TRANSLATED
        self.original_state = self.state

        # Save updated unit to database, skip running checks
        self.save(
            update_fields=update_fields,
            run_checks=run_checks,
            force_propagate_checks=was_propagated,
        )

        # Generate change and process it
        self.post_save(user or author, author, change_action)

        # Update related source strings if working on a template
        if self.translation.is_template and self.old_unit["target"] != self.target:
            self.update_source_units(self.old_unit["target"], user or author, author)

        return True

    def post_save(
        self,
        user: User | None,
        author: User | None,
        change_action: int | None,
        *,
        save: bool = True,
        check_new: bool = True,
    ) -> Change:
        # Generate Change object for this change
        change = self.generate_change(
            user or author, author, change_action, save=save, check_new=check_new
        )

        if change.action not in {
            ActionEvents.UPLOAD,
            ActionEvents.AUTO,
            ActionEvents.BULK_EDIT,
        }:
            old_translated = self.translation.stats.translated

            # Update translation stats
            self.translation.invalidate_cache()

            # Postpone completed translation detection for translated strings
            if self.state >= STATE_TRANSLATED:
                transaction.on_commit(
                    partial(
                        self.translation.detect_completed_translation,
                        change,
                        old_translated,
                    )
                )

            # Update user stats
            if save and change.author and not change.author.is_anonymous:
                change.author.profile.increase_count("translated")
        return change

    def update_source_units(
        self, previous_source: str, user: User | None, author: User | None
    ) -> None:
        """
        Update source for units within same component.

        This is needed when editing template translation for monolingual formats.
        """
        with sentry_sdk.start_span(op="unit.update_source_units", name=f"{self.pk}"):
            changes = []

            # Find relevant units
            for unit in self.unit_set.exclude(id=self.id).prefetch().prefetch_bulk():
                unit.commit_if_pending(author)
                # Update source and number of words
                unit.source = self.target
                unit.num_words = self.num_words
                # Find reverted units
                if (
                    unit.state == STATE_FUZZY
                    and unit.previous_source == self.target
                    and unit.target
                ):
                    # Unset fuzzy on reverted
                    unit.original_state = unit.state = STATE_TRANSLATED
                    unit.pending = True
                    unit.previous_source = ""
                elif (
                    unit.original_state == STATE_FUZZY
                    and unit.previous_source == self.target
                    and unit.target
                ):
                    # Unset fuzzy on reverted
                    unit.original_state = STATE_TRANSLATED
                    unit.previous_source = ""
                elif unit.state >= STATE_TRANSLATED and unit.target:
                    # Set fuzzy on changed
                    unit.original_state = STATE_FUZZY
                    if unit.state < STATE_READONLY:
                        unit.state = STATE_FUZZY
                        unit.pending = True
                    unit.previous_source = previous_source

                # Save unit
                unit.save()
                # Generate change
                changes.append(
                    unit.generate_change(
                        user,
                        author,
                        ActionEvents.SOURCE_CHANGE,
                        check_new=False,
                        old=previous_source,
                        target=self.target,
                        save=False,
                    )
                )
            if changes:
                # Bulk create changes
                Change.objects.bulk_create(changes)
                # Invalidate stats
                self.translation.component.invalidate_cache()

    def generate_change(
        self,
        user: User | None,
        author: User | None,
        change_action: int | None,
        *,
        check_new: bool = True,
        save: bool = True,
        old: str | None = None,
        target: str | None = None,
    ) -> Change:
        """Create Change entry for saving unit."""
        # Notify about new contributor
        if (
            check_new
            and user is not None
            and not user.is_bot
            and not self.translation.change_set.filter(user=user).exists()
        ):
            self.change_set.create(
                unit=self,
                action=ActionEvents.NEW_CONTRIBUTOR,
                user=user,
                author=author,
            )

        # Action type to store
        if change_action is not None:
            action = change_action
        elif self.state == STATE_FUZZY:
            action = ActionEvents.MARKED_EDIT
        elif self.old_unit["state"] >= STATE_FUZZY:
            if self.state == STATE_APPROVED:
                action = ActionEvents.APPROVE
            else:
                action = ActionEvents.CHANGE
        elif self.state == STATE_APPROVED:
            action = ActionEvents.APPROVE
        else:
            action = ActionEvents.NEW

        # Create change object
        change = Change(
            unit=self,
            action=action,
            user=user,
            author=author,
            target=self.target if target is None else target,
            old=self.old_unit["target"] if old is None else old,
            details={
                "state": self.state,
                "old_state": self.old_unit["state"],
                "source": self.source,
            },
        )
        if save:
            change.save(force_insert=True)
        return change

    @cached_property
    def suggestions(self) -> models.QuerySet[Suggestion]:
        """Return all suggestions for this unit."""
        return self.suggestion_set.order()

    @cached_property
    def all_checks(self) -> Iterable[Check]:
        result = self.check_set.all()
        # Force fetching
        list(result)
        return result

    def clear_checks_cache(self) -> None:
        if "all_checks" in self.__dict__:
            del self.__dict__["all_checks"]

    @property
    def all_checks_names(self) -> set[str]:
        return {check.name for check in self.all_checks}

    @property
    def dismissed_checks(self) -> list[Check]:
        return [check for check in self.all_checks if check.dismissed]

    @property
    def active_checks(self) -> list[Check]:
        """Return all active (not ignored) checks for this unit."""
        return [check for check in self.all_checks if not check.dismissed]

    @cached_property
    def all_comments(self) -> models.QuerySet[Comment]:
        """Return list of target comments."""
        if self.is_source:
            # Add all comments on translation on source string comment
            query = Q(unit__source_unit=self)
        else:
            # Add source string comments for translation unit
            query = Q(unit__in=(self, self.source_unit))
        return Comment.objects.filter(query).prefetch_related("unit", "user").order()

    @cached_property
    def unresolved_comments(self) -> list[Comment]:
        return [
            comment
            for comment in self.all_comments
            if not comment.resolved and comment.unit_id == self.id
        ]

    def run_checks(  # noqa: C901
        self, *, force_propagate: bool = False, skip_propagate: bool = False
    ) -> None:
        """Update checks for this unit."""
        src = self.get_source_plurals()
        tgt = self.get_target_plurals()

        old_checks = self.all_checks_names
        create = []

        args: tuple[list[str], Unit] | tuple[list[str], list[str], Unit]
        if self.is_source:
            checks = CHECKS.source
            meth = "check_source"
            args = src, self
        else:
            checks = {} if self.readonly else CHECKS.target
            meth = "check_target"
            args = src, tgt, self
        if self.translation.component.is_glossary:
            checks = CHECKS.glossary
            meth = "check_target"
            args = src, tgt, self

        # Initial propagation setup
        propagation: set[Literal["source", "target"]] = set()
        if force_propagate:
            propagation.add("source")

        # Run all checks
        for check, check_obj in checks.items():
            # Does the check fire?
            if getattr(check_obj, meth)(*args):
                if check in old_checks:
                    # We already have this check
                    old_checks.remove(check)
                    # Propagation is handled later in this method
                else:
                    # Create new check
                    create.append(Check(unit=self, dismissed=False, name=check))
                    if check_obj.propagates and not skip_propagate:
                        propagation.add(check_obj.propagates)

        if create:
            Check.objects.bulk_create(create, batch_size=500, ignore_conflicts=True)

        # Delete no longer failing checks
        if old_checks:
            Check.objects.filter(unit=self, name__in=old_checks).delete()
            if not skip_propagate:
                for check_name in old_checks:
                    try:
                        check_obj = CHECKS[check_name]
                    except KeyError:
                        # Skip disabled/removed checks
                        continue
                    if check_obj.propagates:
                        if check_obj.propagates == "source":
                            propagated_units = self.propagated_units
                            values = set(
                                propagated_units.values_list("target", flat=True)
                            )
                        elif check_obj.propagates == "target":
                            propagated_units = Unit.objects.same_target(
                                self, self.old_unit["target"]
                            )
                            values = set(
                                propagated_units.values_list("source", flat=True)
                            )
                        else:
                            message = f"Unsupported propagation: {check_obj.propagates}"
                            raise ValueError(message)

                        if len(values) == 1:
                            for other in propagated_units:
                                other.check_set.filter(name=check_name).delete()
                                if (
                                    other.translation != self.translation
                                    or other.source != self.source
                                ):
                                    other.translation.invalidate_cache()
                                other.clear_checks_cache()

        # Propagate checks which need it (for example consistency)
        if propagation:
            querymap: dict[Literal["source", "target"], UnitQuerySet] = {
                "source": self.propagated_units,
                "target": Unit.objects.same_target(self),
            }
            propagated_units: UnitQuerySet = reduce(
                operator.or_, (querymap[item] for item in propagation)
            )
            propagated_units = (
                propagated_units.distinct()
                .prefetch_related("source_unit")
                .prefetch_all_checks()
            )

            for unit in propagated_units:
                try:
                    unit.run_checks(force_propagate=False, skip_propagate=True)
                except Unit.DoesNotExist:
                    # This can happen in some corner cases like changing
                    # source language of a project - the source language is
                    # changed first and then components are updated. But
                    # not all are yet updated and this spans across them.
                    continue

        # Trigger source checks on target check update (multiple failing checks)
        if (create or old_checks) and not self.is_source:
            if self.is_batch_update:
                self.translation.component.updated_sources[self.source_unit.id] = (
                    self.source_unit
                )
            else:
                self.source_unit.run_checks()

        # This is always preset as it is used in top of this method
        self.clear_checks_cache()

        if not self.is_batch_update and (create or old_checks):
            self.translation.invalidate_cache()

    def nearby(self, count: int) -> models.QuerySet[Unit]:
        """Return list of nearby messages based on location."""
        if self.position == 0:
            return Unit.objects.none()
        with sentry_sdk.start_span(op="unit.nearby", name=f"{self.pk}"):
            # Limiting the query is needed to avoid issues when unit
            # position is not properly populated
            result = (
                self.translation.unit_set.prefetch_full()
                .order_by("position")
                .filter(
                    position__gte=self.position - count,
                    position__lte=self.position + count,
                )[: ((2 * count) + 1)]
            )
            # Force materializing the query
            return result.fill_in_source_translation()

    def nearby_keys(self, count: int) -> Iterable[Unit]:
        # Do not show nearby keys on bilingual
        if not self.translation.component.has_template():
            return []
        with sentry_sdk.start_span(op="unit.nearby_keys", name=f"{self.pk}"):
            key = self.translation.keys_cache_key
            key_list = cache.get(key)
            unit_set = self.translation.unit_set
            if key_list is None or self.pk not in key_list:
                key_list = list(
                    unit_set.order_by("context").values_list("id", flat=True)
                )
                cache.set(key, key_list)
            offset = key_list.index(self.pk)
            nearby = key_list[max(offset - count, 0) : offset + count]
            return (
                unit_set.filter(id__in=nearby)
                .prefetch_full()
                .order_by("context")
                .fill_in_source_translation()
            )

    def variants(self) -> Iterable[Unit]:
        if not self.variant:
            return []
        return (
            self.variant.unit_set.filter(translation=self.translation)
            .prefetch()
            .prefetch_full()
            .order_by("context")
        )

    @transaction.atomic
    def translate(
        self,
        user: User | None,
        new_target: str | list[str],
        new_state: StringState,
        *,
        change_action: int | None = None,
        propagate: bool = True,
        author: User | None = None,
        request: AuthenticatedHttpRequest | None = None,
        add_alternative: bool = False,
    ) -> bool:
        """
        Store new translation of a unit.

        Propagation is currently disabled on import.
        """
        component = self.translation.component

        # Force flushing checks cache
        self.invalidate_checks_cache()

        # Fetch current copy from database and lock it for update
        old_unit = Unit.objects.select_for_update().get(pk=self.pk)
        self.store_old_unit(old_unit)

        # Handle simple string units
        new_target_list = [new_target] if isinstance(new_target, str) else new_target

        # Handle managing alternative translations
        if add_alternative:
            new_target_list.append("")
        elif component.is_multivalue:
            new_target_list = [target for target in new_target_list if target]
            if not new_target_list:
                new_target_list = [""]

        if not component.is_multivalue:
            new_target_list = self.adjust_plurals(new_target_list)

        # Apply autofixes
        if not self.translation.is_template:
            new_target_list, self.fixups = fix_target(new_target_list, self)

        # Update unit and save it
        self.target = join_plural(new_target_list)
        not_empty = any(new_target_list)

        # Newlines fixup
        if "dos-eol" in self.all_flags:
            self.target = NEWLINES.sub("\r\n", self.target)

        # Update string state
        if not_empty:
            self.state = new_state
        else:
            self.state = STATE_EMPTY

        # Update original state unless we are updating read-only strings. This
        # does never happen directly, but FillReadOnlyAddon does this.
        if new_state != STATE_READONLY:
            self.original_state = self.state

        # Save to the database
        saved = self.save_backend(
            user,
            change_action=change_action,
            propagate=propagate,
            author=author,
            request=request,
        )

        # Enforced checks can revert the state to needs editing (fuzzy)
        if (
            self.state >= STATE_TRANSLATED
            and component.enforced_checks
            and self.all_checks_names & set(component.enforced_checks)
        ):
            self.state = self.original_state = STATE_FUZZY
            self.save(
                run_checks=False,
                same_content=True,
                update_fields=["state", "original_state"],
            )

        self.update_translation_memory(user)

        if change_action == ActionEvents.AUTO:
            self.labels.add(component.project.automatically_translated_label)
        else:
            self.labels.through.objects.filter(
                unit=self, label__name="Automatically translated"
            ).delete()

        return saved

    def get_all_flags(self, override=None):
        """Return union of own and component flags."""
        # Validate flags from the unit to avoid crash
        try:
            unit_flags = Flags(override or self.flags)
        except ParseException:
            unit_flags = None

        # Ordering is important here as that defines overriding
        return Flags(
            # Base on translation + component flags
            self.translation.all_flags,
            # Apply unit flags from the file format
            unit_flags,
            # The source_unit is None before saving the object for the first time
            getattr(self.source_unit, "extra_flags", ""),
            # This unit flag overrides
            self.extra_flags,
        )

    @cached_property
    def all_flags(self):
        return self.get_all_flags()

    def get_unit_flags(self):
        return Flags(self.extra_flags)

    @cached_property
    def edit_mode(self) -> str:
        """Return syntax highlighting mode for Prismjs."""
        flags = self.all_flags
        if "icu-message-format" in flags:
            return "icu-message-format"
        if "rst-text" in flags:
            return "rest"
        if "md-text" in flags:
            return "markdown"
        if "xml-text" in flags:
            return "xml"
        if "safe-html" in flags:
            return "html"
        return "none"

    def get_secondary_units(self, user: User) -> list[Unit]:
        """Return list of secondary units."""
        translation = self.translation
        component = translation.component
        secondary_langs: set[int] = user.profile.secondary_language_ids

        # Add project/component secondary languages
        if component.secondary_language_id:
            secondary_langs.add(component.secondary_language_id)
        elif component.project.secondary_language_id:
            secondary_langs.add(component.project.secondary_language_id)

        # Remove current source and trarget language
        secondary_langs -= {translation.language_id, component.source_language_id}

        if not secondary_langs:
            return []
        result = get_distinct_translations(
            self.source_unit.unit_set.filter(
                Q(translation__language__in=secondary_langs)
                & Q(state__gte=STATE_TRANSLATED)
                & Q(state__lt=STATE_READONLY)
                & ~Q(target__lower__md5=MD5(Value("")))
                & ~Q(pk=self.pk)
            ).select_related(
                "source_unit",
                "translation__language",
                "translation__plural",
            )
        )
        # Avoid fetching component again from the database
        for unit in result:
            unit.translation.component = component
        return result

    @property
    def checksum(self):
        """
        Return unique hex identifier.

        It's unsigned representation of id_hash in hex.
        """
        return hash_to_checksum(self.id_hash)

    @cached_property
    def propagated_units(self) -> UnitQuerySet:
        return (
            Unit.objects.same(self)
            .prefetch()
            .filter(
                translation__component__allow_translation_propagation=True,
                translation__plural_id=self.translation.plural_id,
            )
        )

    def get_max_length(self):
        """Return maximal translation length."""
        # Fallback to reasonably big value
        fallback = 10000

        # Not yet saved unit
        if not self.pk:
            return fallback
        # Flag defines length
        if self.all_flags.has_value("max-length"):
            return self.all_flags.get_value("max-length")
        # Avoid limiting source strings
        if self.is_source and not self.translation.component.intermediate:
            return fallback
        # Base length on source string
        if settings.LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH:
            return max(100, len(self.get_source_plurals()[0]) * 10)

        return fallback

    def get_target_hash(self) -> int:
        return calculate_hash(self.target)

    @cached_property
    def content_hash(self) -> int:
        return calculate_hash(self.source, self.context)

    @cached_property
    def recent_content_changes(self):
        """
        Content changes for a unit ordered by timestamp.

        Can be prefetched using prefetch_recent_content_changes.
        """
        return self.change_set.content().select_related("author").order_by("-timestamp")

    def get_last_content_change(self, silent: bool = False) -> tuple[User, datetime]:
        """
        Get last content change metadata.

        Used when committing pending changes, needs to handle and report inconsistencies
        from past releases.
        """
        from weblate.auth.models import get_anonymous

        try:
            change = self.recent_content_changes[0]
        except IndexError:
            return get_anonymous(), timezone.now()
        return change.author or get_anonymous(), change.timestamp

    def get_locations(self) -> Generator[tuple[str, str, str], None, None]:
        """Return list of location filenames."""
        for location in self.location.split(","):
            location = location.strip()
            if not location:
                continue
            location_parts = location.split(":")
            if len(location_parts) == 2:
                filename, line = location_parts
            else:
                filename = location_parts[0]
                line = "0"
            yield location, filename, line

    @cached_property
    def all_labels(self):
        from weblate.trans.models import Label

        if self.is_source:
            return self.labels.all()
        return Label.objects.filter(
            unit__id__in=(self.id, self.source_unit_id)
        ).distinct()

    def get_flag_actions(self):
        flags = self.all_flags
        translation = self.translation
        component = translation.component
        result = []
        if self.is_source:
            if "read-only" in flags:
                if (
                    "read-only" not in translation.all_flags
                    and "read-only" not in component.all_flags
                ):
                    result.append(
                        ("removeflag", "read-only", gettext("Unmark as read-only"))
                    )
            else:
                result.append(("addflag", "read-only", gettext("Mark as read-only")))
        if component.is_glossary:
            if "read-only" in self.source_unit.get_unit_flags():
                result.append(
                    ("removeflag", "read-only", gettext("Unmark as untranslatable"))
                )
            else:
                result.append(
                    ("addflag", "read-only", gettext("Mark as untranslatable"))
                )
            if "forbidden" in flags:
                result.append(
                    (
                        "removeflag",
                        "forbidden",
                        gettext("Unmark as forbidden translation"),
                    )
                )
            else:
                result.append(
                    (
                        "addflag",
                        "forbidden",
                        gettext("Mark as forbidden translation"),
                    )
                )
            if "terminology" in flags:
                result.append(
                    (
                        "removeflag",
                        "terminology",
                        gettext("Unmark as terminology"),
                    )
                )
            else:
                result.append(
                    (
                        "addflag",
                        "terminology",
                        gettext("Mark as terminology"),
                    )
                )
        return result

    def invalidate_related_cache(self) -> None:
        # Invalidate stats counts
        self.translation.invalidate_cache()
        # Invalidate unit cached properties
        for key in ["all_comments", "suggestions"]:
            if key in self.__dict__:
                del self.__dict__[key]

    def update_explanation(
        self, explanation: str, user: User, save: bool = True
    ) -> bool:
        """Update glossary explanation."""
        verify_in_transaction()
        old = self.old_unit["explanation"]
        if old == explanation:
            return False
        self.explanation = explanation
        file_format_support = (
            self.translation.component.file_format_cls.supports_explanation
        )
        units: Iterable[Unit] = []
        if file_format_support:
            if self.is_source:
                units = self.unit_set.exclude(id=self.id).select_for_update()
                units.update(pending=True)
            else:
                self.pending = True
            # Always generate change for self
            units = [*units, self]
        if save:
            self.save(update_fields=["explanation", "pending"], only_save=True)

        for unit in units:
            unit.generate_change(
                user=user,
                author=user,
                change_action=ActionEvents.EXPLANATION,
                check_new=False,
                save=True,
                target=explanation,
                old=old,
            )
        return True

    def update_extra_flags(
        self, extra_flags: str, user: User, save: bool = True
    ) -> None:
        """Update unit extra flags."""
        old = self.old_unit["extra_flags"]
        self.extra_flags = extra_flags
        units: Iterable[Unit] = []
        if self.is_source:
            units = self.unit_set.select_for_update().exclude(id=self.id)
        # Always generate change for self
        units = [*units, self]
        if save:
            self.save(update_fields=["extra_flags"], only_save=True)

        for unit in units:
            unit.generate_change(
                user=user,
                author=user,
                change_action=ActionEvents.EXTRA_FLAGS,
                check_new=False,
                save=True,
                old=old,
                target=self.extra_flags,
            )

    @cached_property
    def glossary_sort_key(self):
        return (self.translation.component.priority, self.source.lower())

    def update_translation_memory(
        self, user: User | None = None, *, needs_user_check: bool = True
    ) -> None:
        if needs_user_check and (
            not user
            or user.is_bot
            or not user.is_active
            or self.target == self.old_unit["target"]
        ):
            return

        translation = self.translation
        component = translation.component
        if (
            (not translation.is_source or component.intermediate)
            and self.state >= STATE_TRANSLATED
            and not component.is_glossary
            and is_valid_memory_entry(source=self.source, target=self.target)
        ):
            handle_unit_translation_change(self, user)
