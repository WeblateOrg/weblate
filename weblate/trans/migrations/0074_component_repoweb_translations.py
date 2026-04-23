# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models

import weblate.utils.render


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0073_alter_change_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="component",
            name="repoweb_translations",
            field=models.CharField(
                blank=True,
                help_text="Link to repository browser for translation files, use {{branch}} for branch, {{filename}} and {{line}} as filename and line placeholders. If left empty, the Repository browser above will be used. You might want to strip leading directory by using {{filename|parentdir}}.",
                max_length=200,
                validators=[weblate.utils.render.validate_repoweb],
                verbose_name="Repository browser for translations",
            ),
        ),
    ]
