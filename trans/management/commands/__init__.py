from django.core.management.base import BaseCommand
from optparse import make_option
from trans.models import Unit

class UnitCommand(BaseCommand):
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option('--all',
            action='store_true',
            dest='all',
            default=False,
            help='work on all projects'),
        )

    def get_units(self, *args, **options):
        if options['all']:
            base = Unit.objects.all()
        else:
            base = Unit.objects.none()
            for arg in args:
                parts = arg.split('/')
                if len(parts) == 2:
                    prj, subprj = parts
                    base |= Unit.objects.filter(
                        translation__subproject__slug = subprj,
                        translation__subproject__project__slug = prj)

                else:
                    prj = parts[0]
                    base |= Unit.objects.filter(translation__subproject__project__slug = prj)
        return base

