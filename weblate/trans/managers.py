# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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
from django.conf import settings
from django.core.cache import cache
import itertools

from weblate.lang.models import Language

from whoosh import qparser

from util import msg_checksum, get_source, get_target, get_context

from weblate.trans.search import FULLTEXT_INDEX, SOURCE_SCHEMA, TARGET_SCHEMA

# Set of ignored words
IGNORE_WORDS = set([
    'a',
    'an',
    'and',
    'are',
    'as',
    'at',
    'be',
    'but',
    'by',
    'for',
    'if',
    'in',
    'into',
    'is',
    'it',
    'no',
    'not',
    'of',
    'on',
    'or',
    's',
    'such',
    't',
    'that',
    'the',
    'their',
    'then',
    'there',
    'these',
    'they',
    'this',
    'to',
    'was',
    'will',
    'with',
])

# Set of words to ignore in similar lookup
IGNORE_SIMILAR = set([
    'also',
    'class',
    'href',
    'http',
    'me',
    'most',
    'net',
    'per',
    'span',
    'their',
    'theirs',
    'you',
    'your',
    'yours',
    'www',
]) | IGNORE_WORDS

class TranslationManager(models.Manager):
    def update_from_blob(self, subproject, code, path, force = False):
        '''
        Parses translation meta info and creates/updates translation object.
        '''
        lang = Language.objects.auto_get_or_create(code = code)
        translation, created = self.get_or_create(
            language = lang,
            language_code = code,
            subproject = subproject
        )
        if translation.filename != path:
            force = True
            translation.filename = path
        translation.update_from_blob(force)

        return translation

    def enabled(self):
        return self.filter(enabled = True)

