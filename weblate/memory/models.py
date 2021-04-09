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

import json
import math
import os
from functools import reduce

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.encoding import force_str
from django.utils.translation import gettext as _
from django.utils.translation import pgettext
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from translate.misc.xml_helpers import getXMLlang, getXMLspace
from translate.storage.tmx import tmxfile
from weblate_schemas import load_schema

from weblate.lang.models import Language
from weblate.memory.utils import (
    CATEGORY_FILE,
    CATEGORY_PRIVATE_OFFSET,
    CATEGORY_SHARED,
    CATEGORY_USER_OFFSET,
)
from weblate.utils.db import adjust_similarity_threshold
from weblate.utils.errors import report_error


class MemoryImportError(Exception):
    pass


def get_node_data(unit, node):
    """Generic implementation of LISAUnit.gettarget."""
    # The language should be present as xml:lang, but in some
    # cases it's there only as lang
    return (
        getXMLlang(node) or node.get("lang"),
        unit.getNodeText(node, getXMLspace(unit.xmlelement, "preserve")),
    )


class MemoryQuerySet(models.QuerySet):
    def filter_type(self, user=None, project=None, use_shared=False, from_file=False):
        query = []
        if from_file:
            query.append(Q(from_file=from_file))
        if use_shared:
            query.append(Q(shared=use_shared))
        if project:
            query.append(Q(project=project))
        if user:
            query.append(Q(user=user))
        return self.filter(reduce(lambda x, y: x | y, query))

    def lookup(
        self, source_language, target_language, text: str, user, project, use_shared
    ):
        # Basic similarity for short strings
        length = len(text)
        threshold = 0.5
        # Adjust similarity based on string length to get more relevant matches
        # for long strings
        if length > 50:
            threshold = 1 - 28.1838 * math.log(0.0443791 * length) / length
        adjust_similarity_threshold(threshold)
        # Actual database query
        return self.filter_type(
            # Type filtering
            user=user,
            project=project,
            use_shared=use_shared,
            from_file=True,
        ).filter(
            # Full-text search on source
            source__search=text,
            # Language filtering
            source_language=source_language,
            target_language=target_language,
        )[
            :50
        ]

    def prefetch_lang(self):
        return self.prefetch_related("source_language", "target_language")


class MemoryManager(models.Manager):
    def import_file(self, request, fileobj, langmap=None, **kwargs):
        origin = os.path.basename(fileobj.name).lower()
        name, extension = os.path.splitext(origin)
        if len(name) > 25:
            origin = f"{name[:25]}...{extension}"

        if extension == ".tmx":
            result = self.import_tmx(request, fileobj, origin, langmap, **kwargs)
        elif extension == ".json":
            result = self.import_json(request, fileobj, origin, **kwargs)
        else:
            raise MemoryImportError(_("Unsupported file!"))
        if not result:
            raise MemoryImportError(_("No valid entries found in the uploaded file!"))
        return result

    def import_json(self, request, fileobj, origin=None, **kwargs):
        content = fileobj.read()
        try:
            data = json.loads(force_str(content))
        except ValueError as error:
            report_error(cause="Failed to parse memory")
            raise MemoryImportError(_("Failed to parse JSON file: {!s}").format(error))
        try:
            validate(data, load_schema("weblate-memory.schema.json"))
        except ValidationError as error:
            report_error(cause="Failed to validate memory")
            raise MemoryImportError(_("Failed to parse JSON file: {!s}").format(error))
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

    def import_tmx(self, request, fileobj, origin=None, langmap=None, **kwargs):
        if not kwargs:
            kwargs = {"from_file": True}
        try:
            storage = tmxfile.parsefile(fileobj)
        except (SyntaxError, AssertionError):
            report_error(cause="Failed to parse")
            raise MemoryImportError(_("Failed to parse TMX file!"))
        header = next(
            storage.document.getroot().iterchildren(storage.namespaced("header"))
        )
        lang_cache = {}
        try:
            source_language = Language.objects.get_by_code(
                header.get("srclang"), lang_cache, langmap
            )
        except Language.DoesNotExist:
            raise MemoryImportError(_("Failed to find source language!"))

        found = 0
        for unit in storage.units:
            # Parse translations (translate-toolkit does not care about
            # languages here, it just picks first and second XML elements)
            translations = {}
            for node in unit.getlanguageNodes():
                lang_code, text = get_node_data(unit, node)
                if not lang_code or not text:
                    continue
                language = Language.objects.get_by_code(lang_code, lang_cache, langmap)
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

    def update_entry(self, **kwargs):
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
    from_file = models.BooleanField(db_index=True, default=False)
    shared = models.BooleanField(db_index=True, default=False)

    objects = MemoryManager.from_queryset(MemoryQuerySet)()

    def __str__(self):
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
