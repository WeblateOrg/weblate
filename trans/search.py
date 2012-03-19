'''
Whoosh based full text search.
'''

import whoosh
import os
from whoosh.fields import SchemaClass, TEXT, KEYWORD, ID, NUMERIC
from django.db.models.signals import post_syncdb
from django.conf import settings
from whoosh import index
from whoosh.writing import BufferedWriter

ix_translation = None
ix_source = None

class TranslationSchema(SchemaClass):
    unit = ID(stored = True)
    target = TEXT
    language = NUMERIC(stored = True)

class SourceSchema(SchemaClass):
    unit = ID(stored = True)
    source = TEXT
    context = TEXT

def create_source_index():
    ix_source = index.create_in(
        settings.WHOOSH_INDEX,
        schema = SourceSchema,
        indexname = 'source'
    )

def create_translation_index():
    ix_translation = index.create_in(
        settings.WHOOSH_INDEX,
        schema = TranslationSchema,
        indexname = 'translation'
    )

def create_index(sender=None, **kwargs):
    if not os.path.exists(settings.WHOOSH_INDEX):
        os.mkdir(settings.WHOOSH_INDEX)
        create_translation_index()
        create_source_index()

post_syncdb.connect(create_index)

def get_source_index():
    if ix_source is None:
        ix_source = index.open_dir(
            settings.WHOOSH_INDEX,
            indexname = 'source'
        )
    return ix_source

def get_translation_index():
    if ix_translation is None:
        ix_translation = index.open_dir(
            settings.WHOOSH_INDEX,
            indexname = 'translationg'
        )
    return ix_translation

source_writer = None

def get_source_writer(buffered = True):
    if not buffered:
        return ix_source.writer()
    if source_writer is None:
        source_writer = BufferedWriter(ix_source)
    return source_writer

translation_writer = None

def get_translation_writer(buffered = True):
    if not buffered:
        return ix_translation.writer()
    if translation_writer is None:
        translation_writer = BufferedWriter(ix_translation)
    return translation_writer
