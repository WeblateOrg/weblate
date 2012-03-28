from django.core.management.base import BaseCommand, CommandError
from trans.models import SubProject
from optparse import make_option

class Command(BaseCommand):
    help = 'forces commiting changes to git repo'
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option('--all',
            action='store_true',
            dest='all',
            default=False,
            help='Check all projects'),
        )

    def handle(self, *args, **options):
        if options['all']:
            for s in SubProject.objects.all():
                s.commit_pending()
        for arg in args:
            prj, subprj = arg.split('/')
            s = SubProject.objects.get(slug = subprj, project__slug = prj)
            s.commit_pending()



