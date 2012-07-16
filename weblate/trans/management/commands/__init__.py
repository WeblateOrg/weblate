from django.core.management.base import BaseCommand
from optparse import make_option
from weblate.trans.models import Unit

class UnitCommand(BaseCommand):
    '''
    Command which accepts project/subproject/--all params to process units.
    '''
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option('--all',
            action='store_true',
            dest='all',
            default=False,
            help='work on all projects'),
        )

    def get_units(self, *args, **options):
        '''
        Returns list of units matching parameters.
        '''
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

