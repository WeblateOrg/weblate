from django.core.management.base import BaseCommand, CommandError
from lang.models import Language
from translate.lang import data

class Command(BaseCommand):
    help = 'Populates language definitions'

    def handle(self, *args, **options):
        for code, props in data.languages.items():
            lang, created = Language.objects.get_or_create(
                code = code,
                name = props[0],
                nplurals = props[1],
                pluralequation = props[2])

