# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from weblate.accounts import defaults as accounts_defaults
from weblate.accounts.models import WeblateAccountsConf
from weblate.addons.defaults import DEFAULT_WEBLATE_ADDONS
from weblate.addons.models import AddonsConf
from weblate.checks.defaults import DEFAULT_CHECK_LIST
from weblate.checks.models import WeblateChecksConf
from weblate.formats.defaults import DEFAULT_FORMATS
from weblate.formats.models import FormatsConf
from weblate.lang import defaults as lang_defaults
from weblate.lang.models import WeblateLanguagesConf
from weblate.machinery.defaults import DEFAULT_WEBLATE_MACHINERY
from weblate.machinery.models import WeblateConf as MachineryConf
from weblate.trans import defaults as trans_defaults
from weblate.trans.backups import ProjectBackup
from weblate.trans.models import Project
from weblate.trans.models._conf import WeblateConf as TransConf
from weblate.utils import defaults as utils_defaults
from weblate.utils.models import WeblateConf as UtilsConf
from weblate.vcs import defaults as vcs_defaults
from weblate.vcs.models import VCSConf


class DefaultsTest(SimpleTestCase):
    def test_registry_defaults(self) -> None:
        self.assertEqual(WeblateChecksConf.CHECK_LIST, DEFAULT_CHECK_LIST)
        self.assertEqual(FormatsConf.FORMATS, DEFAULT_FORMATS)
        self.assertEqual(AddonsConf.WEBLATE_ADDONS, DEFAULT_WEBLATE_ADDONS)
        self.assertEqual(MachineryConf.WEBLATE_MACHINERY, DEFAULT_WEBLATE_MACHINERY)
        self.assertEqual(VCSConf.VCS_BACKENDS, vcs_defaults.DEFAULT_VCS_BACKENDS)
        self.assertEqual(TransConf.AUTOFIX_LIST, trans_defaults.DEFAULT_AUTOFIX_LIST)

    def test_scalar_defaults(self) -> None:
        self.assertEqual(
            WeblateAccountsConf.REGISTRATION_OPEN,
            accounts_defaults.DEFAULT_REGISTRATION_OPEN,
        )
        self.assertEqual(
            WeblateLanguagesConf.SIMPLIFY_LANGUAGES,
            lang_defaults.DEFAULT_SIMPLIFY_LANGUAGES,
        )
        self.assertEqual(TransConf.SITE_TITLE, trans_defaults.DEFAULT_SITE_TITLE)
        self.assertEqual(TransConf.REQUIRE_LOGIN, trans_defaults.DEFAULT_REQUIRE_LOGIN)
        self.assertEqual(
            TransConf.ENABLE_SHARING, trans_defaults.DEFAULT_ENABLE_SHARING
        )
        self.assertEqual(
            UtilsConf.TRANSLATION_UPLOAD_MAX_SIZE,
            utils_defaults.DEFAULT_TRANSLATION_UPLOAD_MAX_SIZE,
        )
        self.assertEqual(
            UtilsConf.SENTRY_PROFILES_SAMPLE_RATE,
            utils_defaults.DEFAULT_SENTRY_PROFILES_SAMPLE_RATE,
        )
        self.assertEqual(
            UtilsConf.GOOGLE_CLOUD_ERROR_REPORTING,
            utils_defaults.DEFAULT_GOOGLE_CLOUD_ERROR_REPORTING,
        )
        self.assertEqual(
            UtilsConf.OPENTELEMETRY_SERVICE_NAME,
            utils_defaults.DEFAULT_OPENTELEMETRY_SERVICE_NAME,
        )
        self.assertEqual(
            VCSConf.VCS_CLONE_DEPTH,
            vcs_defaults.DEFAULT_VCS_CLONE_DEPTH,
        )

    def test_backup_import_limits(self) -> None:
        self.assertEqual(
            ProjectBackup.MAX_ARCHIVE_MEMBERS,
            trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_MEMBERS,
        )
        self.assertEqual(
            ProjectBackup.MAX_COMPRESSED_ENTRY_SIZE,
            trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE,
        )
        self.assertEqual(
            ProjectBackup.MIN_COMPRESSED_RATIO_SIZE,
            trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MIN_RATIO_SIZE,
        )
        self.assertEqual(
            ProjectBackup.MAX_COMPRESSED_ENTRY_RATIO,
            trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_RATIO,
        )
        self.assertEqual(
            ProjectBackup.MAX_TOTAL_UNCOMPRESSED_SIZE,
            trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_TOTAL_UNCOMPRESSED_SIZE,
        )

    @override_settings(LICENSE_REQUIRED=True, LICENSE_FILTER=None)
    def test_license_requirement_uses_require_login(self) -> None:
        project = Project(access_control=Project.ACCESS_PUBLIC)

        with override_settings(REQUIRE_LOGIN=False):
            self.assertTrue(project.needs_license())

        with override_settings(REQUIRE_LOGIN=True):
            self.assertFalse(project.needs_license())
