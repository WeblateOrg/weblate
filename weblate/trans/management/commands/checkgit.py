from django.core.management.base import BaseCommand
from weblate.trans.models import SubProject
from optparse import make_option

class Command(BaseCommand):
    help = 'checks status of git repo'
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
                r = s.get_repo()
                print '%s:' % s
                print r.git.status()
        for arg in args:
            prj, subprj = arg.split('/')
            s = SubProject.objects.get(slug = subprj, project__slug = prj)
            r = s.get_repo()
            print '%s:' % s
            print r.git.status()


