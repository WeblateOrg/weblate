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

class TranslationSchema(SchemaClass):
    unit = NUMERIC
    target = TEXT
    language = NUMERIC

class SourceSchema(SchemaClass):
    unit = NUMERIC
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
    if not hasattr(get_source_index, 'ix_source'):
        get_source_index.ix_source = index.open_dir(
            settings.WHOOSH_INDEX,
            indexname = 'source'
        )
    return get_source_index.ix_source

def get_translation_index():
    if not hasattr(get_translation_index, 'ix_translation'):
        get_translation_index.ix_translation = index.open_dir(
            settings.WHOOSH_INDEX,
            indexname = 'translation'
        )
    return get_translation_index.ix_translation

def get_source_writer(buffered = True):
    if not buffered:
        return get_source_index().writer()
    if not hasattr(get_source_writer, 'source_writer'):
        get_source_writer.source_writer = BufferedWriter(get_source_index())
    return get_source_writer.source_writer

def get_translation_writer(buffered = True):
    if not buffered:
        return get_translation_index().writer()
    if not hasattr(get_translation_writer, 'translation_writer'):
        get_translation_writer.translation_writer = BufferedWriter(get_translation_index())
    return get_translation_writer.translation_writer
