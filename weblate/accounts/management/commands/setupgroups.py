from django.core.management.base import BaseCommand
from optparse import make_option
from accounts.models import create_groups

class Command(BaseCommand):
    help = 'setups default groups'
    option_list = BaseCommand.option_list + (
        make_option('--move',
            action='store_true',
            dest='move',
            default=False,
            help='Move all users to Users group'),
        make_option('--no-update',
            action='store_false',
            dest='update',
            default=True,
            help='Prevents updates to existing group definitions'),
        )

    def handle(self, *args, **options):
        create_groups(options['update'], options['move'])
