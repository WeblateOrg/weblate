# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from runpy import run_path

from django.db import connection
from django.db.migrations.loader import MigrationLoader

from weblate.accounts.models import AuditLog
from weblate.trans.tests.test_views import FixtureTestCase


class ProjectTokenMigrationTest(FixtureTestCase):
    def test_repair_project_tokens(self) -> None:
        scripts = Path(__file__).resolve().parents[3] / "ci" / "migrate-scripts"
        run_path(str(scripts / "setup-project-token-repair.py"))
        migration = import_module(
            "weblate.accounts.migrations.0040_repair_project_tokens"
        )
        state = MigrationLoader(connection).project_state(
            [("accounts", "0040_repair_project_tokens")]
        )
        with connection.schema_editor() as editor:
            migration.repair_project_tokens(state.apps, editor)
        run_path(str(scripts / "assert-project-token-repair.py"))
        audit_count = AuditLog.objects.count()
        with connection.schema_editor() as editor:
            migration.repair_project_tokens(state.apps, editor)
        self.assertEqual(AuditLog.objects.count(), audit_count)
        run_path(str(scripts / "assert-project-token-repair.py"))
