# -*- coding: utf-8 -*-
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


import re
from copy import copy

from django.conf import settings
from django.core.cache import cache
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy

from weblate.checks import CHECKS
from weblate.checks.flags import Flags
from weblate.checks.models import Check
from weblate.formats.helpers import CONTROLCHARS
from weblate.memory.tasks import update_memory
from weblate.trans.mixins import LoggerMixin
from weblate.trans.models.change import Change
from weblate.trans.models.comment import Comment
from weblate.trans.search import Fulltext
from weblate.trans.signals import unit_pre_create
from weblate.trans.util import (
    get_distinct_translations,
    is_plural,
    join_plural,
    split_plural,
)
from weblate.trans.validators import validate_check_flags
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
    "approved_suggestions": {"state": STATE_APPROVED, "has_suggestion": True},
    "unapproved": {"state": STATE_TRANSLATED},
    "todo": {"state__lt": STATE_TRANSLATED},
    "nottranslated": {"state": STATE_EMPTY},
    "translated": {"state__gte": STATE_TRANSLATED},
    "suggestions": {"has_suggestion": True},
    "nosuggestions": {"has_suggestion": False, "state__lt": STATE_TRANSLATED},
    "comments": {"has_comment": True},
    "allchecks": {"has_failing_check": True},
}

NEWLINES = re.compile(r"\r\n|\r|\n")


class UnitQuerySet(models.QuerySet):
    def filter_type(self, rqtype):
        """Basic filtering based on unit state or failed checks."""
        if rqtype in SIMPLE_FILTERS:
            return self.filter(**SIMPLE_FILTERS[rqtype])
        if rqtype.startswith("check:"):
            check_id = rqtype[6:]
            if check_id not in CHECKS:
                raise ValueError("Unknown check: {}".format(check_id))
            return self.filter(check__check=check_id, check__ignore=False)
        if rqtype.startswith("label:"):
            return self.filter(labels__name=rqtype[6:])
        if rqtype == "all":
            return self.all()
        raise ValueError("Unknown filter: {}".format(rqtype))

    def prefetch(self):
        return self.prefetch_related(
            "translation",
            "translation__language",
            "translation__plural",
            "translation__component",
            "translation__component__project",
            "translation__component__project__source_language",
        )

    def search(self, query):
        """High level wrapper for searching."""
        return self.prefetch().filter(parse_query(query))

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
            translation__language__code__startswith=unit.translation.language.code,
        )
        if exclude:
            result = result.exclude(pk=unit.id)
        return result

    def get_unit(self, ttunit):
        """Find unit matching translate-toolkit unit.

        This is used for import, so kind of fuzzy matching is expected.
        """
        source = ttunit.source
        context = ttunit.context

        params = [{"source": source, "context": context}, {"source": source}]
        # Try empty context first before matching any context
        if context != "":
            params.insert(1, {"source": source, "context": ""})
        # Special case for XLIFF
        if "///" in context:
            params.insert(1, {"source": source, "context": context.split("///", 1)[1]})

        for param in params:
            try:
                return self.get(**param)
            except (Unit.DoesNotExist, Unit.MultipleObjectsReturned):
                continue

        raise Unit.DoesNotExist("No matching unit found!")

    def order(self):
        return self.order_by("-priority", "position")


