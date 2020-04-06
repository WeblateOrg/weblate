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
from functools import reduce
from itertools import islice

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from whoosh.analysis import LanguageAnalyzer, NgramAnalyzer, SimpleAnalyzer
from whoosh.analysis.filters import StopFilter
from whoosh.lang import NoStopWords

from weblate.checks.same import strip_string
from weblate.formats.auto import AutodetectFormat
from weblate.lang.models import Language
from weblate.trans.defines import GLOSSARY_LENGTH
from weblate.trans.models.project import Project
from weblate.utils.db import re_escape
from weblate.utils.errors import report_error

SPLIT_RE = re.compile(r"[\s,.:!?]+", re.UNICODE)


class DictionaryManager(models.Manager):
    # pylint: disable=no-init

    def upload(self, request, project, language, fileobj, method):
        """Handle dictionary upload."""
        from weblate.trans.models.change import Change

        store = AutodetectFormat.parse(fileobj)

        ret = 0

        # process all units
        for _unused, unit in store.iterate_merge(False):
            source = unit.source
            target = unit.target

            # Ignore too long words
            if len(source) > 190 or len(target) > 190:
                continue

            # Get object
            try:
                word, created = self.get_or_create(
                    project=project,
                    language=language,
                    source=source,
                    defaults={"target": target},
                )
            except Dictionary.MultipleObjectsReturned:
                word = self.filter(project=project, language=language, source=source)[0]
                created = False

            # Already existing entry found
            if not created:
                # Same as current -> ignore
                if target == word.target:
                    continue
                if method == "add":
                    # Add word
                    self.create(
                        user=request.user,
                        action=Change.ACTION_DICTIONARY_UPLOAD,
                        project=project,
                        language=language,
                        source=source,
                        target=target,
                    )
                elif method == "overwrite":
                    # Update word
                    word.target = target
                    word.save()

            ret += 1

        return ret

    def create(self, user, **kwargs):
        """Create new dictionary object."""
        from weblate.trans.models.change import Change

        action = kwargs.pop("action", Change.ACTION_DICTIONARY_NEW)
        created = super().create(**kwargs)
        Change.objects.create(
            action=action, dictionary=created, user=user, target=created.target
        )
        return created


class DictionaryQuerySet(models.QuerySet):
    # pylint: disable=no-init

    def get_words(self, unit):
        """Return list of word pairs for an unit."""
        words = set()
        source_language = unit.translation.component.project.source_language

        # Filters stop words for a language
        try:
            stopfilter = StopFilter(lang=source_language.base_code)
        except NoStopWords:
            stopfilter = StopFilter()

        # Prepare analyzers
        # - simple analyzer just splits words based on regexp
        # - language analyzer if available (it is for English)
        analyzers = [
            SimpleAnalyzer(expression=SPLIT_RE, gaps=True) | stopfilter,
            LanguageAnalyzer(source_language.base_code),
        ]

        # Add ngram analyzer for languages like Chinese or Japanese
        if source_language.uses_ngram():
            analyzers.append(NgramAnalyzer(4))

        # Extract words from all plurals and from context
        flags = unit.all_flags
        for text in unit.get_source_plurals() + [unit.context]:
            text = strip_string(text, flags).lower()
            for analyzer in analyzers:
                # Some Whoosh analyzers break on unicode
                try:
                    words.update(token.text for token in analyzer(text))
                except (UnicodeDecodeError, IndexError):
                    report_error(cause="Dictionary words parsing")
                if len(words) > 1000:
                    break
            if len(words) > 1000:
                break

        if "" in words:
            words.remove("")

        if not words:
            # No extracted words, no dictionary
            return self.none()

        # Build the query for fetching the words
        # We want case insensitive lookup
        words = islice(words, 1000)
        if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
            # Use regex as that is utilizing pg_trgm index
            results = self.filter(
                source__iregex=r"(^|[ \t\n\r\f\v])({0})($|[ \t\n\r\f\v])".format(
                    "|".join(re_escape(word) for word in words)
                ),
            )
        else:
            # MySQL
            results = self.filter(
                reduce(
                    lambda x, y: x | y,
                    (models.Q(source__search=word) for word in words),
                ),
            )

        return results.filter(
            project=unit.translation.component.project,
            language=unit.translation.language,
        )

    def order(self):
        return self.order_by(Lower("source"))


class Dictionary(models.Model):
    project = models.ForeignKey(Project, on_delete=models.deletion.CASCADE)
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)
    source = models.CharField(max_length=GLOSSARY_LENGTH, db_index=True)
    target = models.CharField(max_length=GLOSSARY_LENGTH)

    objects = DictionaryManager.from_queryset(DictionaryQuerySet)()

    class Meta:
        app_label = "trans"

    def __str__(self):
        return "{0}/{1}: {2} -> {3}".format(
            self.project, self.language, self.source, self.target
        )

    def get_absolute_url(self):
        return reverse(
            "edit_dictionary",
            kwargs={
                "project": self.project.slug,
                "lang": self.language.code,
                "pk": self.id,
            },
        )

    def get_parent_url(self):
        return reverse(
            "show_dictionary",
            kwargs={"project": self.project.slug, "lang": self.language.code},
        )

    def edit(self, request, source, target):
        """Edit word in a dictionary."""
        from weblate.trans.models.change import Change

        self.source = source
        self.target = target
        self.save()
        Change.objects.create(
            action=Change.ACTION_DICTIONARY_EDIT,
            dictionary=self,
            user=request.user,
            target=self.target,
        )
