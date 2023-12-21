# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.management.commands.makemessages import Command as BaseCommand

from weblate.utils.files import should_skip


class Command(BaseCommand):
    def find_files(self, root):
        return [obj for obj in super().find_files(root) if not should_skip(obj.path)]

    def build_potfiles(self):
        if self.domain == "django":
            self.xgettext_options = self.xgettext_options[:] + [
                "--keyword=pgettext_noop:1c,2"
            ]
        return super().build_potfiles()
