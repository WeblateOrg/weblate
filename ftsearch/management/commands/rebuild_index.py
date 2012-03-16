from django.core.management.base import BaseCommand, CommandError
from trans.models import Unit
from ftsearch.models import WordLocation, Word
from optparse import make_option

class Command(BaseCommand):
    help = 'updates index for fulltext search'
    option_list = BaseCommand.option_list + (
        make_option('--clean',
            action='store_true',
            dest='clean',
            default=False,
            help='removes also all words from database'),
        )

    def handle(self, *args, **options):
        if options['clean']:
            Word.objects.all().delete()
        WordLocation.objects.all().delete()
        units = Unit.objects.all()
        for unit in units:
            Unit.objects.add_to_index(unit)
