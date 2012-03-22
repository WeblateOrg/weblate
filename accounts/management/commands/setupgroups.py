from django.core.management.base import BaseCommand, CommandError
from trans.models import SubProject
from optparse import make_option
from django.contrib.auth.models import Group, Permission, User

class Command(BaseCommand):
    help = 'setups default groups'
    option_list = BaseCommand.option_list + (
        make_option('--move',
            action='store_true',
            dest='move',
            default=False,
            help='Move all users to Users group'),
        )

    def handle(self, *args, **options):
        group, created = Group.objects.get_or_create(name = 'Users')
        group.permissions.add(
            Permission.objects.get(codename = 'upload_translation'),
            Permission.objects.get(codename = 'overwrite_translation'),
            Permission.objects.get(codename = 'save_translation'),
            Permission.objects.get(codename = 'accept_suggestion'),
            Permission.objects.get(codename = 'delete_suggestion'),
            Permission.objects.get(codename = 'ignore_check'),
        )
        group, created = Group.objects.get_or_create(name = 'Managers')
        group.permissions.add(
            Permission.objects.get(codename = 'author_translation'),
            Permission.objects.get(codename = 'upload_translation'),
            Permission.objects.get(codename = 'overwrite_translation'),
            Permission.objects.get(codename = 'save_translation'),
            Permission.objects.get(codename = 'accept_suggestion'),
            Permission.objects.get(codename = 'delete_suggestion'),
            Permission.objects.get(codename = 'ignore_check'),
        )
        if options['move']:
            for u in User.objects.all():
                u.groups.add(group)
