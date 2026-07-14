# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import math
import os
import re
from typing import TYPE_CHECKING, BinaryIO, NotRequired, Self, TypedDict, cast

from django.conf import settings
from django.contrib.postgres import indexes as postgres_indexes
from django.contrib.postgres.search import TrigramDistance, TrigramSimilarity
from django.db import models, router, transaction
from django.db.models import Exists, F, OuterRef, Prefetch, Q, Value
from django.db.models.functions import MD5, Left
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.translation import gettext, gettext_lazy, pgettext, pgettext_lazy
from translate.misc.xml_helpers import getXMLlang, getXMLspace
from translate.storage.tmx import tmxfile
from weblate_schemas import load_schema

from weblate.lang.models import Language
from weblate.machinery.base import MACHINERY_DEFAULT_THRESHOLD
from weblate.memory.utils import (
    CATEGORY_FILE,
    CATEGORY_PRIVATE_OFFSET,
    CATEGORY_SHARED,
    CATEGORY_USER_OFFSET,
    is_valid_memory_entry,
)
from weblate.utils.db import adjust_similarity_threshold
from weblate.utils.errors import report_error

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.trans.models import Project

NON_WORD_RE = re.compile(r"\W")

SUPPORTED_FORMATS = (
    "json",
    "tmx",
    "xliff",
    "po",
    "csv",
)

MIN_SIMILARITY_THRESHOLD = 0.3
MAX_MACHINERY_SIMILARITY_BACKOFF = 0.2
MEMORY_LOOKUP_LIMIT = 50
MEMORY_LOOKUP_PREFIX_LENGTH = 2048


class MemoryDict(TypedDict):
    source: str
    target: str
    source_language: str
    target_language: str
    origin: str
    category: int
    context: NotRequired[str]
    status: NotRequired[int]


class MemoryImportError(Exception):
    pass


def get_node_data(unit, node):
    """
    Return XML unit text.

    Generic implementation of LISAUnit.gettarget.
    """
    # The language should be present as xml:lang, but in some
    # cases it's there only as lang
    return (
        getXMLlang(node) or node.get("lang"),
        unit.getNodeText(node, getXMLspace(unit.xmlelement, "preserve")),
    )


def load_memory_json_data(content: bytes) -> list[MemoryDict]:
    """Load and validate a memory export payload."""
    # Lazily import as this is expensive
    # ruff: ignore[import-outside-top-level]
    from jsonschema import validate

    data = json.loads(force_str(content))
    validate(data, load_schema("weblate-memory.schema.json"))
    return cast("list[MemoryDict]", data)


def load_memory_tmx_store(fileobj: BinaryIO):
    """Parse a TMX file into a translate-toolkit store."""
    return tmxfile.parsefile(fileobj)


