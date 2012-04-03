from trans.management.commands import UnitCommand
from trans.models import Unit
from lang.models import Language
import trans.search
from optparse import make_option

class Command(UnitCommand):
    help = 'updates index for fulltext search'
    option_list = UnitCommand.option_list + (
        make_option('--clean',
            action='store_true',
            dest='clean',
            default=False,
            help='removes also all words from database'),
        )

    def handle(self, *args, **options):
        languages = Language.objects.all()
        if options['clean']:
            trans.search.create_source_index()
            for lang in languages:
                trans.search.create_target_index(lang = lang.code)

        base = self.get_units(*args, **options)

        if base.count() == 0:
            return

        with trans.search.get_source_writer(buffered = False) as writer:
            for unit in base.values('checksum', 'source', 'context', 'translation_id').iterator():
                Unit.objects.add_to_source_index(
                    unit['checksum'],
                    unit['source'],
                    unit['context'],
                    unit['translation_id'],
                    writer)

        for lang in languages:
            with trans.search.get_target_writer(lang = lang.code, buffered = False) as writer:
                for unit in base.filter(translation__language =
                    lang).exclude(target = '').values('checksum', 'target', 'translation_id').iterator():
                    Unit.objects.add_to_target_index(
                        unit['checksum'],
                        unit['target'],
                        unit['translation_id'],
                        writer)

