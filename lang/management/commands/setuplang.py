from django.core.management.base import BaseCommand, CommandError
from lang.models import Language
from translate.lang import data

EXTRALANGS = [
    ('ur', 'Urdu', 2, '(n != 1)'),
    ('uz@latin', 'Uzbek (latin)', 1, '0'),
    ('uz', 'Uzbek', 1, '0'),
    ('sr@latin', 'Serbian (latin)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('be@latin', 'Belarusian (latin)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
]

class Command(BaseCommand):
    help = 'Populates language definitions'

    def handle(self, *args, **options):
        for code, props in data.languages.items():
            lang, created = Language.objects.get_or_create(
                code = code)
            lang.name = props[0].split(';')[0]
            # Use shorter name
            if code == 'ia':
                lang.name = 'Interlingua'
            # Workaround bug in data
            if code == 'gd' and props[2] == 'nplurals=4; plural=(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3':
                lang.nplurals = 4
                lang.pluralequation = '(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3'
            else:
                lang.nplurals = props[1]
                lang.pluralequation = props[2]
            lang.save()
        for props in EXTRALANGS:
            lang, created = Language.objects.get_or_create(
                code = props[0])
            lang.name = props[1]
            lang.nplurals = props[2]
            lang.pluralequation = props[3]
            lang.save()

