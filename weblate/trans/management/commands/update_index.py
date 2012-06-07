
from django.core.management.base import BaseCommand
from weblate.trans.models import IndexUpdate
from weblate.lang.models import Language
from weblate.trans.search import FULLTEXT_INDEX, create_source_index, create_target_index
from optparse import make_option

class Command(BaseCommand):
    help = 'updates index for fulltext search'

    def handle(self, *args, **options):
        languages = Language.objects.all()

        base = IndexUpdate.objects.all()

        if base.count() == 0:
            return

        with FULLTEXT_INDEX.source_writer(buffered = False) as writer:
            for update in base.iterator():
                Unit.objects.add_to_source_index(
                    update.unit.checksum,
                    update.unit.source,
                    update.unit.context,
                    writer)

        for lang in languages:
            with FULLTEXT_INDEX.target_writer(lang = lang.code, buffered = False) as writer:
                for update in base.filter(unit__translation__language =
                    lang).exclude(unit__target = '').iterator():
                    Unit.objects.add_to_target_index(
                        update.unit.checksum,
                        update.unit.target,
                        writer)


        base.delete()
