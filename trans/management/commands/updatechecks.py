from django.core.management.base import BaseCommand, CommandError
from trans.models import Unit
from ftsearch.models import WordLocation, Word
from optparse import make_option

class Command(BaseCommand):
    help = 'updates checks for all units'

    def handle(self, *args, **options):
        units = Unit.objects.all()
        for unit in units:
            unit.check()
