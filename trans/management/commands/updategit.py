from django.core.management.base import BaseCommand, CommandError
from trans.models import SubProject
from optparse import make_option
from django.conf import settings

class Command(BaseCommand):
    help = 'updates git repos'
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option('--all',
            action='store_true',
            dest='all',
            default=False,
            help='Update all projects'),
        )

    def handle(self, *args, **options):
        settings.LOGGING['loggers']['weblate']['handlers'] = ['console']
        if options['all']:
            for s in SubProject.objects.all():
                s.update_branch()
                s.create_translations()
        for arg in args:
            prj, subprj = arg.split('/')
            s = SubProject.objects.get(slug = subprj, project__slug = prj)
            s.update_branch()
            s.create_translations()

