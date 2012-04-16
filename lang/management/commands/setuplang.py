# -*- coding: UTF-8 -*-
from django.core.management.base import BaseCommand
from optparse import make_option
from lang.models import Language

class Command(BaseCommand):
    help = 'Populates language definitions'

    option_list = BaseCommand.option_list + (
        make_option('--no-update',
            action='store_false',
            dest='update',
            default=True,
            help='Updates existing language definitions'),
        )

    def handle(self, *args, **options):
        Language.objects.setup(options['update'])
