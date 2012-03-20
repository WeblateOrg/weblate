from django.core.management.base import BaseCommand, CommandError
from trans.models import Unit
from optparse import make_option

class Command(BaseCommand):
    help = 'updates checks for units'
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option('--all',
            action='store_true',
            dest='all',
            default=False,
            help='Update all projects'),
        )

    def handle(self, *args, **options):
        if options['all']:
            for unit in Unit.objects.all().iterator():
                unit.check()
        for arg in args:
            parts = arg.split('/')
            if len(parts) == 2:
                prj, subprj = parts
                for unit in Unit.objects.filter(
                        translation__subproject__slug = subprj,
                        translation__subproject__project__slug = prj):
                    unit.check()

            else:
                prj = parts[0]
                for unit in Unit.objects.filter(translation__subproject__project__slug = prj):
                    unit.check()
