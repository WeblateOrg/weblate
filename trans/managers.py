from django.db import models, connection
from django.conf import settings

from lang.models import Language

from util import is_plural, split_plural, join_plural, msg_checksum

import search

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

    def is_indexed(self, unit):
        from ftsearch.models import WordLocation
        return WordLocation.objects.filter(unit = unit).exists()

    def remove_from_index(self, unit):
        from ftsearch.models import WordLocation
        return WordLocation.objects.filter(unit = unit).delete()

    def separate_words(self, words):
        return settings.SEARCH_WORD_SPLIT_REGEX.split(words)

    def get_similar_list(self, words):
        words = [word.lower() for word in self.separate_words(words)]
        return [word for word in words if not word in IGNORE_SIMILAR and len(word) > 0]

    def __index_item(self, text, language, unit):
        from ftsearch.models import WordLocation, Word

        # Split to words
        p = settings.SEARCH_STEMMER()
        stemmed_text = [p.stem(s.lower()) for s in self.separate_words(text) if s != '']

        # Store words in database
        for i, word in enumerate(stemmed_text):
            if word in IGNORE_WORDS:
                continue

            wordobj, created = Word.objects.get_or_create(
                word = word,
                language = language
            )
            WordLocation.objects.create(
                unit = unit,
                word = wordobj,
                location = i
            )

    def add_to_index(self, unit, writer_translation = None, writer_source = None):
        if writer_translation is None:
            writer_translation = search.get_translation_writer()
        if writer_source is None:
            writer_source = search.get_source_writer()

        writer_translation.add(
            target = '\n'.join(unit.get_target_plurals()),
            language = unit.translation.language.id,
            unit = unit.id
        )
        writer_source.add(
            source = '\n'.join(unit.get_source_plurals()),
            context = unit.context,
            unit = unit.id
        )

    def __get_match_rows(self, query, language):
        from ftsearch.models import Word
        # Grab relevant words
        word_objects = Word.objects.filter(word__in = query, language = language)

        field_list = 'w0.unit_id'
        table_list = ''
        clause_list = ''

        table_number = 0

        for word in word_objects:

            if table_number > 0:
                table_list += ', '
                clause_list += ' and w%d.unit_id = w%d.unit_id and ' \
                               % (table_number - 1, table_number)

            table_list += 'ftsearch_wordlocation w%d' % table_number
            clause_list += 'w%d.word_id=%d' % (table_number, word.id)

            table_number += 1

        if not table_list or not clause_list:
            return []

        cur = connection.cursor()
        cur.execute('select %s from %s where %s' \
                % (field_list, table_list, clause_list))

        rows = cur.fetchall()

        return [row[0] for row in rows]

    def search(self, query, language):
        from trans.models import Unit
        if isinstance(query, str) or isinstance(query, unicode):
            # split the string into a list of search terms
            query = self.separate_words(query)
        elif not isinstance(query, list) and  not isinstance(query, tuple):
            raise TypeError("search must be called with a string or a list")

        p = settings.SEARCH_STEMMER()
        # lowercase and stem each word
        stemmed_query = [p.stem(s.lower()) for s in query if s != '']

        # get a row from the db for each matching word
        rows = self.__get_match_rows(stemmed_query, language)
        if rows == []:
            return self.none()

        return self.filter(pk__in = rows)
