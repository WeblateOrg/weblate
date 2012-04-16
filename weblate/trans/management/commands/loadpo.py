from django.core.management.base import BaseCommand
from weblate.trans.models import SubProject
from optparse import make_option

class Command(BaseCommand):
    help = '(re)loads translations from disk'
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option('--force',
            action='store_true',
            dest='force',
            default=False,
            help='Force rereading files even when they should be up to date'),
        )

    def handle(self, *args, **options):
        for arg in args:
            prj, subprj = arg.split('/')
            s = SubProject.objects.get(slug = subprj, project__slug = prj)
            s.create_translations(options['force'])
