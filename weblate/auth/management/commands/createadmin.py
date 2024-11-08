# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.management.base import CommandError
from django.db.models import Q

from weblate.auth.models import User
from weblate.utils.backup import make_password
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "setups admin user with random password"

    def add_arguments(self, parser) -> None:
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

    def handle(self, *args, **options) -> None:
        """
        Create admin account with admin password.

        This is useful mostly for setup inside appliances, when user wants to be able to
        login remotely and change password then.
        """
        email = options["email"]
        username = options["username"]
        if not email:
            email = "admin@example.com"
            self.stdout.write(f"Blank e-mail for admin, using {email} instead!")
        matching_users = User.objects.filter(Q(username=username) | Q(email=email))

        if len(matching_users) == 0:
            user = None
        elif len(matching_users) == 1:
            user = matching_users[0]
        else:
            for user in matching_users:
                self.stderr.write(
                    f"Found matching user: username={user.username} email={user.email}"
                )
            msg = "Multiple users matched given parameters!"
            raise CommandError(msg)

        if user and not options["update"]:
            msg = f"User {username} already exists, specify --update to update existing"
            raise CommandError(msg)

        if options["no_password"]:
            password = None
        elif options["password"]:
            password = options["password"]
        else:
            password = make_password(13)
            self.stdout.write(f"Using generated password: {password}")

        if user and options["update"]:
            self.stdout.write(f"Updating user {user.username}")
            user.email = email
            if password is not None and not user.check_password(password):
                user.set_password(password)
        else:
            self.stdout.write(f"Creating user {username}")
            user = User.objects.create_user(username, email, password)
        user.full_name = options["name"]
        user.is_superuser = True
        user.is_active = True
        user.save()
