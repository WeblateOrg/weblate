# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import functools
import re
import sys

from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import Q
from django.utils.encoding import python_2_unicode_compatible

from whoosh.analysis import (
    LanguageAnalyzer, StandardAnalyzer, StemmingAnalyzer, NgramAnalyzer,
    SimpleAnalyzer,
)
from whoosh.lang import has_stemmer

from weblate.lang.models import Language
from weblate.trans.formats import AutoFormat
from weblate.trans.models.project import Project
from weblate.utils.errors import report_error


SPLIT_RE = re.compile(r'[\s,.:!?]+', re.UNICODE)


class DictionaryManager(models.Manager):
    # pylint: disable=W0232

    def upload(self, request, project, language, fileobj, method):
        """Handle dictionary upload."""
        from weblate.trans.models.change import Change
        store = AutoFormat.parse(fileobj)

        ret = 0

        # process all units
        for dummy, unit in store.iterate_merge(False):
            source = unit.get_source()
            target = unit.get_target()

            # Ignore too long words
            if len(source) > 190 or len(target) > 190:
                continue

            # Get object
            try:
                word, created = self.get_or_create(
                    project=project,
                    language=language,
                    source=source,
                    defaults={
                        'target': target,
                    },
                )
            except self.MultipleObjectsReturned:
                word = self.filter(
                    project=project,
                    language=language,
                    source=source
                )[0]
                created = False

            # Already existing entry found
            if not created:
                # Same as current -> ignore
                if target == word.target:
                    continue
                if method == 'add':
                    # Add word
                    word = self.create(
                        user=request.user,
                        action=Change.ACTION_DICTIONARY_UPLOAD,
                        project=project,
                        language=language,
                        source=source,
                        target=target
                    )
                elif method == 'overwrite':
                    # Update word
                    word.target = target
                    word.save()

            ret += 1

        return ret

    def create(self, user, **kwargs):
        """Create new dictionary object."""
        from weblate.trans.models.change import Change
        action = kwargs.pop('action', Change.ACTION_DICTIONARY_NEW)
        created = super(DictionaryManager, self).create(**kwargs)
        Change.objects.create(
            action=action,
            dictionary=created,
            user=user,
            target=created.target,
        )
        return created

    def get_words(self, unit):
        """Return list of word pairs for an unit."""
        words = set()

        # Prepare analyzers
        # - standard analyzer simply splits words
        # - stemming extracts stems, to catch things like plurals
        analyzers = [
            (SimpleAnalyzer(), True),
            (SimpleAnalyzer(expression=SPLIT_RE, gaps=True), True),
            (StandardAnalyzer(), False),
            (StemmingAnalyzer(), False),
        ]
        source_language = unit.translation.subproject.project.source_language
        lang_code = source_language.base_code()
        # Add per language analyzer if Whoosh has it
        if has_stemmer(lang_code):
            analyzers.append((LanguageAnalyzer(lang_code), False))
        # Add ngram analyzer for languages like Chinese or Japanese
        if source_language.uses_ngram():
            analyzers.append((NgramAnalyzer(4), False))

        # Extract words from all plurals and from context
        for text in unit.get_source_plurals() + [unit.context]:
            for analyzer, combine in analyzers:
                # Some Whoosh analyzers break on unicode
                new_words = []
                try:
                    new_words = [token.text for token in analyzer(text)]
                except (UnicodeDecodeError, IndexError) as error:
                    report_error(error, sys.exc_info())
                words.update(new_words)
                # Add combined string to allow match against multiple word
                # entries allowing to combine up to 5 words
                if combine:
                    words.update(
                        [
                            ' '.join(new_words[x:y])
                            for x in range(len(new_words))
                            for y in range(1, min(x + 6, len(new_words) + 1))
                            if x != y
                        ]
                    )

        # Grab all words in the dictionary
        dictionary = self.filter(
            project=unit.translation.subproject.project,
            language=unit.translation.language
        )

        if len(words) == 0:
            # No extracted words, no dictionary
            dictionary = dictionary.none()
        else:
            # Build the query for fetching the words
            # Can not use __in as we want case insensitive lookup
            dictionary = dictionary.filter(
                functools.reduce(
                    lambda x, y: x | y,
                    [Q(source__iexact=word) for word in words]
                )
            )

        return dictionary


@python_2_unicode_compatible
class Dictionary(models.Model):
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)
    source = models.CharField(max_length=190, db_index=True)
    target = models.CharField(max_length=190)

    objects = DictionaryManager()

    class Meta(object):
        ordering = ['source']
        permissions = (
            ('upload_dictionary', "Can import dictionary"),
        )
        app_label = 'trans'

    def __str__(self):
        return '{0}/{1}: {2} -> {3}'.format(
            self.project,
            self.language,
            self.source,
            self.target
        )

    @models.permalink
    def get_absolute_url(self):
        return (
            'edit_dictionary',
            (),
            {
                'project': self.project.slug,
                'lang': self.language.code,
                'pk': self.id,
            }
        )

    def get_parent_url(self):
        return reverse(
            'show_dictionary',
            kwargs={'project': self.project.slug, 'lang': self.language.code}
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
