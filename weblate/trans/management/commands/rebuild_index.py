from weblate.trans.management.commands import UnitCommand
from weblate.trans.models import Unit
from weblate.lang.models import Language
from weblate.trans.search import FULLTEXT_INDEX, create_source_index, create_target_index
from optparse import make_option

class Command(UnitCommand):
    help = 'rebuilds index for fulltext search'
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
            create_source_index()
            for lang in languages:
                create_target_index(lang = lang.code)

        base = self.get_units(*args, **options)

        if base.count() == 0:
            return

        with FULLTEXT_INDEX.source_writer(buffered = False) as writer:
            for unit in base.values('checksum', 'source', 'context').iterator():
                Unit.objects.add_to_source_index(
                    unit['checksum'],
                    unit['source'],
                    unit['context'],
                    writer)

        for lang in languages:
            with FULLTEXT_INDEX.target_writer(lang = lang.code, buffered = False) as writer:
                for unit in base.filter(translation__language =
                    lang).exclude(target = '').values('checksum', 'target').iterator():
                    Unit.objects.add_to_target_index(
                        unit['checksum'],
                        unit['target'],
                        writer)

