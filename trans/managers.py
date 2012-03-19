from django.db import models, connection
from django.conf import settings

from lang.models import Language

from whoosh import qparser

from util import is_plural, split_plural, join_plural, msg_checksum

import trans.search

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

# List of
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
    def update_from_blob(self, subproject, code, path, blob, force = False):
        '''
        Parses translation meta info and creates/updates translation object.
        '''
        lang = Language.objects.get(code = code)
        trans, created = self.get_or_create(
            language = lang,
            subproject = subproject,
            filename = path)
        trans.update_from_blob(blob, force)

class UnitManager(models.Manager):
    def update_from_unit(self, translation, unit, pos):
        '''
        Process translation toolkit unit and stores/updates database entry.
        '''
        if hasattr(unit.source, 'strings'):
            src = join_plural(unit.source.strings)
        else:
            src = unit.source
        ctx = unit.getcontext()
        checksum = msg_checksum(src, ctx)
        from trans.models import Unit
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

        if dbunit is None:
            dbunit = Unit(
                translation = translation,
                checksum = checksum,
                source = src,
                context = ctx)
            force = True

        dbunit.update_from_unit(unit, pos, force)
        return dbunit

    def filter_type(self, rqtype):
        import trans.models
        if rqtype == 'all':
            return self.all()
        elif rqtype == 'fuzzy':
            return self.filter(fuzzy = True)
        elif rqtype == 'untranslated':
            return self.filter(translated = False)
        elif rqtype == 'suggestions':
            sample = self.all()[0]
            sugs = trans.models.Suggestion.objects.filter(
                language = sample.translation.language,
                project = sample.translation.subproject.project)
            sugs = sugs.values_list('checksum', flat = True)
            return self.filter(checksum__in = sugs)
        elif rqtype in [x[0] for x in trans.models.CHECK_CHOICES]:
            sample = self.all()[0]
            sugs = trans.models.Check.objects.filter(
                language = sample.translation.language,
                project = sample.translation.subproject.project,
                check = rqtype,
                ignore = False)
            sugs = sugs.values_list('checksum', flat = True)
            return self.filter(checksum__in = sugs, fuzzy = False, translated = True)
        else:
            return self.all()

    def add_to_source_index(self, checksum, source, context, translation, writer):
        writer.update_document(
            checksum = checksum,
            source = source,
            context = context,
            translation = translation,
        )

    def add_to_target_index(self, checksum, target, translation, writer):
        writer.update_document(
            checksum = checksum,
            target = target,
            translation = translation,
        )

    def add_to_index(self, unit, writer_target = None, writer_source = None):
        if writer_target is None:
            writer_target = trans.search.get_target_writer(unit.translation.language.code)
        if writer_source is None:
            writer_source = trans.search.get_source_writer()

        self.add_to_source_index(
            unit.checksum,
            unit.source,
            unit.context,
            unit.translation_id,
            writer_source)
        self.add_to_target_index(
            unit.checksum,
            unit.target,
            unit.translation_id,
            writer_target)

    def search(self, query, source = True, context = True, translation = True):
        ret = []
        sample = self.all()[0]
        if source or context:
            with trans.search.get_source_searcher() as searcher:
                if source:
                    qp = qparser.QueryParser('source', trans.search.SourceSchema())
                    q = qp.parse(query)
                    for doc in searcher.docs_for_query(q):
                        ret.append(searcher.stored_fields(doc)['checksum'])
                if context:
                    qp = qparser.QueryParser('context', trans.search.SourceSchema())
                    q = qp.parse(query)
                    for doc in searcher.docs_for_query(q):
                        ret.append(searcher.stored_fields(doc)['checksum'])

        if translation:
            with trans.search.get_target_searcher(sample.translation.language.code) as searcher:
                qp = qparser.QueryParser('target', trans.search.TargetSchema())
                q = qp.parse(query)
                for doc in searcher.docs_for_query(q):
                    ret.append(searcher.stored_fields(doc)['checksum'])

        return self.filter(checksum__in = ret)

    def similar(self, unit):
        ret = []
        with trans.search.get_source_searcher() as searcher:
            doc = searcher.document_number(checksum = unit.checksum)
            mlt = searcher.more_like(doc, 'source', unit.source)
            for m in mlt:
                ret.append(m['checksum'])
        return self.filter(
                    translation__subproject__project = unit.translation.subproject.project,
                    translation__language = unit.translation.language,
                    checksum__in = ret).exclude(checksum = unit.checksum, target = '')