class MemoryQuerySet(models.QuerySet["Memory", "Memory"]):
    def using_write_db(self) -> Self:
        if self.db != "memory_db":
            return self
        return self.using(router.db_for_write(self.model) or "default")

    def get_scope_exists(self, scope_query: Q) -> Exists:
        return Exists(
            MemoryScope.objects.using(self.db).filter(
                scope_query, memory_id=OuterRef("pk")
            )
        )

    def get_has_scope_exists(self) -> Exists:
        return Exists(
            MemoryScope.objects.using(self.db).filter(memory_id=OuterRef("pk"))
        )

    def filter_scope(self, scope_query: Q) -> Self:
        return self.alias(
            memory_scope_visible=self.get_scope_exists(scope_query),
        ).filter(memory_scope_visible=True)

    def get_type_scope_query(
        self,
        *,
        user: User | None = None,
        project: Project | None = None,
        use_shared: bool = False,
        from_file: bool = False,
        use_workspace: bool = False,
    ) -> Q:
        query = Q(pk__isnull=True)
        if from_file:
            query |= Q(scope=MemoryScope.SCOPE_GLOBAL_FILE)
        if use_shared:
            query |= Q(
                scope=MemoryScope.SCOPE_SHARED,
                source_project__contribute_shared_tm=True,
            )
        if project:
            query |= Q(scope=MemoryScope.SCOPE_PROJECT, project=project)
            query |= Q(scope=MemoryScope.SCOPE_PROJECT_FILE, project=project)
            if use_workspace and project.effective_use_workspace_tm:
                query |= Q(
                    scope=MemoryScope.SCOPE_WORKSPACE,
                    workspace_id=project.workspace_id,
                ) & Q(
                    workspace_id=F("source_project__workspace_id"),
                    source_project__contribute_workspace_tm=True,
                    source_project__workspace__contribute_workspace_tm=True,
                )
        if user:
            query |= Q(scope=MemoryScope.SCOPE_USER, user=user)
            query |= Q(scope=MemoryScope.SCOPE_USER_FILE, user=user)
        return query

    def filter_type(
        self,
        *,
        user: User | None = None,
        project: Project | None = None,
        use_shared: bool = False,
        from_file: bool = False,
        use_workspace: bool = False,
    ) -> Self:
        base = self
        if "memory_db" in settings.DATABASES:
            base = base.using("memory_db")
        return base.filter_scope(
            base.get_type_scope_query(
                user=user,
                project=project,
                use_shared=use_shared,
                from_file=from_file,
                use_workspace=use_workspace,
            )
        )

    def visible_to_user(self, user: User, *, alias: str) -> Self:
        if user.is_superuser or user.has_perm("memory.manage"):
            return self.filter_scope(Q())

        allowed_projects = user.allowed_projects.using(alias)
        allowed_workspaces = allowed_projects.filter(
            workspace__isnull=False,
            use_workspace_tm=True,
            workspace__use_workspace_tm=True,
        ).values("workspace_id")
        scope_query = (
            Q(scope=MemoryScope.SCOPE_USER, user=user)
            | Q(scope=MemoryScope.SCOPE_USER_FILE, user=user)
            | Q(
                scope=MemoryScope.SCOPE_SHARED,
                source_project__contribute_shared_tm=True,
            )
            | Q(scope=MemoryScope.SCOPE_GLOBAL_FILE)
            | Q(scope=MemoryScope.SCOPE_PROJECT, project__in=allowed_projects)
            | Q(scope=MemoryScope.SCOPE_PROJECT_FILE, project__in=allowed_projects)
            | Q(
                scope=MemoryScope.SCOPE_WORKSPACE,
                workspace__in=allowed_workspaces,
                workspace_id=F("source_project__workspace_id"),
                source_project__contribute_workspace_tm=True,
                source_project__workspace__contribute_workspace_tm=True,
            )
        )
        return self.filter_scope(scope_query)

    def delete_scope(self, scope_query: Q, *, delete_legacy: bool = True) -> None:
        # TODO(2028.1): Remove legacy unscoped cleanup once Weblate no longer
        # supports direct upgrades from 2026 releases. Runtime visibility is
        # scope-only; this exists for the temporary migration/backfill window.
        queryset = self.using_write_db()
        memory_query = queryset.order_by().values("pk")
        if delete_legacy:
            queryset.alias(memory_has_scope=queryset.get_has_scope_exists()).filter(
                memory_has_scope=False
            ).delete()

        matching_scope = MemoryScope.objects.using(queryset.db).filter(
            scope_query, memory_id=OuterRef("pk")
        )
        remaining_scope = (
            MemoryScope.objects.using(queryset.db)
            .filter(memory_id=OuterRef("pk"))
            .exclude(scope_query)
        )
        Memory.objects.using(queryset.db).filter(pk__in=memory_query).alias(
            has_matching_scope=Exists(matching_scope),
            has_remaining_scope=Exists(remaining_scope),
        ).filter(has_matching_scope=True, has_remaining_scope=False).delete()

        MemoryScope.objects.using(queryset.db).filter(
            memory_id__in=memory_query
        ).filter(scope_query).delete()

    def filter(self, *args, **kwargs) -> Self:
        # Use MD5 for filtering to utilize MD5 index
        for field in ("source", "target", "origin"):
            if field in kwargs:
                kwargs[f"{field}__md5"] = MD5(Value(kwargs.pop(field)))
            in_field = f"{field}__in"
            if in_field in kwargs:
                kwargs[f"{field}__md5__in"] = [
                    MD5(Value(value)) for value in kwargs.pop(in_field)
                ]
        return super().filter(*args, **kwargs)

    def get_lookup_length(self, text: str) -> int:
        return len(NON_WORD_RE.sub("", text))

    def threshold_to_similarity(self, text: str, threshold: int) -> float:
        """
        Convert machinery threshold into PostgreSQL similarity threshold.

        Machinery threshold typical values:

        - 80 machinery and automatic translation (default value)
        - 10 search

        PostgreSQL similarity threshold needs to be higher to avoid too slow
        queries.

        We exclude non-word characters while calculating this as those are
        excluded in the trigram matching.
        """
        if threshold >= 100:
            return 1.0

        # Highest similarity we want to get
        high = 0.985
        # Limit the number of decimals to avoid too frequent flipping of the setting
        # inside PostgreSQL
        decimals = 3

        # Maps threshold to a minimal score, approximately:
        #  10 => 0.7
        #  75 => 0.95
        #  80 => 0.96
        # 100 => 1.0
        base = 0.127264 * math.log(24.282 * threshold)
        if base >= high:
            return min(round(base, decimals), 1.0)

        # Allow up to +20% boost based on length
        maximum = min(base * 1.2, high)

        # Measure the length of alphanumeric characters in the text
        max_length = 2000
        length = min(max(1, self.get_lookup_length(text)), max_length)

        # Apply boost based on square root of length so that it grows faster
        # for shorter strings
        boost = (maximum - base) * math.sqrt(length) / math.sqrt(max_length)

        similarity = max(0.6, min(1.0, round(base + boost, decimals)))

        # Short, common strings tend to produce broad trigram matches. Start with
        # a stricter threshold for those so that we avoid expensive fuzzy scans.
        if threshold >= 75:
            if length <= 8:
                similarity = max(similarity, 0.97)
            elif length <= 16:
                similarity = max(similarity, 0.95)

        return similarity

    def minimum_similarity(self, text: str, threshold: int) -> float:
        if threshold >= 100:
            return 1.0
        if threshold >= 75:
            # High-quality machinery lookups should not back off to the broad
            # interactive-search floor; those scans are expensive on large TMs.
            minimum = max(
                MIN_SIMILARITY_THRESHOLD,
                round(
                    self.threshold_to_similarity(text, threshold)
                    - MAX_MACHINERY_SIMILARITY_BACKOFF,
                    3,
                ),
            )
            length = self.get_lookup_length(text)
            if length <= 8:
                return max(minimum, 0.92)
            if length <= 16:
                return max(minimum, 0.90)
            return minimum
        return MIN_SIMILARITY_THRESHOLD

    def get_fuzzy_candidates(self, text: str, limit: int = MEMORY_LOOKUP_LIMIT) -> Self:
        lookup_prefix = text[:MEMORY_LOOKUP_PREFIX_LENGTH]
        return self.alias(
            match_distance=TrigramDistance(
                Left("source", MEMORY_LOOKUP_PREFIX_LENGTH), lookup_prefix
            )
        ).order_by("match_distance", "-status", "pk")[:limit]

    def get_full_source_fuzzy_candidates(
        self,
        text: str,
        *,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
        exclude_ids: Iterable[int] = (),
        limit: int = MEMORY_LOOKUP_LIMIT,
    ) -> Iterator[Memory]:
        if limit <= 0:
            return

        seen_ids = set(exclude_ids)
        yielded = 0

        similarity_threshold = self.threshold_to_similarity(text, threshold)
        minimum_similarity = self.minimum_similarity(text, threshold)

        while similarity_threshold >= minimum_similarity and yielded < limit:
            remaining = limit - yielded
            queryset = self.exclude(pk__in=sorted(seen_ids)) if seen_ids else self
            adjust_similarity_threshold(similarity_threshold, alias=self.db)
            candidates = (
                queryset.filter(source__trgm_search=text)
                .annotate(match_similarity=TrigramSimilarity("source", text))
                .order_by("-match_similarity", "-status", "pk")[:remaining]
            )
            for candidate in candidates:
                if candidate.pk in seen_ids:
                    continue
                seen_ids.add(candidate.pk)
                yielded += 1
                yield candidate
                if yielded >= limit:
                    return

            similarity_threshold = round(similarity_threshold - 0.05, 3)
            if similarity_threshold < minimum_similarity < similarity_threshold + 0.05:
                similarity_threshold = minimum_similarity

    def get_scored_fuzzy_candidates(
        self,
        text: str,
        scorer: Callable[[Memory], int],
        *,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
        limit: int = MEMORY_LOOKUP_LIMIT,
    ) -> list[tuple[int, Memory]]:
        candidates: list[Memory] = list(self.get_fuzzy_candidates(text, limit=limit))
        accepted: list[tuple[int, int, Memory]] = []
        best_quality = threshold - 1

        for candidate in candidates:
            quality = scorer(candidate)
            if quality < threshold:
                continue
            best_quality = max(best_quality, quality)
            accepted.append((quality, len(accepted), candidate))

        if (
            best_quality < 100
            and len(text) > MEMORY_LOOKUP_PREFIX_LENGTH
            and len(candidates) >= limit
        ):
            checked_ids = [candidate.pk for candidate in candidates]
            for candidate in self.get_full_source_fuzzy_candidates(
                text,
                threshold=threshold,
                exclude_ids=checked_ids,
                limit=limit,
            ):
                quality = scorer(candidate)
                if quality < threshold:
                    continue
                best_quality = max(best_quality, quality)
                accepted.append((quality, len(accepted), candidate))

        return [
            (quality, candidate)
            for quality, _sequence, candidate in sorted(
                accepted, key=lambda item: (-item[0], item[1])
            )[:limit]
        ]

    def get_best_fuzzy_match(
        self,
        text: str,
        scorer: Callable[[Memory], int],
        *,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> Memory | None:
        if threshold >= 100:
            return self.filter(source=text).order_by("-status", "id").first()

        candidates = self.get_scored_fuzzy_candidates(text, scorer, threshold=threshold)
        if candidates:
            return candidates[0][1]
        return None

    def get_lookup_queryset(
        self,
        source_language,
        target_language,
        user,
        project,
        use_shared,
    ) -> Self:
        return (
            self.filter_type(
                user=user,
                project=project,
                use_shared=use_shared,
                from_file=True,
                use_workspace=True,
            )
            .prefetch_scopes()
            .filter(
                source_language=source_language,
                target_language=target_language,
            )
        )

    def lookup(
        self,
        source_language,
        target_language,
        text: str,
        user,
        project,
        use_shared,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ):
        queryset = self.get_lookup_queryset(
            source_language, target_language, user, project, use_shared
        )
        if threshold >= 100:
            return queryset.filter(source=text)[:MEMORY_LOOKUP_LIMIT]

        return queryset.get_fuzzy_candidates(text)

    def lookup_full_source(
        self,
        source_language,
        target_language,
        text: str,
        user,
        project,
        use_shared,
        *,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
        exclude_ids: Iterable[int] = (),
    ) -> Iterator[Memory]:
        return self.get_lookup_queryset(
            source_language, target_language, user, project, use_shared
        ).get_full_source_fuzzy_candidates(
            text, threshold=threshold, exclude_ids=exclude_ids
        )

    def prefetch_lang(self) -> Self:
        return self.prefetch_related("source_language", "target_language")

    def prefetch_scopes(self) -> Self:
        return self.prefetch_related(
            Prefetch(
                "scopes",
                queryset=MemoryScope.objects.using(self.db).select_related(
                    "project",
                    "workspace",
                    "source_project",
                ),
            )
        )


class MemoryManager(models.Manager["Memory"]):
    _hints: dict[str, models.Model]

    def get_queryset(self) -> MemoryQuerySet:
        return MemoryQuerySet(model=self.model, using=self._db, hints=self._hints)

    def import_file(
        self,
        *,
        request: AuthenticatedHttpRequest | None,
        fileobj: BinaryIO,
        langmap: dict[str, str] | None = None,
        source_language: Language | str | None = None,
        target_language: Language | str | None = None,
        user: User | None = None,
        project: Project | None = None,
        from_file: bool = True,
    ):
        origin = os.path.basename(fileobj.name).lower()
        name, extension = os.path.splitext(origin)

        if extension.lower().strip(".") not in SUPPORTED_FORMATS:
            raise MemoryImportError(
                gettext("Unsupported file extension: %s") % extension
            )

        if len(name) > 25:
            origin = f"{name[:25]}...{extension}"

        if extension == ".tmx":
            result = self.import_tmx(
                request=request,
                fileobj=fileobj,
                origin=origin,
                langmap=langmap,
                user=user,
                project=project,
                from_file=True,
                status=Memory.STATUS_ACTIVE,
            )
        elif extension == ".json":
            result = self.import_json(
                request=request,
                fileobj=fileobj,
                origin=origin,
                user=user,
                project=project,
                from_file=True,
                status=Memory.STATUS_ACTIVE,
            )
        else:
            result = self.import_other_format(
                request=request,
                fileobj=fileobj,
                origin=origin,
                source_language=source_language,
                target_language=target_language,
                user=user,
                project=project,
                from_file=True,
                status=Memory.STATUS_ACTIVE,
            )

        if not result:
            raise MemoryImportError(
                gettext("No valid entries found in the uploaded file!")
            )
        return result

    def import_json(
        self,
        *,
        request: AuthenticatedHttpRequest | None,
        fileobj: BinaryIO,
        origin: str,
        user: User | None = None,
        project: Project | None = None,
        from_file: bool = False,
        status: int = 0,
    ) -> int:
        # Lazily import as this is expensive
        # ruff: ignore[import-outside-top-level]
        from jsonschema.exceptions import ValidationError

        try:
            data = load_memory_json_data(fileobj.read())
        except json.JSONDecodeError as error:
            report_error("Could not parse memory")
            raise MemoryImportError(
                gettext("Could not parse JSON file: %s") % error
            ) from error
        except ValidationError as error:
            report_error("Could not validate memory")
            raise MemoryImportError(
                gettext("Could not parse JSON file: %s") % error
            ) from error
        found = 0
        lang_cache: dict[str, Language] = {}
        for entry in data:
            try:
                self.update_entry(
                    source_language=Language.objects.get_by_code(
                        entry["source_language"], lang_cache
                    ),
                    target_language=Language.objects.get_by_code(
                        entry["target_language"], lang_cache
                    ),
                    source=entry["source"],
                    target=entry["target"],
                    origin=origin,
                    context=entry.get("context", ""),
                    user=user,
                    project=project,
                    from_file=from_file,
                    status=status,
                    shared=False,
                )
                found += 1
            except Language.DoesNotExist:
                continue
        return found

    def import_tmx(
        self,
        *,
        request: AuthenticatedHttpRequest | None,
        fileobj: BinaryIO,
        origin: str,
        langmap: dict[str, str] | None = None,
        user: User | None = None,
        project: Project | None = None,
        from_file: bool = False,
        status: int = 0,
    ) -> int:
        try:
            storage = load_memory_tmx_store(fileobj)
        except (SyntaxError, AssertionError) as error:
            report_error("Could not parse")
            raise MemoryImportError(
                gettext("Could not parse TMX file: %s") % error
            ) from error
        header = next(
            storage.document.getroot().iterchildren(storage.namespaced("header")),
            None,
        )
        if header is None:
            raise MemoryImportError(gettext("Header missing in the TMX file!"))
        lang_cache: dict[str, Language] = {}
        srclang = header.get("srclang")
        if not srclang:
            raise MemoryImportError(
                gettext("Source language not defined in the TMX file!")
            )
        try:
            source_language = Language.objects.get_by_code(srclang, lang_cache, langmap)
        except Language.DoesNotExist as error:
            raise MemoryImportError(
                gettext("Could not find language %s!") % srclang
            ) from error

        found = 0
        for unit in storage.units:
            # Parse translations (translate-toolkit does not care about
            # languages here, it just picks first and second XML elements)
            translations = {}
            for node in unit.getlanguageNodes():
                lang_code, text = get_node_data(unit, node)
                if not lang_code or not text:
                    continue
                try:
                    language = Language.objects.get_by_code(
                        lang_code, lang_cache, langmap
                    )
                except Language.DoesNotExist as error:
                    raise MemoryImportError(
                        gettext("Could not find language %s!") % lang_code
                    ) from error
                translations[language.code] = text

            try:
                source = translations.pop(source_language.code)
            except KeyError:
                # Skip if source language is not present
                continue

            for lang, text in translations.items():
                self.update_entry(
                    source_language=source_language,
                    target_language=Language.objects.get_by_code(
                        lang, lang_cache, langmap
                    ),
                    source=source,
                    target=text,
                    origin=origin,
                    context=unit.getcontext(),
                    user=user,
                    project=project,
                    from_file=from_file,
                    status=status,
                    shared=False,
                )
                found += 1
        return found

    def import_other_format(
        self,
        *,
        request: AuthenticatedHttpRequest | None,
        fileobj: BinaryIO,
        origin: str,
        source_language: Language | str | None = None,
        target_language: Language | str | None = None,
        user: User | None = None,
        project: Project | None = None,
        from_file: bool = False,
        status: int = 0,
    ) -> int:
        """
        Import memory from other formats.

        This is a generic function to import memories from other formats.
        It currently supports all formats supported by `try_load` from
        `weblate.formats.auto`.

        """
        # ruff: ignore[import-outside-top-level]
        from weblate.formats.auto import try_load

        lang_cache: dict[str, Language] = {}
        try:
            storage = try_load(origin, fileobj.read(), None, None)
        except Exception as error:
            report_error("Could not parse memory")
            raise MemoryImportError(gettext("Unsupported file!")) from error

        if storage.monolingual is True:
            raise MemoryImportError(
                gettext("Monolingual format not supported for memory upload")
            )

        def get_language(language: Language | str | None) -> Language:
            """Get a language object based on the given code."""
            if isinstance(language, Language):
                return language

            if not language:
                raise MemoryImportError(
                    gettext("Missing source or target language in file!")
                )
            try:
                return Language.objects.get_by_code(language, lang_cache)
            except Language.DoesNotExist as error:
                raise MemoryImportError(
                    gettext("Could not find language %s!") % language
                ) from error

        source_language = get_language(storage.source_language or source_language)
        target_language = get_language(storage.language_code or target_language)

        count = 0
        for _unused, unit in storage.iterate_merge("", only_translated=True):
            self.update_entry(
                source_language=source_language,
                target_language=target_language,
                source=unit.source,
                target=unit.target,
                origin=origin,
                context=unit.context,
                user=user,
                project=project,
                from_file=from_file,
                status=status,
                shared=False,
            )
            count += 1
        return count

    def update_entry(
        self,
        *,
        source: str,
        target: str,
        source_language: Language,
        target_language: Language,
        context: str,
        origin: str,
        status: int,
        user: User | None,
        project: Project | None,
        from_file: bool,
        shared: bool,
    ) -> None:
        if not is_valid_memory_entry(
            source=source,
            target=target,
            status=status,
            source_language=source_language,
            target_language=target_language,
            origin=origin,
            context=context,
            legacy_user=user,
            legacy_project=project,
            legacy_from_file=from_file,
            legacy_shared=shared,
        ):
            return
        lookup = {
            "source": source,
            "target": target,
            "status": status,
            "source_language": source_language,
            "target_language": target_language,
            "origin": origin,
            "context": context,
        }
        write_queryset = self.get_queryset().using_write_db()
        existing = write_queryset.filter(**lookup)
        write_db = write_queryset.db
        scope_manager = MemoryScope.objects.db_manager(write_db)
        scope = MemoryScope.objects.get_for_update_entry(
            user=user,
            project=project,
            from_file=from_file,
            shared=shared,
        )
        if scope is not None:
            if existing.filter_scope(
                MemoryScope.objects.get_scope_query(scope)
            ).exists():
                return
            memory = existing.filter_scope(Q()).order_by("id").first()
            if memory is not None:
                memory.normalize_legacy_owner()
                scope.memory = memory
                scope_manager.bulk_create([scope], ignore_conflicts=True)
                return

        with transaction.atomic(using=write_db):
            memory = write_queryset.create(
                source=source,
                target=target,
                status=status,
                source_language=source_language,
                target_language=target_language,
                origin=origin,
                context=context,
            )
            if scope is not None:
                scope.memory = memory
                scope_manager.bulk_create([scope], ignore_conflicts=True)


class Memory(models.Model):
    # Transient scope metadata used before MemoryScope rows are bulk-created.
    # The source-project ID is migration-only; normal runtime writes use
    # pending_scopes instead of the legacy owner columns.
    scope_source_project_id: int | None = None
    pending_scopes: list[MemoryScope] | None = None
    # Transient per-instance cache for serializers that derive legacy API fields
    # from prefetched scope rows.
    scope_list: list[MemoryScope] | None = None

    # Status choices for the memory entry
    STATUS_PENDING = 0
    STATUS_ACTIVE = 1
    STATUS_CHOICES = (
        (STATUS_PENDING, gettext_lazy("Pending")),
        (STATUS_ACTIVE, gettext_lazy("Active")),
    )

    source_language = models.ForeignKey(
        "lang.Language",
        on_delete=models.deletion.CASCADE,
        related_name="memory_source_set",
    )
    target_language = models.ForeignKey(
        "lang.Language",
        on_delete=models.deletion.CASCADE,
        related_name="memory_target_set",
    )
    source = models.TextField()
    target = models.TextField()
    origin = models.TextField()
    context = models.TextField(default="", blank=True)
    # Scope rows own translation-memory visibility. These legacy columns are
    # kept only for compatibility with unbackfilled rows and import/backfill
    # code paths during the supported upgrade window.
    # TODO(2028.1): Remove legacy ownership columns and backfill/import
    # compatibility once Weblate no longer supports direct upgrades from 2026
    # releases.
    legacy_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
        default=None,
        related_name="+",
    )
    legacy_project = models.ForeignKey(
        "trans.Project",
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
        default=None,
        related_name="+",
    )
    legacy_from_file = models.BooleanField(default=False)
    legacy_shared = models.BooleanField(default=False)
    status = models.IntegerField(
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    objects = MemoryManager.from_queryset(MemoryQuerySet)()

    class Meta:
        verbose_name = "Translation memory entry"
        verbose_name_plural = "Translation memory entries"
        # ruff: ignore[mutable-class-default]
        indexes = [
            # Use MD5 to index text fields, applied in MemoryQuerySet.filter
            models.Index(
                MD5("origin"),
                MD5("source"),
                MD5("target"),
                "source_language",
                "target_language",
                name="memory_md5_index",
            ),
            # Partial index for to optimize lookup for file based entries
            models.Index(
                "legacy_from_file",
                condition=Q(legacy_from_file=True),
                name="memory_from_file",
            ),
            postgres_indexes.GinIndex(
                postgres_indexes.OpClass(models.F("source"), name="gin_trgm_ops"),
                models.F("target_language"),
                models.F("source_language"),
                name="memory_source_trgm",
            ),
            postgres_indexes.GistIndex(
                models.F("source_language"),
                models.F("target_language"),
                postgres_indexes.OpClass(
                    Left("source", MEMORY_LOOKUP_PREFIX_LENGTH), name="gist_trgm_ops"
                ),
                name="memory_source_gist_prefix",
            ),
        ]

    def __str__(self) -> str:
        return f"Memory: {self.source_language}:{self.target_language}"

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)
        if not getattr(self, "_skip_scope_sync", False):
            MemoryScope.objects.create_for_memory(self)

    def normalize_legacy_owner(self) -> None:
        (
            Memory.objects.using(self._state.db or "default")
            .using_write_db()
            .filter(pk=self.pk)
            .update(
                legacy_project=None,
                legacy_user=None,
                legacy_shared=False,
                legacy_from_file=False,
            )
        )
        self.legacy_project_id = None
        self.legacy_user_id = None
        self.legacy_shared = False
        self.legacy_from_file = False

    def get_scope_list(self) -> list[MemoryScope]:
        if self.scope_list is None:
            self.scope_list = list(self.scopes.all())
        return self.scope_list

    def get_context_origin_display(
        self,
        scopes: list[MemoryScope],
        *,
        project: Project | None,
        user: User | None,
    ) -> str | None:
        if project is not None and any(
            scope.scope in {MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE}
            and scope.project_id == project.id
            for scope in scopes
        ):
            return pgettext("Translation memory category", "Project: {}")
        if user is not None and any(
            scope.scope in {MemoryScope.SCOPE_USER, MemoryScope.SCOPE_USER_FILE}
            and scope.user_id == user.id
            for scope in scopes
        ):
            return pgettext("Translation memory category", "Personal: {}")
        if project is not None and project.use_shared_tm:
            for scope in scopes:
                if scope.scope != MemoryScope.SCOPE_SHARED:
                    continue
                source_project = scope.source_project
                if source_project is not None and source_project.contribute_shared_tm:
                    return pgettext("Translation memory category", "Shared: {}")
        if any(scope.scope == MemoryScope.SCOPE_GLOBAL_FILE for scope in scopes):
            return pgettext("Translation memory category", "File: {}")
        if project is not None and project.effective_use_workspace_tm:
            for scope in scopes:
                if (
                    scope.scope != MemoryScope.SCOPE_WORKSPACE
                    or scope.workspace_id != project.workspace_id
                ):
                    continue
                source_project = scope.source_project
                workspace = scope.workspace
                if (
                    source_project is not None
                    and source_project.workspace_id == project.workspace_id
                    and source_project.contribute_workspace_tm
                    and workspace is not None
                    and workspace.contribute_workspace_tm
                ):
                    return pgettext("Translation memory category", "Workspace: {}")
        return None

    def get_origin_display(
        self,
        *,
        project: Project | None = None,
        user: User | None = None,
    ) -> str:
        scopes = self.get_scope_list()
        text = self.get_context_origin_display(scopes, project=project, user=user)
        if text is not None:
            return text.format(self.origin)
        if any(
            scope.scope in {MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE}
            for scope in scopes
        ):
            text = pgettext("Translation memory category", "Project: {}")
        elif any(
            scope.scope in {MemoryScope.SCOPE_USER, MemoryScope.SCOPE_USER_FILE}
            for scope in scopes
        ):
            text = pgettext("Translation memory category", "Personal: {}")
        elif any(scope.scope == MemoryScope.SCOPE_SHARED for scope in scopes):
            text = pgettext("Translation memory category", "Shared: {}")
        elif any(scope.scope == MemoryScope.SCOPE_GLOBAL_FILE for scope in scopes):
            text = pgettext("Translation memory category", "File: {}")
        elif any(scope.scope == MemoryScope.SCOPE_WORKSPACE for scope in scopes):
            text = pgettext("Translation memory category", "Workspace: {}")
        else:
            text = "Unknown: {}"
        return text.format(self.origin)

    def get_category(self) -> int:
        return self.get_categories()[0]

    def get_categories(self) -> list[int]:
        categories = []
        has_workspace = False
        for scope in self.get_scope_list():
            if (
                scope.scope
                in {MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE}
                and scope.project_id is not None
            ):
                categories.append(CATEGORY_PRIVATE_OFFSET + scope.project_id)
            if (
                scope.scope in {MemoryScope.SCOPE_USER, MemoryScope.SCOPE_USER_FILE}
                and scope.user_id is not None
            ):
                categories.append(CATEGORY_USER_OFFSET + scope.user_id)
            if scope.scope == MemoryScope.SCOPE_SHARED:
                categories.append(CATEGORY_SHARED)
            if scope.scope == MemoryScope.SCOPE_GLOBAL_FILE:
                categories.append(CATEGORY_FILE)
            if scope.scope == MemoryScope.SCOPE_WORKSPACE:
                has_workspace = True
        if has_workspace:
            # The legacy JSON memory format has no workspace category. Keep
            # using 0 for workspace exports until the format grows explicit
            # scope metadata.
            categories.append(0)
        return list(dict.fromkeys(categories)) or [0]

    def as_dict(self, *, category: int | None = None) -> MemoryDict:
        """Convert to dict suitable for JSON export."""
        return {
            "source": self.source,
            "context": self.context,
            "target": self.target,
            "source_language": self.source_language.code,
            "target_language": self.target_language.code,
            "origin": self.origin,
            "category": self.get_category() if category is None else category,
            "status": self.status,
        }

    def as_dicts(self) -> list[MemoryDict]:
        """Convert to JSON export dictionaries for all represented scopes."""
        return [self.as_dict(category=category) for category in self.get_categories()]


