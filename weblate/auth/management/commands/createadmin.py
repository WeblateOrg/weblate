#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


from django.core.management.base import CommandError
from django.db.models import Q

from weblate.auth.models import User
from weblate.utils.backup import make_password
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "setups admin user with random password"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=None,
            help="Password to set, random is generated if not specified",
        )
        parser.add_argument(
            "--no-password",
            action="store_true",
            default=False,
            help="Do not set password at all (useful with --update)",
        )
        parser.add_argument(
            "--username", default="admin", help='Admin username, defaults to "admin"'
        )
        parser.add_argument(
            "--email",
            default="admin@example.com",
            help='Admin email, defaults to "admin@example.com"',
        )
        parser.add_argument(
            "--name",
            default="Weblate Admin",
            help='Admin name, defaults to "Weblate Admin"',
        )
        parser.add_argument(
            "--update",
            action="store_true",
            default=False,
            help="Change password for this account if exists",
        )

    def handle(self, *args, **options):
        """Create admin account with admin password.

        This is useful mostly for setup inside appliances, when user wants to be able to
        login remotely and change password then.
        """
        try:
            user = User.objects.filter(
                Q(username=options["username"]) | Q(email=options["email"])
            ).get()
        except User.DoesNotExist:
            user = None
        except User.MultipleObjectsReturned:
            raise CommandError("Multiple users matched given parameters!")

        if user and not options["update"]:
            raise CommandError("User exists, specify --update to update existing")

        if options["no_password"]:
            password = None
        elif options["password"]:
            password = options["password"]
        else:
            password = make_password(13)
            self.stdout.write(f"Using generated password: {password}")

        if user and options["update"]:
            self.stdout.write(f"Updating user {user.username}")
            user.email = options["email"]
            if password is not None and not user.check_password(password):
                user.set_password(password)
        else:
            self.stdout.write("Creating user {}".format(options["username"]))
            user = User.objects.create_user(
                options["username"], options["email"], password
            )
        user.full_name = options["name"]
        user.is_superuser = True
        user.is_active = True
        user.save()
