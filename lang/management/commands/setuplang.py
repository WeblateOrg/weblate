from django.core.management.base import BaseCommand, CommandError
from lang.models import Language
from translate.lang import data

EXTRALANGS = [
    ('ur', 'Urdu', 2, '(n != 1)'),
]

class Command(BaseCommand):
    help = 'Populates language definitions'

    def handle(self, *args, **options):
        for code, props in data.languages.items():
            lang, created = Language.objects.get_or_create(
                code = code,
                name = props[0],
                nplurals = props[1],
                pluralequation = props[2])
        for props in EXTRALANGS:
            lang, created = Language.objects.get_or_create(
                code = props[0],
                name = props[1],
                nplurals = props[2],
                pluralequation = props[3])