class MemoryScopeManager(models.Manager["MemoryScope"]):
    def get_write_db_for_memory(self, memory: Memory | None = None) -> str:
        if self._db is not None and self._db != "memory_db":
            return self._db
        memory_db = None if memory is None else memory._state.db  # ruff: ignore[private-member-access]
        if memory_db is not None and memory_db != "memory_db":
            return memory_db
        return router.db_for_write(self.model, instance=memory) or "default"

    def get_for_update_entry(
        self,
        *,
        user: User | None,
        project: Project | None,
        from_file: bool,
        shared: bool,
    ) -> MemoryScope | None:
        if from_file:
            if project is not None:
                return MemoryScope(
                    scope=MemoryScope.SCOPE_PROJECT_FILE, project=project
                )
            if user is not None:
                return MemoryScope(scope=MemoryScope.SCOPE_USER_FILE, user=user)
            return MemoryScope(scope=MemoryScope.SCOPE_GLOBAL_FILE)
        if project is not None:
            return MemoryScope(scope=MemoryScope.SCOPE_PROJECT, project=project)
        if shared:
            return MemoryScope(scope=MemoryScope.SCOPE_SHARED)
        if user is not None:
            return MemoryScope(scope=MemoryScope.SCOPE_USER, user=user)
        return None

    def get_scope_query(self, scope: MemoryScope) -> Q:
        if scope.scope in {MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE}:
            return Q(scope=scope.scope, project_id=scope.project_id)
        if scope.scope == MemoryScope.SCOPE_WORKSPACE:
            return Q(
                scope=scope.scope,
                workspace_id=scope.workspace_id,
                source_project_id=scope.source_project_id,
            )
        if scope.scope in {MemoryScope.SCOPE_USER, MemoryScope.SCOPE_USER_FILE}:
            return Q(scope=scope.scope, user_id=scope.user_id)
        if scope.scope == MemoryScope.SCOPE_SHARED:
            return Q(scope=scope.scope, source_project_id=scope.source_project_id)
        return Q(scope=scope.scope)

    def get_for_memory(self, memory: Memory) -> list[MemoryScope]:
        if memory.pending_scopes is not None:
            return [
                MemoryScope(
                    memory=memory,
                    scope=scope.scope,
                    project_id=scope.project_id,
                    workspace_id=scope.workspace_id,
                    source_project_id=scope.source_project_id,
                    user_id=scope.user_id,
                )
                for scope in memory.pending_scopes
            ]

        scopes = []
        if memory.legacy_from_file:
            if memory.legacy_project_id:
                scopes.append(
                    MemoryScope(
                        memory=memory,
                        scope=MemoryScope.SCOPE_PROJECT_FILE,
                        project_id=memory.legacy_project_id,
                    )
                )
            elif memory.legacy_user_id:
                scopes.append(
                    MemoryScope(
                        memory=memory,
                        scope=MemoryScope.SCOPE_USER_FILE,
                        user_id=memory.legacy_user_id,
                    )
                )
            else:
                scopes.append(
                    MemoryScope(memory=memory, scope=MemoryScope.SCOPE_GLOBAL_FILE)
                )
        else:
            if memory.legacy_project_id:
                scopes.append(
                    MemoryScope(
                        memory=memory,
                        scope=MemoryScope.SCOPE_PROJECT,
                        project_id=memory.legacy_project_id,
                    )
                )
            if memory.legacy_shared:
                # Source-project inference runs before scope creation and can
                # recover renamed projects from history. Runtime visibility is
                # still gated by the recovered source project settings.
                scopes.append(
                    MemoryScope(
                        memory=memory,
                        scope=MemoryScope.SCOPE_SHARED,
                        source_project_id=memory.scope_source_project_id,
                    )
                )
            if memory.legacy_user_id:
                scopes.append(
                    MemoryScope(
                        memory=memory,
                        scope=MemoryScope.SCOPE_USER,
                        user_id=memory.legacy_user_id,
                    )
                )
        return scopes

    def create_for_memory(self, memory: Memory) -> None:
        scopes = self.get_for_memory(memory)
        if scopes:
            self.db_manager(self.get_write_db_for_memory(memory)).bulk_create(
                scopes, ignore_conflicts=True
            )

    def bulk_create_for_memories(self, memories) -> None:
        memories = list(memories)
        scopes = []
        for memory in memories:
            scopes.extend(self.get_for_memory(memory))
        if scopes:
            memory = memories[0] if memories else None
            self.db_manager(self.get_write_db_for_memory(memory)).bulk_create(
                scopes, ignore_conflicts=True
            )


