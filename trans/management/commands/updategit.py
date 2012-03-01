from django.core.management.base import BaseCommand, CommandError
from trans.models import SubProject
from optparse import make_option

class Command(BaseCommand):
    help = 'updates git repos'
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option('--all',
            action='store_true',
            dest='all',
            default=False,
            help='Force rereading files even when they should be up to date'),
        )

    def handle(self, *args, **options):
        if options['all']:
            for s in SubProject.objects.all():
                s.update_branch()
                s.create_translations()
        for arg in args:
            prj, subprj = arg.split('/')
            s = SubProject.objects.get(slug = subprj, project__slug = prj)
            s.update_branch()
            s.create_translations()

