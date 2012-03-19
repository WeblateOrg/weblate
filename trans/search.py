'''
Whoosh based full text search.
'''

import whoosh
import os
from whoosh.fields import SchemaClass, TEXT, ID, NUMERIC
from django.db.models.signals import post_syncdb
from django.conf import settings
from whoosh import index
from whoosh.writing import BufferedWriter

class TargetSchema(SchemaClass):
    checksum = ID(stored = True, unique = True)
    target = TEXT
    translation = NUMERIC

class SourceSchema(SchemaClass):
    checksum = ID(stored = True, unique = True)
    source = TEXT
    context = TEXT
    translation = NUMERIC

def create_source_index():
    return index.create_in(
        settings.WHOOSH_INDEX,
        schema = SourceSchema,
        indexname = 'source'
    )

def create_target_index(lang):
    return index.create_in(
        settings.WHOOSH_INDEX,
        schema = TargetSchema,
        indexname = 'target-%s' % lang
    )

def create_index(sender=None, **kwargs):
    if not os.path.exists(settings.WHOOSH_INDEX):
        os.mkdir(settings.WHOOSH_INDEX)
        create_source_index()

post_syncdb.connect(create_index)

def get_source_index():
    if not hasattr(get_source_index, 'ix_source'):
        get_source_index.ix_source = index.open_dir(
            settings.WHOOSH_INDEX,
            indexname = 'source'
        )
    return get_source_index.ix_source

def get_target_index(lang):
    if not hasattr(get_target_index, 'ix_target'):
        get_target_index.ix_target = {}
    if not lang in get_target_index.ix_target:
        try:
            get_target_index.ix_target[lang] = index.open_dir(
                settings.WHOOSH_INDEX,
                indexname = 'target-%s' % lang
            )
        except whoosh.index.EmptyIndexError:
            get_target_index.ix_target[lang] = create_target_index(lang)
    return get_target_index.ix_target[lang]

def get_source_writer(buffered = True):
    if not buffered:
        return get_source_index().writer()
    if not hasattr(get_source_writer, 'source_writer'):
        get_source_writer.source_writer = BufferedWriter(get_source_index())
    return get_source_writer.source_writer

def get_target_writer(lang, buffered = True):
    if not buffered:
        return get_target_index(lang).writer()
    if not hasattr(get_target_writer, 'target_writer'):
        get_target_writer.target_writer = {}
    if not lang in get_target_writer.target_writer:
        get_target_writer.target_writer[lang] = BufferedWriter(get_target_index(lang))
    return get_target_writer.target_writer[lang]

def get_source_searcher():
    return get_source_writer().searcher()

def get_target_searcher(lang):
    return get_target_writer(lang).searcher()
