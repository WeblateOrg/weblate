# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("trans", "0112_translation_parent")]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION weblate_source_workflow_gate(
                    requested_project_id bigint, exclusive boolean
                ) RETURNS jsonb
                LANGUAGE plpgsql VOLATILE PARALLEL UNSAFE AS $$
                DECLARE
                    workflows jsonb;
                BEGIN
                    IF exclusive THEN
                        PERFORM id FROM trans_project
                        WHERE id = requested_project_id FOR UPDATE;
                    ELSE
                        PERFORM id FROM trans_project
                        WHERE id = requested_project_id FOR KEY SHARE;
                    END IF;
                    -- A separate statement in a VOLATILE function sees changes
                    -- committed while the preceding row lock was waiting.
                    SELECT COALESCE(jsonb_object_agg(language_id, source_language_id), '{}')
                    INTO workflows FROM trans_workflowsetting
                    WHERE trans_workflowsetting.project_id = requested_project_id
                        AND source_language_id IS NOT NULL;
                    RETURN workflows;
                END;
                $$;
            """,
            reverse_sql="DROP FUNCTION weblate_source_workflow_gate(bigint, boolean);",
        ),
    ]
