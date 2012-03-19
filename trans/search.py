'''
Whoosh based full text search.
'''

import whoosh
import os
from whoosh.fields import SchemaClass, TEXT, KEYWORD, ID, NUMERIC
from django.db.models.signals import post_syncdb
from django.conf import settings
from whoosh import index

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

def create_index(sender=None, **kwargs):
    if not os.path.exists(settings.WHOOSH_INDEX):
        os.mkdir(settings.WHOOSH_INDEX)
        ix_translation = index.create_in(
            settings.WHOOSH_INDEX,
            schema = TranslationSchema,
            indexname = 'translation'
        )
        ix_source = index.create_in(
            settings.WHOOSH_INDEX,
            schema = SourceSchema,
            indexname = 'source'
        )

post_syncdb.connect(create_index)

def get_ix_source():
    if ix_source is None:
        ix_source = index.open_dir(
            settings.WHOOSH_INDEX,
            indexname = 'source'
        )
    return ix_source

def get_ix_translationg():
    if ix_translationg is None:
        ix_translationg = index.open_dir(
            settings.WHOOSH_INDEX,
            indexname = 'translationg'
        )
    return ix_translationg
