from django.core.management.base import BaseCommand, CommandError
from trans.models import Unit
import trans.search
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
            trans.search.create_source_index()
            trans.search.create_translation_index()

        with trans.search.get_source_writer(buffered = False) as src_writer:
            with trans.search.get_translation_writer(buffered = False) as trans_writer:
                for unit in Unit.objects.all().iterator():
                    Unit.objects.add_to_index(unit, trans_writer, src_writer)
