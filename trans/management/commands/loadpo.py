from django.core.management.base import BaseCommand, CommandError
from trans.models import SubProject

class Command(BaseCommand):
    help = '(re)loads translations from disk'
    args = '<project/subproject>'

    def handle(self, *args, **options):
        for arg in args:
            prj, subprj = arg.split('/')
            SubProject.objects.get(slug = subprj, project__slug = prj).create_translations()
