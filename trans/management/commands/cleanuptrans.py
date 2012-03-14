from django.core.management.base import BaseCommand, CommandError
from trans.models import Suggestion, Check, Unit
from optparse import make_option

class Command(BaseCommand):
    help = 'clenups orphaned checks and suggestions'

    def handle(self, *args, **options):
        units = Unit.objects.values('checksum').distinct()
        Check.objects.exclude(checksum__in = units).delete()
        Suggestion.objects.exclude(checksum__in = units).delete()