class UnitManager(models.Manager):
    def update_from_unit(self, translation, unit, pos, template = None):
        '''
        Process translation toolkit unit and stores/updates database entry.
        '''
        if template is None:
            src = get_source(unit)
            ctx = get_context(unit)
        else:
            src = get_target(template)
            ctx = get_context(template)
        checksum = msg_checksum(src, ctx)

        # Try getting existing unit
        from weblate.trans.models import Unit
        dbunit = None
        try:
            dbunit = self.get(
                translation = translation,
                checksum = checksum)
            force = False
        except Unit.MultipleObjectsReturned:
            # Some inconsistency (possibly race condition), try to recover
            self.filter(
                translation = translation,
                checksum = checksum).delete()
        except Unit.DoesNotExist:
            pass

        # Create unit if it does not exist
        if dbunit is None:
            dbunit = Unit(
                translation = translation,
                checksum = checksum,
                source = src,
                context = ctx)
            force = True

        # Update all details
        dbunit.update_from_unit(unit, pos, force, template)

        # Return result
        return dbunit, force

    def filter_type(self, rqtype, translation):
        '''
        Basic filtering based on unit state or failed checks.
        '''
        from weblate.trans.models import Suggestion, Check
        from weblate.trans.checks import CHECKS
        if rqtype == 'all':
            return self.all()
        elif rqtype == 'fuzzy':
            return self.filter(fuzzy = True)
        elif rqtype == 'untranslated':
            return self.filter(translated = False)
        elif rqtype == 'suggestions':
            sugs = Suggestion.objects.filter(
                language = translation.language,
                project = translation.subproject.project)
            sugs = sugs.values_list('checksum', flat = True)
            return self.filter(checksum__in = sugs)
        elif rqtype in CHECKS or rqtype in ['allchecks', 'sourcechecks']:

            # Filter checks for current project
            checks = Check.objects.filter(
                project = translation.subproject.project,
                ignore = False
            )

            # Filter by language
            if rqtype == 'allchecks':
                checks = checks.filter(language = translation.language)
            elif rqtype == 'sourcechecks':
                checks = checks.filter(language = None)
            elif CHECKS[rqtype].source and CHECKS[rqtype].target:
                checks = checks.filter(
                    Q(language = translation.language) | Q(language = None)
                )
            elif CHECKS[rqtype].source:
                checks = checks.filter(language = None)
            elif CHECKS[rqtype].target:
                checks = checks.filter(language = translation.language)

            # Filter by check type
            if not rqtype in ['allchecks', 'sourcechecks']:
                checks = checks.filter(check = rqtype)

            checks = checks.values_list('checksum', flat = True)
            return self.filter(checksum__in = checks, translated = True)
        else:
            return self.all()

    def count_type(self, rqtype, translation):
        '''
        Cached counting of failing checks (and other stats).
        '''
        # Use precalculated data if we can
        if rqtype == 'all':
            return translation.total
        elif rqtype == 'fuzzy':
            return translation.fuzzy
        elif rqtype == 'untranslated':
            return translation.total - translation.translated

        # Try to get value from cache
        cache_key = 'counts-%s-%s-%s' % (
            translation.subproject.get_full_slug(),
            translation.language.code,
            rqtype
        )
        ret = cache.get(cache_key)
        if ret is not None:
            return ret

        # Actually count units
        ret = self.filter_type(rqtype, translation).count()

        # Update cache
        cache.set(cache_key, ret)
        return ret

    def review(self, date, user):
        '''
        Returns units touched by other users since given time.
        '''
        if user.is_anonymous():
            return self.none()
        from weblate.trans.models import Change
        sample = self.all()[0]
        changes = Change.objects.filter(unit__translation = sample.translation, timestamp__gte = date).exclude(user = user)
        return self.filter(id__in = changes.values_list('unit__id', flat = True))

    def add_to_source_index(self, checksum, source, context, writer):
        '''
        Updates/Adds to source index given unit.
        '''
        writer.update_document(
            checksum = unicode(checksum),
            source = unicode(source),
            context = unicode(context),
        )

    def add_to_target_index(self, checksum, target, writer):
        '''
        Updates/Adds to target index given unit.
        '''
        writer.update_document(
            checksum = unicode(checksum),
            target = unicode(target),
        )

    def add_to_index(self, unit):
        '''
        Updates/Adds to all indices given unit.
        '''
        if settings.OFFLOAD_INDEXING:
            from weblate.trans.models import IndexUpdate
            IndexUpdate.objects.get_or_create(unit = unit)
            return

        writer_target = FULLTEXT_INDEX.target_writer(unit.translation.language.code)
        writer_source = FULLTEXT_INDEX.source_writer()

        self.add_to_source_index(
            unit.checksum,
            unit.source,
            unit.context,
            writer_source)
        self.add_to_target_index(
            unit.checksum,
            unit.target,
            writer_target)

    def __search(self, searcher, field, schema, query):
        '''
        Wrapper for fulltext search.
        '''
        qp = qparser.QueryParser(field, schema)
        q = qp.parse(query)
        return [searcher.stored_fields(d)['checksum'] for d in searcher.docs_for_query(q)]


    def search(self, query, source = True, context = True, translation = True, checksums = False):
        '''
        Performs full text search on defined set of fields.

        Returns queryset unless checksums is set.
        '''
        ret = set()
        if source or context:
            with FULLTEXT_INDEX.source_searcher(not settings.OFFLOAD_INDEXING) as searcher:
                if source:
                    ret = ret.union(self.__search(searcher, 'source', SOURCE_SCHEMA, query))
                if context:
                    ret = ret.union(self.__search(searcher, 'context', SOURCE_SCHEMA, query))

        if translation:
            sample = self.all()[0]
            with FULLTEXT_INDEX.target_searcher(sample.translation.language.code, not settings.OFFLOAD_INDEXING) as searcher:
                ret = ret.union(self.__search(searcher, 'target', TARGET_SCHEMA, query))

        if checksums:
            return ret

        return self.filter(checksum__in = ret)

    def similar(self, unit):
        '''
        Finds similar units to current unit.
        '''
        ret = set([unit.checksum])
        with FULLTEXT_INDEX.source_searcher(not settings.OFFLOAD_INDEXING) as searcher:
            # Extract up to 10 terms from the source
            terms = [kw for kw, score in searcher.key_terms_from_text('source', unit.source, numterms = 10) if not kw in IGNORE_SIMILAR]
            cnt = len(terms)
            # Try to find at least configured number of similar strings, remove up to 4 words
            while len(ret) < settings.SIMILAR_MESSAGES and cnt > 0 and len(terms) - cnt < 4:
                for search in itertools.combinations(terms, cnt):
                    ret = ret.union(self.search(' '.join(search), True, False, False, True))
                cnt -= 1

        return self.filter(
                    translation__subproject__project = unit.translation.subproject.project,
                    translation__language = unit.translation.language,
                    checksum__in = ret).exclude(
                    target__in = ['', unit.target])

    def same(self, unit):
        '''
        Units with same source withing same project.
        '''
        return self.filter(
            checksum = unit.checksum,
            translation__subproject__project = unit.translation.subproject.project,
            translation__language = unit.translation.language
        )

class DictionaryManager(models.Manager):
    def upload(self, project, language, fileobj, overwrite):
        '''
        Handles dictionary update.
        '''
        from weblate.trans.models import ttkit

        ret = 0

        # Load file using ttkit
        store = ttkit(fileobj)

        # process all units
        for unit in store.units:
            # We care only about translated things
            if not unit.istranslatable() or not unit.istranslated():
                continue

            # Ignore too long words
            if len(unit.source) > 200 or len(unit.target) > 200:
                continue

            # Get object
            word, created = self.get_or_create(
                project = project,
                language = language,
                source = unit.source
            )

            # Should we write translation
            if not created and not overwrite:
                continue

            # Store word
            word.target = unit.target
            word.save()

            ret += 1

        return ret
