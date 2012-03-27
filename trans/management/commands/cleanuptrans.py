from django.core.management.base import BaseCommand, CommandError
from trans.models import Suggestion, Check, Unit, Project
from lang.models import Language
from optparse import make_option

class Command(BaseCommand):
    help = 'clenups orphaned checks and suggestions'

    def handle(self, *args, **options):
        for lang in Language.objects.all():
            for prj in Project.objects.all():
                translatedunits = Unit.objects.filter(translation__language = lang, translated = True, translation__subproject__project = prj).values('checksum').distinct()
                Check.objects.filter(language = lang, project = prj).exclude(checksum__in = translatedunits).delete()
                units = Unit.objects.filter(translation__language = lang, translation__subproject__project = prj).values('checksum').distinct()
                Suggestion.objects.filter(language = lang, project = prj).exclude(checksum__in = units).delete()
