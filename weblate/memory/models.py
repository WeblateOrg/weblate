# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import math
import os
import re
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models import Q, Value
from django.db.models.functions import MD5
from django.utils.encoding import force_str
from django.utils.translation import gettext, pgettext
from translate.misc.xml_helpers import getXMLlang, getXMLspace
from translate.storage.tmx import tmxfile
from weblate_schemas import load_schema

from weblate.lang.models import Language
from weblate.memory.utils import (
    CATEGORY_FILE,
    CATEGORY_PRIVATE_OFFSET,
    CATEGORY_SHARED,
    CATEGORY_USER_OFFSET,
    is_valid_memory_entry,
)
from weblate.utils.db import adjust_similarity_threshold, using_postgresql
from weblate.utils.errors import report_error

if TYPE_CHECKING:
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


class MemoryQuerySet(models.QuerySet):
    def filter_type(
        self,
        *,
        user: User | None = None,
        project: Project | None = None,
        use_shared: bool = False,
        from_file: bool = False,
    ):
        base = self
        if "memory_db" in settings.DATABASES:
            base = base.using("memory_db")
        query = Q()
        if from_file:
            query |= Q(from_file=from_file)
        if use_shared:
            query |= Q(shared=use_shared)
        if project:
            query |= Q(project=project)
        if user:
            query |= Q(user=user)
        return base.filter(query)

    def filter(self, *args, **kwargs):
        if using_postgresql():
            # Use MD5 for filtering to utilize MD5 index,
            # MariaDB does not support that, but has partial
            # index on text fields created manually
            for field in ("source", "target", "origin"):
                if field in kwargs:
                    kwargs[f"{field}__md5"] = MD5(Value(kwargs.pop(field)))
                in_field = f"{field}__in"
                if in_field in kwargs:
                    kwargs[f"{field}__md5__in"] = [
                        MD5(Value(value)) for value in kwargs.pop(in_field)
                    ]
        return super().filter(*args, **kwargs)

    def threshold_to_similarity(self, text: str, threshold: int) -> float:
        """
        Convert machinery threshold into PostgreSQL similarity threshold.

        Machinery threshold typical values:

        - 75 machinery
        - 80 automatic translation (default value)
        - 10 search

        PostgreSQL similarity threshold needs to be higher to avoid too slow
        queries.

        We exclude non-word characters while calculating this as those are
        excluded in the trigram matching.
        """
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
        length = min(max(1, len(NON_WORD_RE.sub("", text))), max_length)

        # Apply boost based on square root of length so that it grows faster
        # for shorter strings
        boost = (maximum - base) * math.sqrt(length) / math.sqrt(max_length)

        # Cap result into reasonable limits
        return max(0.6, min(1.0, round(base + boost, decimals)))

    def lookup(
        self,
        source_language,
        target_language,
        text: str,
        user,
        project,
        use_shared,
        threshold: int = 75,
    ):
        # Adjust similarity based on string length to get more relevant matches
        # for long strings
        adjust_similarity_threshold(self.threshold_to_similarity(text, threshold))

        # Actual database query
        return (
            self.prefetch_project()
            .filter_type(
                # Type filtering
                user=user,
                project=project,
                use_shared=use_shared,
                from_file=True,
            )
            .filter(
                # Full-text search on source
                source__search=text,
                # Language filtering
                source_language=source_language,
                target_language=target_language,
            )[:50]
        )

    def prefetch_lang(self):
        return self.prefetch_related("source_language", "target_language")

    def prefetch_project(self):
        return self.select_related("project")


