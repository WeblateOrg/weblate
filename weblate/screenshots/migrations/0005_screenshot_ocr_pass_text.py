# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("screenshots", "0004_screenshot_backup_author_claim"),
    ]

    operations = [
        migrations.RunSQL(
            # Store a bounded prefix of complete lines for each pass.
            sql="""
                CREATE FUNCTION weblate_ocr_pass_text(
                    cache jsonb, pass_index integer
                ) RETURNS text
                LANGUAGE SQL IMMUTABLE STRICT PARALLEL SAFE
                RETURN (
                    SELECT btrim(regexp_replace(
                        coalesce(string_agg(line, ' ' ORDER BY line_number), ''),
                        '[[:space:]]+', ' ', 'g'
                    ))
                    FROM (
                        SELECT value #>> '{}' AS line, line_number,
                               sum(octet_length(value #>> '{}') + 1)
                                   OVER (ORDER BY line_number) AS total_bytes
                        FROM jsonb_path_query(
                            cache -> 'passes' -> pass_index,
                            '$.lines[*].text ? (@.type() == "string")'
                        ) WITH ORDINALITY AS recognized(value, line_number)
                    ) AS lines
                    WHERE total_bytes <= 32768
                );
            """,
            reverse_sql="DROP FUNCTION weblate_ocr_pass_text(jsonb, integer);",
        ),
        migrations.AddField(
            model_name="screenshotocr",
            name="first_pass_text",
            field=models.GeneratedField(
                expression=models.Func(
                    "data",
                    models.Value(0),
                    function="weblate_ocr_pass_text",
                    output_field=models.TextField(),
                ),
                output_field=models.TextField(),
                db_persist=True,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="screenshotocr",
            name="second_pass_text",
            field=models.GeneratedField(
                expression=models.Func(
                    "data",
                    models.Value(1),
                    function="weblate_ocr_pass_text",
                    output_field=models.TextField(),
                ),
                output_field=models.TextField(),
                db_persist=True,
                null=True,
            ),
        ),
    ]
