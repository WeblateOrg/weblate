# -*- coding: UTF-8 -*-
from django.core.management.base import BaseCommand
from lang.models import Language
from translate.lang import data

EXTRALANGS = [
    ('ur', 'Urdu', 2, '(n != 1)'),
    ('uz@latin', 'Uzbek (latin)', 1, '0'),
    ('uz', 'Uzbek', 1, '0'),
    ('sr@latin', 'Serbian (latin)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('sr_SR@latin', 'Serbian (latin)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('sr@cyrillic', 'Serbian (cyrrilic)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('sr_SR@cyrillic', 'Serbian (cyrrilic)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('be@latin', 'Belarusian (latin)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('en_US', 'English (United States)', 2, '(n != 1)'),
    ('nb_NO', 'Norwegian Bokmål', 2, '(n != 1)'),
    ('pt_PT', 'Portuguese (Portugal)', 2, '(n > 1)'),
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
            # Shorten name
            elif code == 'el':
                lang.name = 'Greek'
            elif code == 'st':
                lang.name = 'Sotho'
            elif code == 'oc':
                lang.name = 'Occitan'
            elif code == 'nb':
                lang.name = 'Norwegian Bokmål'
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