class MemoryManager(models.Manager):
    def import_file(
        self,
        request: AuthenticatedHttpRequest,
        fileobj,
        langmap=None,
        source_language: Language | str | None = None,
        target_language: Language | str | None = None,
        **kwargs,
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
            result = self.import_tmx(request, fileobj, origin, langmap, **kwargs)
        elif extension == ".json":
            result = self.import_json(request, fileobj, origin, **kwargs)
        else:
            result = self.import_other_format(
                request,
                fileobj,
                origin,
                source_language,
                target_language,
                **kwargs,
            )

        if not result:
            raise MemoryImportError(
                gettext("No valid entries found in the uploaded file!")
            )
        return result

    def import_json(
        self, request: AuthenticatedHttpRequest, fileobj, origin=None, **kwargs
    ) -> int:
        # Lazily import as this is expensive
        from jsonschema import validate
        from jsonschema.exceptions import ValidationError

        content = fileobj.read()
        try:
            data = json.loads(force_str(content))
        except json.JSONDecodeError as error:
            report_error("Could not parse memory")
            raise MemoryImportError(
                gettext("Could not parse JSON file: %s") % error
            ) from error
        try:
            validate(data, load_schema("weblate-memory.schema.json"))
        except ValidationError as error:
            report_error("Could not validate memory")
            raise MemoryImportError(
                gettext("Could not parse JSON file: %s") % error
            ) from error
        found = 0
        lang_cache = {}
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
                    **kwargs,
                )
                found += 1
            except Language.DoesNotExist:
                continue
        return found

    def import_tmx(
        self,
        request: AuthenticatedHttpRequest,
        fileobj,
        origin=None,
        langmap=None,
        **kwargs,
    ) -> int:
        if not kwargs:
            kwargs = {"from_file": True}
        try:
            storage = tmxfile.parsefile(fileobj)
        except (SyntaxError, AssertionError) as error:
            report_error("Could not parse")
            raise MemoryImportError(
                gettext("Could not parse TMX file: %s") % error
            ) from error
        header = next(
            storage.document.getroot().iterchildren(storage.namespaced("header"))
        )
        lang_cache = {}
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
                        gettext("Could not find language %s!") % header.get("srclang")
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
                    **kwargs,
                )
                found += 1
        return found

    def import_other_format(
        self,
        request,
        fileobj,
        origin,
        source_language: Language | str | None = None,
        target_language: Language | str | None = None,
        **kwargs,
    ) -> int:
        """
        Import memory from other formats.

        This is a generic function to import memories from other formats.
        It currently supports all formats supported by `try_load` from
        `weblate.formats.auto`.

        """
        from weblate.formats.auto import try_load

        langcache = {}
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
                return Language.objects.get_by_code(language, langcache)
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
                **kwargs,
            )
            count += 1
        return count

    def update_entry(self, **kwargs) -> None:
        if not is_valid_memory_entry(**kwargs):  # pylint: disable=missing-kwoa
            return
        if not self.filter(**kwargs).exists():
            self.create(**kwargs)


class Memory(models.Model):
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
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
        default=None,
    )
    project = models.ForeignKey(
        "trans.Project",
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
        default=None,
    )
    from_file = models.BooleanField(default=False)
    shared = models.BooleanField(default=False)

    objects = MemoryManager.from_queryset(MemoryQuerySet)()

    class Meta:
        verbose_name = "Translation memory entry"
        verbose_name_plural = "Translation memory entries"
        indexes = [
            # Additional indexes are created manually in the migration for full text search
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
            # MySQL/MariaDB does not supports condition and uses full index instead.
            models.Index(
                "from_file",
                condition=Q(from_file=True),
                name="memory_from_file",
            ),
        ]

    def __str__(self) -> str:
        return f"Memory: {self.source_language}:{self.target_language}"

    def get_origin_display(self):
        if self.project:
            text = pgettext("Translation memory category", "Project: {}")
        elif self.user:
            text = pgettext("Translation memory category", "Personal: {}")
        elif self.shared:
            text = pgettext("Translation memory category", "Shared: {}")
        elif self.from_file:
            text = pgettext("Translation memory category", "File: {}")
        else:
            text = "Unknown: {}"
        return text.format(self.origin)

    def get_category(self):
        if self.from_file:
            return CATEGORY_FILE
        if self.shared:
            return CATEGORY_SHARED
        if self.project_id:
            return CATEGORY_PRIVATE_OFFSET + self.project_id
        if self.user_id:
            return CATEGORY_USER_OFFSET + self.user_id
        return 0

    def as_dict(self):
        """Convert to dict suitable for JSON export."""
        return {
            "source": self.source,
            "target": self.target,
            "source_language": self.source_language.code,
            "target_language": self.target_language.code,
            "origin": self.origin,
            "category": self.get_category(),
        }
