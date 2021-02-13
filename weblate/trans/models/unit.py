#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import re
from copy import copy
from typing import List, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import models, transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS, Check
from weblate.formats.helpers import CONTROLCHARS
from weblate.memory.tasks import handle_unit_translation_change
from weblate.trans.autofixes import fix_target
from weblate.trans.mixins import LoggerMixin
from weblate.trans.models.change import Change
from weblate.trans.models.comment import Comment
from weblate.trans.models.suggestion import Suggestion
from weblate.trans.models.variant import Variant
from weblate.trans.signals import unit_pre_create
from weblate.trans.util import (
    get_distinct_translations,
    is_plural,
    join_plural,
    split_plural,
)
from weblate.trans.validators import validate_check_flags
from weblate.utils.db import (
    FastDeleteModelMixin,
    FastDeleteQuerySetMixin,
    get_nokey_args,
)
from weblate.utils.errors import report_error
from weblate.utils.hash import calculate_hash, hash_to_checksum
from weblate.utils.search import parse_query
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_CHOICES,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)

SIMPLE_FILTERS = {
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


class UnitQuerySet(FastDeleteQuerySetMixin, models.QuerySet):
    def filter_type(self, rqtype):
        """Basic filtering based on unit state or failed checks."""
        if rqtype in SIMPLE_FILTERS:
            return self.filter(**SIMPLE_FILTERS[rqtype])
        if rqtype.startswith("check:"):
            check_id = rqtype[6:]
            if check_id not in CHECKS:
                raise ValueError(f"Unknown check: {check_id}")
            return self.filter(check__check=check_id, check__dismissed=False)
        if rqtype.startswith("label:"):
            return self.filter(labels__name=rqtype[6:])
        if rqtype == "all":
            return self.all()
        raise ValueError(f"Unknown filter: {rqtype}")

    def prefetch(self):
        return self.prefetch_related(
            "translation",
            "translation__language",
            "translation__plural",
            "translation__component",
            "translation__component__project",
            "translation__component__source_language",
        )

    def prefetch_full(self):
        return self.prefetch_related(
            "labels",
            "source_unit",
            "source_unit__translation",
            "source_unit__translation__component",
            "source_unit__translation__component__project",
            "check_set",
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

    def search(self, query, **context):
        """High level wrapper for searching."""
        return self.filter(parse_query(query, **context))

    def same(self, unit, exclude=True):
        """Unit with same source within same project."""
        translation = unit.translation
        component = translation.component
        result = self.filter(
            source=unit.source,
            context=unit.context,
            translation__component__project_id=component.project_id,
            translation__language_id=translation.language_id,
            translation__component__source_language_id=component.source_language_id,
        )
        if exclude:
            result = result.exclude(pk=unit.id)
        return result

    def order_by_request(self, form_data):
        sort_list_request = form_data.get("sort_by", "").split(",")
        available_sort_choices = [
            "priority",
            "position",
            "context",
            "num_words",
            "labels",
            "timestamp",
            "source",
            "target",
        ]
        countable_sort_choices = {
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
            return self.order()
        if "max_labels_name" in sort_list or "-max_labels_name" in sort_list:
            return self.annotate(max_labels_name=Max("labels__name")).order_by(
                *sort_list
            )
        return self.order_by(*sort_list)

    def order_by_count(self, choice, filter):
        model = choice.split("__")[0].replace("-", "")
        annotation_name = choice.replace("-", "")
        return self.annotate(**{annotation_name: Count(model, filter=filter)}).order_by(
            choice
        )

    @cached_property
    def source_context_lookup(self):
        return {(unit.context, unit.source): unit for unit in self}

    @cached_property
    def source_lookup(self):
        return {unit.source: unit for unit in self}

    def get_unit(self, ttunit):
        """Find unit matching translate-toolkit unit.

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
                return self.source_context_lookup[(match, source)]
            except KeyError:
                continue

        # Fallback to source string only lookup
        try:
            return self.source_lookup[source]
        except KeyError:
            raise Unit.DoesNotExist("No matching unit found!")

    def order(self):
        return self.order_by("-priority", "position")

    def filter_access(self, user):
        if user.is_superuser:
            return self
        return self.filter(
            Q(translation__component__project_id__in=user.allowed_project_ids)
            & (
                Q(translation__component__restricted=False)
                | Q(translation__component_id__in=user.component_permissions)
            )
        )

    def get_ordered(self, ids):
        """Return list of units ordered by ID."""
        return sorted(self.filter(id__in=ids), key=lambda unit: ids.index(unit.id))


class Unit(FastDeleteModelMixin, models.Model, LoggerMixin):

    translation = models.ForeignKey("Translation", on_delete=models.deletion.CASCADE)
    id_hash = models.BigIntegerField()
    location = models.TextField(default="", blank=True)
    context = models.TextField(default="", blank=True)
    note = models.TextField(default="", blank=True)
    flags = models.TextField(default="", blank=True)
    source = models.TextField()
    previous_source = models.TextField(default="", blank=True)
    target = models.TextField(default="", blank=True)
    state = models.IntegerField(
        default=STATE_EMPTY, db_index=True, choices=STATE_CHOICES
    )
    original_state = models.IntegerField(default=STATE_EMPTY, choices=STATE_CHOICES)

    position = models.IntegerField()

    num_words = models.IntegerField(default=0)

    priority = models.IntegerField(default=100)

    pending = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    extra_flags = models.TextField(
        verbose_name=gettext_lazy("Translation flags"),
        default="",
        help_text=gettext_lazy(
            "Additional comma-separated flags to influence quality checks. "
            "Possible values can be found in the documentation."
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
        "Variant",
        on_delete=models.deletion.SET_NULL,
        blank=True,
        null=True,
        default=None,
    )
    labels = models.ManyToManyField(
        "Label", verbose_name=gettext_lazy("Labels"), blank=True
    )

    source_unit = models.ForeignKey(
        "Unit", on_delete=models.deletion.CASCADE, blank=True, null=True
    )

    objects = UnitQuerySet.as_manager()

    class Meta:
        app_label = "trans"
        unique_together = ("translation", "id_hash")
        index_together = [("translation", "pending"), ("priority", "position")]
        verbose_name = "string"
        verbose_name_plural = "strings"

    def __str__(self):
        if self.translation.is_template:
            return self.context
        if self.context:
            return f"[{self.context}] {self.source}"
        return self.source

    def save(
        self,
        same_content: bool = False,
        run_checks: bool = True,
        propagate_checks: Optional[bool] = None,
        force_insert: bool = False,
        force_update: bool = False,
        using=None,
        update_fields: Optional[List[str]] = None,
    ):
        """Wrapper around save to run checks or update fulltext."""
        # Store number of words
        if not same_content or not self.num_words:
            self.num_words = len(self.source_string.split())
            if update_fields and "num_words" not in update_fields:
                update_fields.append("num_words")

        # Actually save the unit
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

        # Set source_unit for source units
        if self.is_source and not self.source_unit:
            self.source_unit = self
            self.save(
                same_content=True, run_checks=False, update_fields=["source_unit"]
            )

        # Update checks if content or fuzzy flag has changed
        if run_checks:
            self.run_checks(propagate_checks)
        if self.is_source:
            self.source_unit_save()

        # Update manual variants
        self.update_variants()

        # Update terminology
        self.sync_terminology()

    def get_absolute_url(self):
        return "{}?checksum={}".format(
            self.translation.get_translate_url(), self.checksum
        )

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super().__init__(*args, **kwargs)
        self.old_unit = copy(self)
        self.is_batch_update = False
        self.is_bulk_edit = False
        self.source_updated = False
        self.check_cache = {}
        self.fixups = []
        # Data for machinery integration
        self.machinery = {"best": -1}
        # Data for glossary integration
        self.glossary_terms = None

    @property
    def approved(self):
        return self.state == STATE_APPROVED

    @property
    def translated(self):
        return self.state >= STATE_TRANSLATED

    @property
    def readonly(self):
        return self.state == STATE_READONLY

    @property
    def fuzzy(self):
        return self.state == STATE_FUZZY

    @property
    def has_failing_check(self):
        return bool(self.active_checks)

    @property
    def has_comment(self):
        # Use bool here as unresolved_comments might be list
        # or a queryset (from prefetch)
        return bool(self.unresolved_comments)

    @property
    def has_suggestion(self):
        return bool(self.suggestions)

    @cached_property
    def full_slug(self):
        return "/".join(
            (
                self.translation.component.project.slug,
                self.translation.component.slug,
                self.translation.language.code,
                str(self.pk),
            )
        )

    def source_unit_save(self):
        # Run checks, update state and priority if flags changed
        # or running bulk edit
        if (
            self.old_unit.extra_flags != self.extra_flags
            or self.state != self.old_unit.state
        ):
            # We can not exclude current unit here as we need to trigger
            # the updates below
            for unit in self.unit_set.prefetch_full():
                unit.update_state()
                unit.update_priority()
                unit.run_checks()
            if not self.is_bulk_edit and not self.is_batch_update:
                self.translation.component.invalidate_cache()

    def sync_terminology(self):
        new_flags = Flags(self.extra_flags, self.flags)

        if "terminology" in new_flags:
            self.translation.component.sync_terminology()

    def update_variants(self):
        old_flags = Flags(self.old_unit.extra_flags, self.old_unit.flags)
        new_flags = Flags(self.extra_flags, self.flags)

        old_variant = None
        if old_flags.has_value("variant"):
            old_variant = old_flags.get_value("variant")
        new_variant = None
        if new_flags.has_value("variant"):
            new_variant = new_flags.get_value("variant")

        # Check for relevant changes
        if old_variant == new_variant:
            return

        # Delete stale variant
        if old_variant:
            for variant in self.defined_variants.all():
                variant.defining_units.remove(self)
                if variant.defining_units.count() == 0:
                    variant.delete()
                else:
                    variant.unit_set.filter(id_hash=self.id_hash).update(variant=None)

        # Add new variant
        if new_variant:
            variant = Variant.objects.get_or_create(
                key=new_variant, component=self.translation.component
            )[0]
            variant.defining_units.add(self)

        # Update variant links
        self.translation.component.update_variants()

    def get_unit_state(self, unit, flags):
        """Calculate translated and fuzzy status."""
        if (
            unit.is_readonly()
            or (flags is not None and "read-only" in self.get_all_flags(flags))
            or (
                flags is not None
                and not self.is_source
                and self.source_unit.state < STATE_TRANSLATED
            )
        ):
            return STATE_READONLY

        # We need to keep approved/fuzzy state for formats which do not
        # support saving it
        if unit.is_fuzzy(self.fuzzy):
            return STATE_FUZZY

        if not unit.is_translated():
            return STATE_EMPTY

        if unit.is_approved(self.approved) and self.translation.enable_review:
            return STATE_APPROVED

        return STATE_TRANSLATED

    @staticmethod
    def check_valid(texts):
        for text in texts:
            if any(char in text for char in CONTROLCHARS):
                raise ValueError(f"String contains control char: {text!r}")

    def update_source_unit(
        self, component, source, context, pos, note, location, flags
    ):
        source_unit = component.get_source(
            self.id_hash,
            create={
                "source": source,
                "target": source,
                "context": context,
                "position": pos,
                "note": note,
                "location": location,
                "flags": flags,
            },
        )
        if (
            not source_unit.source_updated
            and not component.has_template()
            and (
                pos != source_unit.position
                or location != source_unit.location
                or flags != source_unit.flags
                or note != source_unit.note
            )
        ):
            source_unit.position = pos
            source_unit.source_updated = True
            source_unit.location = location
            source_unit.flags = flags
            source_unit.note = note
            source_unit.save(
                update_fields=["position", "location", "flags", "note"],
                same_content=True,
                run_checks=False,
            )
        self.source_unit = source_unit

    def update_from_unit(self, unit, pos, created):
        """Update Unit from ttkit unit."""
        translation = self.translation
        component = translation.component
        self.is_batch_update = True
        self.source_updated = True
        # Get unit attributes
        try:
            location = unit.locations
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
            previous_source = unit.previous_source
        except Exception as error:
            report_error(cause="Unit update error")
            translation.component.handle_parse_error(error, translation)

        # Ensure we track source string for bilingual, this can not use
        # Unit.is_source as that depends on source_unit attribute, which
        # we set here
        old_source_unit = self.source_unit
        if not translation.is_source:
            self.update_source_unit(
                component, source, context, pos, note, location, flags
            )

        # Calculate state
        state = self.get_unit_state(unit, flags)
        original_state = self.get_unit_state(unit, None)

        # Has source changed
        same_source = source == self.source and context == self.context

        # Monolingual files handling (without target change)
        if (
            not created
            and state != STATE_READONLY
            and unit.template is not None
            and target == self.target
        ):
            if not same_source and state in (STATE_TRANSLATED, STATE_APPROVED):
                if self.previous_source == self.source and self.fuzzy:
                    # Source change was reverted
                    previous_source = ""
                    state = STATE_TRANSLATED
                else:
                    # Store previous source and fuzzy flag for monolingual
                    if previous_source == "":
                        previous_source = self.source
                    state = STATE_FUZZY
            elif self.state in (STATE_FUZZY, STATE_APPROVED):
                # We should keep calculated flags if translation was
                # not changed outside
                previous_source = self.previous_source
                state = self.state

        # Update checks on fuzzy update or on content change
        same_target = target == self.target
        same_state = state == self.state and flags == self.flags

        # Check if we actually need to change anything
        # pylint: disable=too-many-boolean-expressions
        if (
            not created
            and same_source
            and same_target
            and same_state
            and original_state == self.original_state
            and location == self.location
            and flags == self.flags
            and note == self.note
            and pos == self.position
            and previous_source == self.previous_source
            and self.source_unit == old_source_unit
            and old_source_unit is not None
        ):
            return

        # Store updated values
        self.original_state = original_state
        self.position = pos
        self.location = location
        self.flags = flags
        self.source = source
        self.target = target
        self.state = state
        self.context = context
        self.note = note
        self.previous_source = previous_source
        self.update_priority(save=False)

        # Sanitize number of plurals
        if self.is_plural:
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
        if not same_source and previous_source:
            Change.objects.create(
                unit=self,
                action=Change.ACTION_SOURCE_CHANGE,
                old=previous_source,
                target=self.source,
            )
        # Update translation memory if needed
        if (
            self.state >= STATE_TRANSLATED
            and (not translation.is_source or component.intermediate)
            and (created or not same_source or not same_target)
        ):
            transaction.on_commit(lambda: handle_unit_translation_change.delay(self.id))

    def update_state(self):
        """
        Updates state based on flags.

        Mark read only strings:

        * Flagged with 'read-only'
        * Where source string is not translated
        """
        if "read-only" in self.all_flags or (
            not self.is_source and self.source_unit.state < STATE_TRANSLATED
        ):
            if not self.readonly:
                self.state = STATE_READONLY
                self.save(same_content=True, run_checks=False, update_fields=["state"])
        elif self.readonly and self.state != self.original_state:
            self.state = self.original_state
            self.save(same_content=True, run_checks=False, update_fields=["state"])

    def update_priority(self, save=True):
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
    def is_plural(self):
        """Check whether message is plural."""
        return is_plural(self.source) or is_plural(self.target)

    @cached_property
    def is_source(self):
        return self.source_unit_id is None or self.source_unit_id == self.id

    def get_source_plurals(self):
        """Return source plurals in array."""
        return split_plural(self.source)

    @cached_property
    def source_string(self):
        """
        Returns a single source string.

        In most cases it's singular with exception of unused singulars
        generated by some frameworks.
        """
        plurals = self.get_source_plurals()
        singular = plurals[0]
        if len(plurals) == 1 or "<unused singular" not in singular:
            return singular
        return plurals[1]

    def get_target_plurals(self, plurals=None):
        """Return target plurals in array."""
        # Is this plural?
        if not self.is_plural:
            return [self.target]

        # Split plurals
        ret = split_plural(self.target)

        if plurals is None:
            plurals = self.translation.plural.number

        # Check if we have expected number of them
        if len(ret) == plurals:
            return ret

        # Pad with empty translations
        while len(ret) < plurals:
            ret.append("")

        # Delete extra plurals
        while len(ret) > plurals:
            del ret[-1]

        return ret

    def propagate(self, user, change_action=None, author=None):
        """Propagate current translation to all others."""
        result = False
        for unit in self.same_source_units:
            if not user.has_perm("unit.edit", unit):
                continue
            if unit.target == self.target and unit.state == self.state:
                continue
            unit.target = self.target
            unit.state = self.state
            unit.save_backend(
                user,
                False,
                change_action=change_action,
                author=None,
                run_checks=False,
            )
            result = True
        return result

    def save_backend(
        self,
        user,
        propagate: bool = True,
        change_action=None,
        author=None,
        run_checks: bool = True,
        propagate_checks: bool = True,
    ):
        """Stores unit to backend.

        Optional user parameters defines authorship of a change.

        This should be always called in a transaction with updated unit
        locked for update.
        """
        # For case when authorship specified, use user
        author = author or user

        # Commit possible previous changes on this unit
        if self.pending:
            change_author = self.get_last_content_change()[0]
            if change_author != author:
                self.translation.commit_pending("pending unit", user, force=True)

        # Propagate to other projects
        # This has to be done before changing source for template
        was_propagated = False
        if propagate:
            was_propagated = self.propagate(user, change_action, author=author)

        changed = (
            self.old_unit.state == self.state and self.old_unit.target == self.target
        )
        # Return if there was no change
        # We have to explicitly check for fuzzy flag change on monolingual
        # files, where we handle it ourselves without storing to backend
        if changed and not was_propagated:
            return False

        update_fields = ["target", "state", "original_state", "pending"]
        if self.is_source and not self.translation.component.intermediate:
            self.source = self.target
            update_fields.extend(["source"])

        # Unit is pending for write
        self.pending = True
        # Update translated flag (not fuzzy and at least one translation)
        translation = bool(max(self.get_target_plurals()))
        if self.state >= STATE_TRANSLATED and not translation:
            self.state = STATE_EMPTY
        elif self.state == STATE_EMPTY and translation:
            self.state = STATE_TRANSLATED
        self.original_state = self.state

        # Save updated unit to database, skip running checks
        self.save(
            update_fields=update_fields,
            run_checks=run_checks,
            propagate_checks=was_propagated or changed,
        )

        # Generate Change object for this change
        self.generate_change(user or author, author, change_action)

        if change_action not in (
            Change.ACTION_UPLOAD,
            Change.ACTION_AUTO,
            Change.ACTION_BULK_EDIT,
        ):
            # Update translation stats
            self.translation.invalidate_cache()

            # Update user stats
            author.profile.increase_count("translated")

        # Update related source strings if working on a template
        if self.translation.is_template and self.old_unit.target != self.target:
            self.update_source_units(self.old_unit.target, user or author, author)

        return True

    def update_source_units(self, previous_source, user, author):
        """Update source for units withing same component.

        This is needed when editing template translation for monolingual formats.
        """
        # Find relevant units
        for unit in self.unit_set.exclude(id=self.id).prefetch_full():
            # Update source and number of words
            unit.source = self.target
            unit.num_words = self.num_words
            # Find reverted units
            if unit.state == STATE_FUZZY and unit.previous_source == self.target:
                # Unset fuzzy on reverted
                unit.original_state = unit.state = STATE_TRANSLATED
                unit.previous_source = ""
            elif (
                unit.original_state == STATE_FUZZY
                and unit.previous_source == self.target
            ):
                # Unset fuzzy on reverted
                unit.original_state = STATE_TRANSLATED
                unit.previous_source = ""
            elif unit.state >= STATE_TRANSLATED:
                # Set fuzzy on changed
                unit.original_state = STATE_FUZZY
                if unit.state < STATE_READONLY:
                    unit.state = STATE_FUZZY
                unit.previous_source = previous_source

            # Save unit and change
            unit.save()
            Change.objects.create(
                unit=unit,
                action=Change.ACTION_SOURCE_CHANGE,
                user=user,
                author=author,
                old=previous_source,
                target=self.target,
            )
            # Invalidate stats
            unit.translation.invalidate_cache()

    def generate_change(self, user, author, change_action, check_new=True):
        """Create Change entry for saving unit."""
        # Notify about new contributor
        if check_new and not self.translation.change_set.filter(user=user).exists():
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
        elif self.old_unit.state >= STATE_FUZZY:
            if self.state == STATE_APPROVED:
                action = Change.ACTION_APPROVE
            else:
                action = Change.ACTION_CHANGE
        else:
            if self.state == STATE_APPROVED:
                action = Change.ACTION_APPROVE
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

    @cached_property
    def suggestions(self):
        """Return all suggestions for this unit."""
        return self.suggestion_set.order()

    @cached_property
    def all_checks(self):
        result = self.check_set.all()
        # Force fetching
        list(result)
        return result

    def clear_checks_cache(self):
        if "all_checks" in self.__dict__:
            del self.__dict__["all_checks"]

    @property
    def all_checks_names(self):
        return {check.check for check in self.all_checks}

    @property
    def dismissed_checks(self):
        return [check for check in self.all_checks if check.dismissed]

    @property
    def active_checks(self):
        """Return all active (not ignored) checks for this unit."""
        return [check for check in self.all_checks if not check.dismissed]

    @cached_property
    def all_comments(self):
        """Return list of target comments."""
        query = Q(unit=self)
        if self.is_source:
            # Add all comments on translation on source string comment
            query |= Q(unit__source_unit=self)
        else:
            # Add source string comments for translation unit
            query |= Q(unit=self.source_unit)
        return Comment.objects.filter(query).prefetch_related("unit", "user").order()

    @cached_property
    def unresolved_comments(self):
        return [
            comment
            for comment in self.all_comments
            if not comment.resolved and comment.unit_id == self.id
        ]

    def run_checks(self, propagate: Optional[bool] = None):
        """Update checks for this unit."""
        needs_propagate = bool(propagate)

        src = self.get_source_plurals()
        tgt = self.get_target_plurals()

        old_checks = self.all_checks_names
        create = []

        if self.translation.component.is_glossary:
            # We might eventually run some checks on glossary
            checks = {}
            meth = "check_source"
            args = src, self
        elif self.is_source:
            checks = CHECKS.source
            meth = "check_source"
            args = src, self
        else:
            if self.readonly:
                checks = {}
            else:
                checks = CHECKS.target
            meth = "check_target"
            args = src, tgt, self

        # Run all checks
        for check, check_obj in checks.items():
            # Does the check fire?
            if getattr(check_obj, meth)(*args):
                if check in old_checks:
                    # We already have this check
                    old_checks.remove(check)
                    # Propagation is handled in
                    # weblate.checks.models.remove_complimentary_checks
                else:
                    # Create new check
                    create.append(Check(unit=self, dismissed=False, check=check))
                    needs_propagate |= check_obj.propagates

        if create:
            Check.objects.bulk_create(create, batch_size=500, ignore_conflicts=True)
            # Trigger source checks on target check update (multiple failing checks)
            if not self.is_source:
                if self.is_batch_update:
                    self.translation.component.updated_sources[
                        self.source_unit.id
                    ] = self.source_unit
                else:
                    self.source_unit.run_checks()
        # Propagate checks which need it (for example consistency)
        if (needs_propagate and propagate is not False) or propagate is True:
            for unit in self.same_source_units:
                try:
                    # Ensure we get a fresh copy of checks
                    # It might be modified meanwhile by propagating to other units
                    unit.clear_checks_cache()

                    unit.run_checks(False)
                except Unit.DoesNotExist:
                    # This can happen in some corner cases like changing
                    # source language of a project - the source language is
                    # changed first and then components are updated. But
                    # not all are yet updated and this spans across them.
                    continue

        # Delete no longer failing checks
        if old_checks:
            Check.objects.filter(unit=self, check__in=old_checks).delete()

        # This is always preset as it is used in top of this method
        self.clear_checks_cache()

    def nearby(self, count):
        """Return list of nearby messages based on location."""
        return (
            self.translation.unit_set.prefetch_full()
            .order_by("position")
            .filter(
                position__gte=self.position - count,
                position__lte=self.position + count,
            )
        )

    def nearby_keys(self, count):
        # Do not show nearby keys on bilingual
        if not self.translation.component.has_template():
            return []
        key = self.translation.keys_cache_key
        key_list = cache.get(key)
        if key_list is None or self.pk not in key_list or True:
            key_list = list(
                self.translation.unit_set.order_by("context").values_list(
                    "id", flat=True
                )
            )
            cache.set(key, key_list)
        offset = key_list.index(self.pk)
        nearby = key_list[max(offset - count, 0) : offset + count]
        return (
            self.translation.unit_set.filter(id__in=nearby)
            .prefetch_full()
            .order_by("context")
        )

    def variants(self):
        if not self.variant:
            return []
        return (
            self.variant.unit_set.filter(translation=self.translation)
            .prefetch_full()
            .order_by("context")
        )

    @transaction.atomic
    def translate(
        self,
        user,
        new_target,
        new_state,
        change_action=None,
        propagate: bool = True,
        author=None,
    ):
        """
        Store new translation of a unit.

        Propagation is currently disabled on import.
        """
        # Fetch current copy from database and lock it for update
        self.old_unit = Unit.objects.select_for_update(**get_nokey_args()).get(
            pk=self.pk
        )

        # Handle simple string units
        if isinstance(new_target, str):
            new_target = [new_target]

        # Apply autofixes
        if not self.translation.is_template:
            new_target, self.fixups = fix_target(new_target, self)

        # Update unit and save it
        self.target = join_plural(new_target)
        not_empty = bool(max(new_target))

        # Newlines fixup
        if "dos-eol" in self.all_flags:
            self.target = NEWLINES.sub("\r\n", self.target)

        if not_empty:
            self.state = new_state
        else:
            self.state = STATE_EMPTY
        self.original_state = self.state
        saved = self.save_backend(
            user, change_action=change_action, propagate=propagate, author=author
        )

        # Enforced checks can revert the state to needs editing (fuzzy)
        if (
            self.state >= STATE_TRANSLATED
            and self.translation.component.enforced_checks
            and self.all_checks_names & set(self.translation.component.enforced_checks)
        ):
            self.state = self.original_state = STATE_FUZZY
            self.save(run_checks=False, same_content=True, update_fields=["state"])

        if (
            propagate
            and user
            and self.target != self.old_unit.target
            and self.state >= STATE_TRANSLATED
            and self.translation.component.is_glossary
        ):
            transaction.on_commit(
                lambda: handle_unit_translation_change.delay(self.id, user.id)
            )

        return saved

    def get_all_flags(self, override=None):
        """Return union of own and component flags."""
        return Flags(
            self.translation.all_flags,
            self.extra_flags,
            # The source_unit is None before saving the object for the first time
            getattr(self.source_unit, "extra_flags", ""),
            override or self.flags,
        )

    @cached_property
    def all_flags(self):
        return self.get_all_flags()

    @cached_property
    def edit_mode(self):
        """Returns syntax higlighting mode for Prismjs."""
        flags = self.all_flags
        if "rst-text" in flags:
            return "rest"
        if "md-text" in flags:
            return "markdown"
        if "xml-text" in flags:
            return "xml"
        if "safe-html" in flags:
            return "html"
        return "none"

    def get_secondary_units(self, user):
        """Return list of secondary units."""
        secondary_langs = user.profile.secondary_languages.exclude(
            id__in=[
                self.translation.language_id,
                self.translation.component.source_language_id,
            ]
        )
        result = get_distinct_translations(
            self.source_unit.unit_set.filter(
                Q(translation__language__in=secondary_langs)
                & Q(state__gte=STATE_TRANSLATED)
                & Q(state__lt=STATE_READONLY)
                & ~Q(target="")
                & ~Q(pk=self.pk)
            ).select_related(
                "source_unit",
                "translation__language",
                "translation__plural",
            )
        )
        for unit in result:
            unit.translation.component = self.translation.component
        return result

    @property
    def checksum(self):
        """Return unique hex identifier.

        It's unsigned representation of id_hash in hex.
        """
        return hash_to_checksum(self.id_hash)

    @cached_property
    def same_source_units(self):
        return (
            Unit.objects.same(self)
            .prefetch_full()
            .filter(translation__component__allow_translation_propagation=True)
        )

    def get_max_length(self):
        """Returns maximal translation length."""
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

    def get_target_hash(self):
        return calculate_hash(self.target)

    @cached_property
    def content_hash(self):
        if self.translation.component.template:
            return calculate_hash(self.source, self.context)
        return self.id_hash

    @cached_property
    def recent_content_changes(self):
        """
        Content changes for a unit ordered by timestamp.

        Can be prefetched using prefetch_recent_content_changes.
        """
        return self.change_set.content().select_related("author").order_by("-timestamp")

    def get_last_content_change(self, silent=False):
        """Wrapper to get last content change metadata.

        Used when commiting pending changes, needs to handle and report inconsistencies
        from past releases.
        """
        from weblate.auth.models import get_anonymous

        try:
            change = self.recent_content_changes[0]
            return change.author or get_anonymous(), change.timestamp
        except IndexError:
            if not silent:
                report_error(level="error")
            return get_anonymous(), timezone.now()

    def get_locations(self):
        """Returns list of location filenames."""
        for location in self.location.split(","):
            location = location.strip()
            if location == "":
                continue
            location_parts = location.split(":")
            if len(location_parts) == 2:
                filename, line = location_parts
            else:
                filename = location_parts[0]
                line = 0
            yield location, filename, line

    @cached_property
    def all_labels(self):
        if self.is_source:
            return self.labels.all()
        return self.source_unit.all_labels

    def get_flag_actions(self):
        flags = Flags(self.extra_flags)
        result = []
        if self.is_source:
            if "read-only" in flags:
                result.append(
                    ("removeflag", "read-only", gettext("Unmark as read-only"))
                )
            else:
                result.append(("addflag", "read-only", gettext("Mark as read-only")))
        if self.translation.component.is_glossary:
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
        if self.is_source and self.translation.component.is_glossary:
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
