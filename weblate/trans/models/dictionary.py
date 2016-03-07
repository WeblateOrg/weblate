# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import sys

from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import Q
from django.utils.encoding import force_text, python_2_unicode_compatible

from whoosh.analysis import (
    LanguageAnalyzer, StandardAnalyzer, StemmingAnalyzer, NgramAnalyzer
)
from whoosh.lang import has_stemmer

from weblate.lang.models import Language
from weblate.trans.formats import AutoFormat
from weblate.trans.models.project import Project
from weblate.trans.util import report_error


class DictionaryManager(models.Manager):
    # pylint: disable=W0232

    def upload(self, request, project, language, fileobj, method):
        '''
        Handles dictionary upload.
        '''
        from weblate.trans.models.changes import Change
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
            word, created = self.get_or_create(
                project=project,
                language=language,
                source=source,
                defaults={
                    'target': target,
                },
            )

            # Already existing entry found
            if not created:
                # Same as current -> ignore
                if target == word.target:
                    continue
                if method == 'add':
                    # Add word
                    word = self.create(
                        request,
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

    def create(self, request, **kwargs):
        '''
        Creates new dictionary object.
        '''
        from weblate.trans.models.changes import Change
        action = kwargs.pop('action', Change.ACTION_DICTIONARY_NEW)
        created = super(DictionaryManager, self).create(**kwargs)
        Change.objects.create(
            action=action,
            dictionary=created,
            user=request.user,
            target=created.target,
        )
        return created

    def get_words(self, unit):
        """
        Returns list of word pairs for an unit.
        """
        words = set()

        # Prepare analyzers
        # - standard analyzer simply splits words
        # - stemming extracts stems, to catch things like plurals
        analyzers = [
            StandardAnalyzer(),
            StemmingAnalyzer(),
        ]
        source_language = unit.translation.subproject.project.source_language
        lang_code = source_language.base_code()
        # Add per language analyzer if Whoosh has it
        if has_stemmer(lang_code):
            analyzers.append(LanguageAnalyzer(lang_code))
        # Add ngram analyzer for languages like Chinese or Japanese
        if source_language.uses_ngram():
            analyzers.append(NgramAnalyzer(4))

        # Extract words from all plurals and from context
        for text in unit.get_source_plurals() + [unit.context]:
            for analyzer in analyzers:
                # Some Whoosh analyzers break on unicode
                try:
                    words.update(
                        [token.text for token in analyzer(force_text(text))]
                    )
                except (UnicodeDecodeError, IndexError) as error:
                    report_error(error, sys.exc_info())

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
            query = Q()
            for word in words:
                query |= Q(source__iexact=word)

            # Filter dictionary
            dictionary = dictionary.filter(query)

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
        return '%s/%s: %s -> %s' % (
            self.project,
            self.language,
            self.source,
            self.target
        )

    def get_absolute_url(self):
        return '%s?id=%d' % (
            reverse(
                'edit_dictionary',
                kwargs={
                    'project': self.project.slug,
                    'lang': self.language.code
                }
            ),
            self.pk
        )

    def get_parent_url(self):
        return reverse(
            'show_dictionary',
            kwargs={'project': self.project.slug, 'lang': self.language.code}
        )

    def edit(self, request, source, target):
        '''
        Edits word in a dictionary.
        '''
        from weblate.trans.models.changes import Change
        self.source = source
        self.target = target
        self.save()
        Change.objects.create(
            action=Change.ACTION_DICTIONARY_EDIT,
            dictionary=self,
            user=request.user,
            target=self.target,
        )