class MemoryScopeChoices(models.IntegerChoices):
    PROJECT = 1, pgettext_lazy("Translation memory scope", "Project")
    WORKSPACE = 2, pgettext_lazy("Translation memory scope", "Workspace")
    SHARED = 3, pgettext_lazy("Translation memory scope", "Shared")
    USER = 4, pgettext_lazy("Translation memory scope", "Personal")
    GLOBAL_FILE = 5, pgettext_lazy("Translation memory scope", "File")
    PROJECT_FILE = 6, pgettext_lazy("Translation memory scope", "Project file")
    USER_FILE = 7, pgettext_lazy("Translation memory scope", "Personal file")


class MemoryScope(models.Model):
    # Scope is stored separately from Memory because one canonical translation
    # memory entry can be visible through multiple independent scopes. Keeping
    # scopes as rows avoids duplicating source/target text for project, shared,
    # workspace, and personal memory, and lets lookup use indexed scope-existence
    # checks instead of broad OR predicates over nullable fields.
    SCOPE_PROJECT = MemoryScopeChoices.PROJECT
    SCOPE_WORKSPACE = MemoryScopeChoices.WORKSPACE
    SCOPE_SHARED = MemoryScopeChoices.SHARED
    SCOPE_USER = MemoryScopeChoices.USER
    SCOPE_GLOBAL_FILE = MemoryScopeChoices.GLOBAL_FILE
    SCOPE_PROJECT_FILE = MemoryScopeChoices.PROJECT_FILE
    SCOPE_USER_FILE = MemoryScopeChoices.USER_FILE

    memory = models.ForeignKey(
        Memory, on_delete=models.deletion.CASCADE, related_name="scopes"
    )
    scope = models.PositiveSmallIntegerField(choices=MemoryScopeChoices)
    project = models.ForeignKey(
        "trans.Project",
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
    )
    source_project = models.ForeignKey(
        "trans.Project",
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
    )

    objects = MemoryScopeManager()

    class Meta:
        verbose_name = "Translation memory scope"
        verbose_name_plural = "Translation memory scopes"
        # ruff: ignore[mutable-class-default]
        indexes = [
            models.Index(fields=["scope", "memory"], name="memory_scope_scope_memory"),
            models.Index(
                fields=["scope", "project", "memory"], name="memory_scope_project"
            ),
            models.Index(
                fields=["scope", "workspace", "memory"],
                name="memory_scope_workspace",
            ),
            models.Index(
                fields=["scope", "source_project", "memory"],
                name="memory_scope_source_project",
            ),
            models.Index(
                fields=["scope", "workspace", "source_project", "memory"],
                name="memory_scope_workspace_source",
            ),
            models.Index(fields=["scope", "user", "memory"], name="memory_scope_user"),
        ]
        # ruff: ignore[mutable-class-default]
        constraints = [
            models.UniqueConstraint(
                fields=("memory", "scope", "project"),
                condition=Q(
                    scope__in=(
                        MemoryScopeChoices.PROJECT,
                        MemoryScopeChoices.PROJECT_FILE,
                    ),
                    project__isnull=False,
                ),
                name="memory_scope_unique_project",
            ),
            models.UniqueConstraint(
                fields=("memory", "scope", "workspace", "source_project"),
                condition=Q(
                    scope=MemoryScopeChoices.WORKSPACE,
                    workspace__isnull=False,
                    source_project__isnull=False,
                ),
                name="memory_scope_unique_workspace",
            ),
            models.UniqueConstraint(
                fields=("memory", "scope", "workspace"),
                condition=Q(
                    scope=MemoryScopeChoices.WORKSPACE,
                    workspace__isnull=False,
                    source_project__isnull=True,
                ),
                name="memory_scope_workspace_null",
            ),
            models.UniqueConstraint(
                fields=("memory", "scope", "user"),
                condition=Q(
                    scope__in=(MemoryScopeChoices.USER, MemoryScopeChoices.USER_FILE),
                    user__isnull=False,
                ),
                name="memory_scope_unique_user",
            ),
            models.UniqueConstraint(
                fields=("memory", "scope"),
                condition=Q(scope=MemoryScopeChoices.GLOBAL_FILE),
                name="memory_scope_unique_global",
            ),
            models.UniqueConstraint(
                fields=("memory", "scope", "source_project"),
                condition=Q(
                    scope=MemoryScopeChoices.SHARED,
                    source_project__isnull=False,
                ),
                name="memory_scope_unique_shared",
            ),
            models.UniqueConstraint(
                fields=("memory", "scope"),
                condition=Q(
                    scope=MemoryScopeChoices.SHARED,
                    source_project__isnull=True,
                ),
                name="memory_scope_shared_null",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.memory_id}:{self.scope}"


class MemoryScopeMigrationState(models.Model):
    # TODO(2028.1): Remove this background TM scope backfill state once Weblate
    # no longer supports direct upgrades from 2026 releases.
    name = models.CharField(max_length=50, primary_key=True)
    last_memory_id = models.IntegerField(default=0)
    completed = models.BooleanField(default=False)
    updated = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Translation memory scope migration state"
        verbose_name_plural = "Translation memory scope migration states"

    def __str__(self) -> str:
        return self.name
