# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.commands.makemessages import check_programs
from django.core.management.utils import handle_extensions
from django.utils.text import get_text_list

from weblate.addons.extractors.django.constants import DJANGO_IGNORE_PATTERNS
from weblate.utils.management.commands.makemessages import Command as BaseCommand


class Command(BaseCommand):
    """
    Extraction-only variant of makemessages using trusted output paths.

    Unlike stock ``makemessages``, this command never discovers repository
    ``locale`` or ``conf/locale`` directories as output locations. Persistent
    gettext output is routed to the trusted paths provided in
    ``settings.LOCALE_PATHS`` rather than to repository locale directories.

    This guarantee relies on the inherited ``find_files()`` implementation
    continuing to honor ``ignore_patterns`` for ``locale`` directories before
    reaching Django's special-case locale directory handling.

    The command line is intentionally narrow because this is an internal
    extractor entry point used by Weblate add-ons, not a general replacement
    for Django's ``makemessages`` command.
    """

    EXTRA_IGNORE_PATTERNS = DJANGO_IGNORE_PATTERNS

    def add_arguments(self, parser):
        """
        Register only the internal CLI supported by this extractor.

        This intentionally replaces Django's default ``makemessages`` argument
        set and does not call ``super().add_arguments()``. The command is used
        only by Weblate's internal add-on integration and should not expose
        the broader stock management command interface.
        """
        parser.add_argument(
            "-d",
            "--domain",
            choices=("django", "djangojs"),
            required=True,
        )
        parser.add_argument("--source-prefix", default=".")
        parser.add_argument("--no-wrap", action="store_true")
        parser.add_argument("--no-location", action="store_true")

    def handle(self, *args, **options):
        self.domain = options["domain"]
        self.verbosity = options["verbosity"]
        self.symlinks = False
        self.ignore_patterns = list(self.EXTRA_IGNORE_PATTERNS)
        self.source_prefix = os.path.normpath(options["source_prefix"])

        if options["no_wrap"]:
            self.msgmerge_options = [*self.msgmerge_options, "--no-wrap"]
            self.msguniq_options = [*self.msguniq_options, "--no-wrap"]
            self.msgattrib_options = [*self.msgattrib_options, "--no-wrap"]
            self.xgettext_options = [*self.xgettext_options, "--no-wrap"]
        if options["no_location"]:
            self.msgmerge_options = [*self.msgmerge_options, "--no-location"]
            self.msguniq_options = [*self.msguniq_options, "--no-location"]
            self.msgattrib_options = [*self.msgattrib_options, "--no-location"]
            self.xgettext_options = [*self.xgettext_options, "--no-location"]

        self.no_obsolete = False
        self.keep_pot = True

        exts = ["js"] if self.domain == "djangojs" else ["html", "txt", "py"]
        self.extensions = handle_extensions(exts)

        if self.verbosity > 1:
            self.stdout.write(
                "examining files with the extensions: "
                f"{get_text_list(list(self.extensions), 'and')}"
            )

        self.invoked_for_django = False
        self.locale_paths = []
        self.default_locale_path = None
        for path in settings.LOCALE_PATHS:
            locale_path = os.path.abspath(path)
            if locale_path not in self.locale_paths:
                self.locale_paths.append(locale_path)
        if not self.locale_paths:
            msg = "Missing trusted locale output path for extraction."
            raise CommandError(msg)
        self.default_locale_path = self.locale_paths[0]
        os.makedirs(self.default_locale_path, exist_ok=True)

        check_programs("xgettext", "msguniq")

        self.build_potfiles()

    def find_files(self, root):
        if root == "." and self.source_prefix not in {"", "."}:
            root = os.path.join(".", self.source_prefix)
        return super().find_files(root)
