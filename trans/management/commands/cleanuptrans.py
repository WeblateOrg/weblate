from django.core.management.base import BaseCommand, CommandError
from trans.models import Suggestion, Check, Unit
from lang.models import Language
from optparse import make_option

class Command(BaseCommand):
    help = 'clenups orphaned checks and suggestions'

    def handle(self, *args, **options):
        for lang in Language.objects.all():
            translatedunits = Unit.objects.filter(translation__language = lang, translated = True).values('checksum').distinct()
            Check.objects.filter(language = lang).exclude(checksum__in = translatedunits).delete()
            units = Unit.objects.filter(translation__language = lang).values('checksum').distinct()
            Suggestion.objects.filter(language = lang).exclude(checksum__in = units).delete()
