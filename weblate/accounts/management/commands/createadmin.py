from django.core.management.base import BaseCommand
from optparse import make_option
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'setups admin user with admin password (INSECURE!)'

    def handle(self, *args, **options):
        '''
        Create admin account with admin password.

        This is useful mostly for setup inside appliances, when user wants
        to be able to login remotely and change password then.
        '''
        user = User.objects.create_user('admin', 'admin@example.com', 'admin')
        user.first_name = 'Weblate'
        user.last_name = 'Admin'
        user.is_superuser = True
        user.is_staff = True
        user.is_active = True
        user.save()
