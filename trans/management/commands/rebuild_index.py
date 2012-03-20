from django.core.management.base import BaseCommand, CommandError
from trans.models import Unit
from lang.models import Language
import trans.search
from optparse import make_option
from django.db.models import Q

class Command(BaseCommand):
    help = 'updates index for fulltext search'
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option('--clean',
            action='store_true',
            dest='clean',
            default=False,
            help='removes also all words from database'),
        ) + (
        make_option('--all',
            action='store_true',
            dest='all',
            default=False,
            help='Update all projects'),
        )


    def handle(self, *args, **options):
        languages = Language.objects.all()
        if options['clean']:
            trans.search.create_source_index()
            for lang in languages:
                trans.search.create_target_index(lang = lang.code)

        if options['all']:
            base = Unit.objects.all()
        else:
            base = Unit.objects.none()
            for arg in args:
                parts = arg.split('/')
                print parts
                if len(parts) == 2:
                    prj, subprj = parts
                    base |= Unit.objects.filter(
                        translation__subproject__slug = subprj,
                        translation__subproject__project__slug = prj)

                else:
                    prj = parts[0]
                    base |= Unit.objects.filter(translation__subproject__project__slug = prj)

        if base.count() == 0:
            return

        with trans.search.get_source_writer(buffered = False) as writer:
            for unit in base.values('checksum', 'source', 'context', 'translation_id').iterator():
                print unit
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

