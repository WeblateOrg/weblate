# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.db import models
from django.db.models import Q
from weblate.lang.models import Language
from weblate.trans.formats import AutoFormat, StringIOMode
from weblate.trans.models.project import Project
from translate.storage.csvl10n import csvfile
from django.core.urlresolvers import reverse
from whoosh.analysis import StandardAnalyzer, StemmingAnalyzer


class DictionaryManager(models.Manager):
    # pylint: disable=W0232

    def upload(self, request, project, language, fileobj, method):
        '''
        Handles dictionary update.
        '''
        filecopy = fileobj.read()
        fileobj.close()
        # Load file using translate-toolkit
        store = AutoFormat.load(StringIOMode(fileobj.name, filecopy))

        ret, skipped = self.import_store(
            request, project, language, store, method
        )

        if ret == 0 and skipped > 0 and isinstance(store, csvfile):
            # Retry with different CSV scheme
            store = csvfile(
                StringIOMode(fileobj.name, filecopy),
                ('source', 'target')
            )
            ret, skipped = self.import_store(
                request, project, language, store, method
            )

        return ret

    def import_store(self, request, project, language, store, method):
        '''
        Actual importer
        '''
        from weblate.trans.models.changes import Change
        ret = 0
        skipped = 0

        # process all units
        for unit in store.units:
            # We care only about translated things
            if not unit.istranslatable() or not unit.istranslated():
                skipped += 1
                continue

            # Ignore too long words
            if len(unit.source) > 200 or len(unit.target) > 200:
                continue

            # Get object
            word, created = self.get_or_create(
                project=project,
                language=language,
                source=unit.source
            )

            # Already existing entry found
            if not created:
                # Same as current -> ignore
                if unit.target == word.target:
                    continue
                if method == 'add':
                    # Add word
                    word = self.create(
                        request,
                        action=Change.ACTION_DICTIONARY_UPLOAD,
                        project=project,
                        language=language,
                        source=unit.source
                    )
                elif method != 'overwrite':
                    # No overwriting or adding
                    continue

            # Store word
            word.target = unit.target
            word.save()

            ret += 1

        return ret, skipped

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
        analyzers = (StandardAnalyzer(), StemmingAnalyzer())

        # Extract words from all plurals and from context
        for text in unit.get_source_plurals() + [unit.context]:
            for analyzer in analyzers:
                words = words.union([token.text for token in analyzer(text)])

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


class Dictionary(models.Model):
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)
    source = models.CharField(max_length=200, db_index=True)
    target = models.CharField(max_length=200)

    objects = DictionaryManager()

    class Meta(object):
        ordering = ['source']
        permissions = (
            ('upload_dictionary', "Can import dictionary"),
        )
        app_label = 'trans'

    def __unicode__(self):
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