class Unit(models.Model, LoggerMixin):

    translation = models.ForeignKey("Translation", on_delete=models.deletion.CASCADE)
    id_hash = models.BigIntegerField()
    content_hash = models.BigIntegerField(db_index=True)
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

    has_suggestion = models.BooleanField(default=False, db_index=True)
    has_comment = models.BooleanField(default=False, db_index=True)
    has_failing_check = models.BooleanField(default=False, db_index=True)

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
    extra_context = models.TextField(
        verbose_name=gettext_lazy("Additional context"), default="", blank=True
    )
    shaping = models.ForeignKey(
        "Shaping",
        on_delete=models.deletion.SET_NULL,
        blank=True,
        null=True,
        default=None,
    )
    labels = models.ManyToManyField(
        "Label", verbose_name=gettext_lazy("Labels"), blank=True
    )

    objects = UnitQuerySet.as_manager()

    class Meta:
        app_label = "trans"
        unique_together = ("translation", "id_hash")
        index_together = [("translation", "pending"), ("priority", "position")]

    def __str__(self):
        if self.translation.is_template:
            return self.context
        if self.context:
            return "[{}] {}".format(self.context, self.source)
        return self.source

    def save(
        self,
        same_content=False,
        same_state=False,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
    ):
        """Wrapper around save to run checks or update fulltext."""
        # Store number of words
        if not same_content or not self.num_words:
            self.num_words = len(self.get_source_plurals()[0].split())
            if update_fields and "num_words" not in update_fields:
                update_fields.append("num_words")

        # Actually save the unit
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

        # Update checks if content or fuzzy flag has changed
        if not same_content or not same_state:
            self.run_checks(same_state, same_content)

        # Update fulltext index if content has changed or this is a new unit
        if force_insert or not same_content:
            Fulltext.update_index_unit(self)

    def get_absolute_url(self):
        return "{0}?checksum={1}".format(
            self.translation.get_translate_url(), self.checksum
        )

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super().__init__(*args, **kwargs)
        self.old_unit = copy(self)
        self.is_batch_update = False

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

    def get_unit_state(self, unit, flags):
        """Calculate translated and fuzzy status."""
        if unit.is_readonly() or (
            flags is not None and "read-only" in self.get_all_flags(flags)
        ):
            return STATE_READONLY

        # We need to keep approved/fuzzy state for formats which do not
        # support saving it
        if unit.is_fuzzy(self.fuzzy):
            return STATE_FUZZY

        if not unit.is_translated():
            return STATE_EMPTY

        if (
            unit.is_approved(self.approved)
            and self.translation.component.project.enable_review
        ):
            return STATE_APPROVED
        return STATE_TRANSLATED

    def check_valid(self, texts):
        for text in texts:
            if any(char in text for char in CONTROLCHARS):
                raise ValueError("String contains control char")

    def update_from_unit(self, unit, pos, created):
        """Update Unit from ttkit unit."""
        component = self.translation.component
        self.is_batch_update = True
        # Get unit attributes
        try:
            location = unit.locations
            flags = unit.flags
            target = unit.target
            self.check_valid(split_plural(target))
            source = unit.source
            self.check_valid(split_plural(source))
            context = unit.context
            self.check_valid([context])
            note = unit.notes
            previous_source = unit.previous_source
            content_hash = unit.content_hash
        except Exception as error:
            self.translation.component.handle_parse_error(error, self.translation)

        # Ensure we track source string for bilingual
        if not self.translation.is_source:
            source_info = component.get_source(
                self.id_hash,
                source=source,
                target=source,
                context=context,
                content_hash=calculate_hash(source, context),
                position=0,
                location=location,
                flags=flags,
            )
            self.extra_context = source_info.extra_context
            self.extra_flags = source_info.extra_flags
            self.__dict__["source_info"] = source_info

        # Calculate state
        state = self.get_unit_state(unit, flags)
        self.original_state = self.get_unit_state(unit, None)

        # Has source changed
        same_source = source == self.source and context == self.context

        # Monolingual files handling (without target change)
        if not created and unit.template is not None and target == self.target:
            if not same_source and state >= STATE_TRANSLATED:
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
            location == self.location
            and flags == self.flags
            and same_source
            and same_target
            and same_state
            and note == self.note
            and pos == self.position
            and content_hash == self.content_hash
            and previous_source == self.previous_source
        ):
            return

        # Store updated values
        self.position = pos
        self.location = location
        self.flags = flags
        self.source = source
        self.target = target
        self.state = state
        self.context = context
        self.note = note
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
        # Track updated sources for source checks
        if self.translation.is_template:
            component.updated_sources[self.id_hash] = self
        # Update unit labels
        if not self.translation.is_source:
            self.labels.set(self.source_info.labels.all())
        # Indicate source string change
        if not same_source and previous_source:
            Change.objects.create(
                unit=self,
                action=Change.ACTION_SOURCE_CHANGE,
                old=previous_source,
                target=self.source,
            )

    def update_state(self):
        """
        Updates state based on flags.

        Mark read only strings:

        * Flagged with 'read-only'
        * Where source string is not translated
        """
        source_info = self.source_info
        if "read-only" in self.all_flags or (
            source_info != self and source_info.state < STATE_TRANSLATED
        ):
            if not self.readonly:
                self.state = STATE_READONLY
                self.save(same_content=True, same_state=True, update_fields=["state"])
        elif self.readonly:
            self.state = self.original_state
            self.save(same_content=True, same_state=True, update_fields=["state"])

    def update_priority(self, save=True):
        if self.all_flags.has_value("priority"):
            priority = self.all_flags.get_value("priority")
        else:
            priority = 100
        if self.priority != priority:
            self.priority = priority
            if save:
                self.save(
                    same_content=True, same_state=True, update_fields=["priority"]
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
            if (
                unit.change_set.count() > 0
                and unit.change_set.content().order()[0].action != Change.ACTION_AUTO
            ):
                continue
            unit.target = self.target
            unit.state = self.state
            unit.save_backend(
                user, False, change_action=Change.ACTION_AUTO, author=None
            )
            result = True
        return result

    def save_backend(self, user, propagate=True, change_action=None, author=None):
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
        # This has to be done before changing source/content_hash for template
        if propagate:
            self.propagate(user, change_action, author=author)

        # Return if there was no change
        # We have to explicitly check for fuzzy flag change on monolingual
        # files, where we handle it ourselves without storing to backend
        if self.old_unit.state == self.state and self.old_unit.target == self.target:
            return False

        if self.translation.is_source:
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
        self.original_state = self.state

        # Save updated unit to database
        self.save()

        # Generate Change object for this change
        self.generate_change(user or author, author, change_action)

        if change_action not in (Change.ACTION_UPLOAD, Change.ACTION_AUTO):
            # Update translation stats
            self.translation.invalidate_cache()

            # Update user stats
            author.profile.translated += 1
            author.profile.save()

        # Update related source strings if working on a template
        if self.translation.is_template and self.old_unit.source != self.source:
            self.update_source_units(self.old_unit.source, user or author, author)

        return True

    def update_source_units(self, previous_source, user, author):
        """Update source for units withing same component.

        This is needed when editing template translation for monolingual formats.
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
                unit.original_state = unit.state = STATE_TRANSLATED
                unit.previous_source = ""
            elif (
                unit.original_state == STATE_FUZZY
                and unit.previous_source == self.source
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

    @cached_property
    def suggestions(self):
        """Return all suggestions for this unit."""
        return self.suggestion_set.order()

    def checks(self, values=False):
        """Return all checks names for this unit (even ignored)."""
        result = self.check_set.all()
        if values:
            return result.values_list("check", flat=True)
        return result

    def active_checks(self):
        """Return all active (not ignored) checks for this unit."""
        return self.check_set.filter(ignore=False)

    def get_comments(self):
        """Return list of target comments."""
        return Comment.objects.filter(
            Q(unit=self)
            | (
                Q(unit__translation=self.translation.component.source_translation)
                & Q(unit__id_hash=self.id_hash)
            )
        ).order()

    def run_checks(self, same_state=True, same_content=True):
        """Update checks for this unit."""
        was_change = False
        has_checks = None

        src = self.get_source_plurals()
        tgt = self.get_target_plurals()

        old_checks = set(self.check_set.values_list("check", flat=True))
        create = []

        if self.translation.is_source:
            checks = CHECKS.source.items()
            meth = "check_source"
            args = src, self
        else:
            checks = CHECKS.target.items()
            meth = "check_target"
            args = src, tgt, self

        # Run all checks
        for check, check_obj in checks:
            # Do not remove batch checks in batch processing
            if self.is_batch_update and check_obj.batch_update:
                old_checks.discard(check)
                continue

            # Does the check fire?
            if getattr(check_obj, meth)(*args):
                if check in old_checks:
                    # We already have this check
                    old_checks.remove(check)
                else:
                    # Create new check
                    create.append(Check(unit=self, ignore=False, check=check))
                    was_change = True
                    has_checks = True

        if create:
            Check.objects.bulk_create(create, batch_size=500, ignore_conflicts=True)

        # Delete no longer failing checks
        if old_checks:
            was_change = True
            Check.objects.filter(unit=self, check__in=old_checks).delete()

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
                same_content=True, same_state=True, update_fields=["has_failing_check"]
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
                same_content=True, same_state=True, update_fields=["has_suggestion"]
            )
            return True
        return False

    def update_has_comment(self):
        """Update flag counting comments."""
        has_comment = len(self.get_comments().filter(resolved=False)) > 0
        if has_comment != self.has_comment:
            self.has_comment = has_comment
            self.save(same_content=True, same_state=True, update_fields=["has_comment"])
            return True
        return False

    def nearby(self):
        """Return list of nearby messages based on location."""
        return (
            Unit.objects.prefetch()
            .order_by("position")
            .filter(
                translation=self.translation,
                position__gte=self.position - settings.NEARBY_MESSAGES,
                position__lte=self.position + settings.NEARBY_MESSAGES,
            )
        )

    def nearby_keys(self):
        # Do not show nearby keys on bilingual
        if not self.translation.component.has_template():
            return []
        key = self.translation.keys_cache_key
        key_list = cache.get(key)
        if key_list is None or self.pk not in key_list or True:
            key_list = list(
                Unit.objects.filter(translation=self.translation)
                .order_by("context")
                .values_list("id", flat=True)
            )
            cache.set(key, key_list)
        offset = key_list.index(self.pk)
        nearby = key_list[
            max(offset - settings.NEARBY_MESSAGES, 0) : offset
            + settings.NEARBY_MESSAGES
        ]
        return (
            Unit.objects.filter(translation=self.translation, id__in=nearby)
            .prefetch()
            .order_by("context")
        )

    def shapings(self):
        if not self.shaping:
            return []
        return (
            self.shaping.unit_set.filter(translation=self.translation)
            .prefetch()
            .order_by("context")
        )

    @transaction.atomic
    def translate(
        self, user, new_target, new_state, change_action=None, propagate=True
    ):
        """Store new translation of a unit."""
        # Fetch current copy from database and lock it for update
        self.old_unit = Unit.objects.select_for_update().get(pk=self.pk)

        # Update unit and save it
        if isinstance(new_target, str):
            self.target = new_target
            not_empty = bool(new_target)
        else:
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
            user, change_action=change_action, propagate=propagate
        )

        # Enforced checks can revert the state to needs editing (fuzzy)
        if (
            self.state >= STATE_TRANSLATED
            and self.check_set.filter(
                check__in=self.translation.component.enforced_checks
            ).exists()
        ):
            self.state = self.original_state = STATE_FUZZY
            self.save(same_state=True, same_content=True, update_fields=["state"])

        if (
            propagate
            and user
            and self.target != self.old_unit.target
            and self.state >= STATE_TRANSLATED
        ):
            update_memory(user, self)

        return saved

    def get_all_flags(self, override=None):
        """Return union of own and component flags."""
        return Flags(
            self.translation.all_flags, self.extra_flags, override or self.flags
        )

    @cached_property
    def all_flags(self):
        return self.get_all_flags()

    @cached_property
    def source_info(self):
        """Return related source string object."""
        if self.translation.is_source:
            return self
        return self.translation.component.get_source(self.id_hash)

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
        """Return unique hex identifier.

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
        if self.all_flags.has_value("max-length"):
            return self.all_flags.get_value("max-length")
        if settings.LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH:
            # Fallback to reasonably big value
            return max(100, len(self.get_source_plurals()[0]) * 10)
        return 10000

    def get_target_hash(self):
        return calculate_hash(None, self.target)

    def get_last_content_change(self, silent=False):
        """Wrapper to get last content change metadata.

        Used when commiting pending changes, needs to handle and report inconsistencies
        from past releases.
        """
        from weblate.auth.models import get_anonymous

        try:
            change = self.change_set.content().order_by("-timestamp")[0]
            return change.author or get_anonymous(), change.timestamp
        except IndexError as error:
            if not silent:
                report_error(error, level="error")
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
